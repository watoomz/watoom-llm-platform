#!/usr/bin/env python3
"""Safe archive tool for models: list, inspect, read and extract assets from zip, tar, 7z and rar archives into a project.

  asset_archive.py list    ARCHIVE [--select GLOB]... [--limit N]
  asset_archive.py inspect ARCHIVE [--test]
  asset_archive.py read    ARCHIVE --entry PATH [--max-bytes N] [--base64]
  asset_archive.py extract ARCHIVE --project PROJECT [--dest DIR] [--select GLOB]... [--dry-run] [--overwrite]
  asset_archive.py status  REQUEST_ID
  asset_archive.py serve   [--once]          # host worker for formats the caller cannot open itself

Output is always one JSON document on stdout. `ok` is false and `errors` is non-empty whenever anything about the archive or the
extraction went wrong; `warnings` are things that were skipped or look unusual. The exit status is 0 when ok, 1 when not, 2 for bad usage.
Standard library only. 7z needs `7z` and rar needs `unrar`, which only the host has; callers without it hand the work to the host worker through
a request file and wait for the result.
"""
import argparse
import base64
import collections
import fnmatch
import json
import os
import pathlib
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
import zlib

VERSION = 1
SOURCE_ROOTS = ('/data/ai/assets', '/data/ai/projects', '/data/ai/artifacts')
PROJECT_ROOT = '/data/ai/projects'
GLOBAL_QUEUE = '/data/ai/projects/work/.archive-requests'   # the pod can only write under projects/* and its own state
PROJECT_QUEUE = '.opencode/archive-requests'
PROTECTED_DEST = {'.git', '.godot', '.opencode', '.import', '.source-backup'}
JUNK_NAMES = {'.ds_store', 'thumbs.db', 'desktop.ini'}
JUNK_PARTS = {'__macosx'}
CHUNK = 1 << 20
LIMITS = {'max_total_bytes': 30 << 30, 'max_file_bytes': 8 << 30, 'max_entries': 300000, 'bomb_ratio': 200, 'bomb_min_bytes': 2 << 30,
          'read_max': 262144, 'list_limit': 200}


class Problem(Exception):
    def __init__(self, code, message, entry=None):
        super().__init__(message)
        self.code, self.entry = code, entry


class Result:
    def __init__(self, op, archive=None):
        self.d = {'ok': True, 'op': op, 'tool_version': VERSION, 'archive': archive, 'errors': [], 'warnings': [], 'summary': ''}

    def error(self, code, message, entry=None):
        self.d['ok'] = False
        item = {'code': code, 'message': message}
        if entry:
            item['entry'] = entry
        if len(self.d['errors']) < 100:
            self.d['errors'].append(item)
        else:
            self.d['errors_truncated'] = self.d.get('errors_truncated', 0) + 1

    def warn(self, code, message, entry=None):
        item = {'code': code, 'message': message}
        if entry:
            item['entry'] = entry
        if len(self.d['warnings']) < 100:
            self.d['warnings'].append(item)
        else:
            self.d['warnings_truncated'] = self.d.get('warnings_truncated', 0) + 1


class Entry:
    __slots__ = ('name', 'raw', 'size', 'packed', 'crc', 'kind', 'encrypted', 'ref')

    def __init__(self, name, raw, size, packed=0, crc=None, kind='file', encrypted=False, ref=None):
        self.name, self.raw, self.size, self.packed, self.crc, self.kind, self.encrypted, self.ref = name, raw, size, packed, crc, kind, encrypted, ref


# ---------------------------------------------------------------- names and selection
def norm_entry(name):
    n = name.replace('\\', '/')
    if '\0' in n or any(ord(c) < 32 for c in n):
        raise Problem('UNSAFE_NAME', 'control characters in entry name')
    if n.startswith('/') or re.match(r'^[A-Za-z]:', n):
        raise Problem('UNSAFE_NAME', 'absolute path in archive')
    parts = [p for p in n.split('/') if p not in ('', '.')]
    if not parts:
        raise Problem('UNSAFE_NAME', 'empty entry name')
    if '..' in parts:
        raise Problem('UNSAFE_NAME', 'path traversal ("..") in archive')
    if any(len(p) > 200 for p in parts) or len('/'.join(parts)) > 240:
        raise Problem('PATH_TOO_LONG', 'entry path is too long for Windows/Godot tooling')
    return '/'.join(parts)


def glob_regex(pattern):
    out, i = '', 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith('**/', i):
            out += '(?:.*/)?'; i += 3; continue
        if pattern.startswith('**', i):
            out += '.*'; i += 2; continue
        out += '[^/]*' if c == '*' else '[^/]' if c == '?' else re.escape(c)
        i += 1
    return re.compile(out)


def is_junk(name):
    parts = [p.lower() for p in name.split('/')]
    return parts[-1] in JUNK_NAMES or any(p in JUNK_PARTS for p in parts)


def make_selector(selects, excludes, prefix, exts):
    inc = [glob_regex(s.strip('/')) for s in selects] + ([glob_regex(prefix.strip('/') + '/**')] if prefix else [])
    exc = [glob_regex(s.strip('/')) for s in excludes]
    extset = {('.' + e.strip().lstrip('.')).lower() for e in (exts or '').split(',') if e.strip()}

    def match(name):
        if selects or prefix:
            hit = any(r.fullmatch(name) for r in inc) or any(name.startswith(x.strip('/') + '/') for x in selects if not re.search(r'[*?]', x))
            if not hit:
                return False
        if exc and any(r.fullmatch(name) for r in exc):
            return False
        if extset and os.path.splitext(name)[1].lower() not in extset:
            return False
        return True
    return match


# ---------------------------------------------------------------- policy and paths
class Policy:
    def __init__(self, source_roots=None, project_root=None, global_queue=None, limits=None):
        env = os.environ.get('WATOOM_ARCHIVE_SOURCE_ROOTS')
        self.source_roots = tuple(source_roots or (env.split(':') if env else SOURCE_ROOTS))
        self.project_root = project_root or os.environ.get('WATOOM_ARCHIVE_PROJECT_ROOT') or PROJECT_ROOT
        self.global_queue = global_queue or os.environ.get('WATOOM_ARCHIVE_QUEUE') or GLOBAL_QUEUE
        self.limits = dict(LIMITS, **(limits or {}))

    def archive_path(self, value):
        p = os.path.realpath(value)
        if not any(p == r or p.startswith(r.rstrip('/') + '/') for r in map(os.path.realpath, self.source_roots)):
            raise Problem('ARCHIVE_NOT_ALLOWED', 'archives may only be read from: ' + ', '.join(self.source_roots))
        if not os.path.isfile(p):
            raise Problem('ARCHIVE_NOT_FOUND', 'archive does not exist: ' + value)
        return p

    def project_path(self, value):
        root = os.path.realpath(self.project_root)
        cand = value if os.path.isabs(value) else None
        if cand is None:
            hits = [h for h in (os.path.join(root, d, value) for d in sorted(os.listdir(root)) if os.path.isdir(os.path.join(root, d))) if os.path.isdir(h)]
            if len(hits) != 1:
                raise Problem('PROJECT_UNKNOWN', 'project name %r matched %d projects; pass the absolute project path' % (value, len(hits)))
            cand = hits[0]
        p = os.path.realpath(cand)
        rel = os.path.relpath(p, root)
        if rel.startswith('..') or len(rel.split('/')) != 2 or os.path.islink(cand.rstrip('/')):
            raise Problem('PROJECT_NOT_ALLOWED', 'project must be a folder like %s/<category>/<name>' % self.project_root)
        if not os.path.isdir(p):
            raise Problem('PROJECT_UNKNOWN', 'project folder does not exist: ' + value)
        return p

    def dest_path(self, project, dest):
        parts = [x for x in dest.replace('\\', '/').split('/') if x not in ('', '.')]
        if not parts or '..' in parts or os.path.isabs(dest):
            raise Problem('DEST_NOT_ALLOWED', 'dest must be a relative folder inside the project')
        if parts[0].lower() in PROTECTED_DEST or any(p.lower() in PROTECTED_DEST for p in parts):
            raise Problem('DEST_NOT_ALLOWED', 'dest may not be inside %s' % sorted(PROTECTED_DEST))
        target = os.path.join(project, *parts)
        cur = project
        for part in parts:
            cur = os.path.join(cur, part)
            if os.path.islink(cur):
                raise Problem('DEST_NOT_ALLOWED', 'dest passes through a symlink')
        return target


# ---------------------------------------------------------------- format detection and backends
def detect_format(path):
    with open(path, 'rb') as f:
        head = f.read(512)
        f.seek(257)
        tar_magic = f.read(5)
    if head.startswith(b'PK\x03\x04') or head.startswith(b'PK\x05\x06') or zipfile.is_zipfile(path):
        return 'zip'
    if head.startswith(b'Rar!\x1a\x07'):
        return 'rar'
    if head.startswith(b'7z\xbc\xaf\x27\x1c'):
        return '7z'
    if head[:2] == b'\x1f\x8b' or head[:6] == b'\xfd7zXZ\x00' or head[:3] == b'BZh' or tar_magic == b'ustar':
        return 'tar'
    if head[:4] == b'\x28\xb5\x2f\xfd':
        return 'zst'
    return 'unknown'


def multipart_hint(path):
    b = os.path.basename(path).lower()
    return bool(re.search(r'\.part0*[2-9]\d*\.rar$|\.r\d\d$|\.z\d\d$|\.7z\.\d{3}$', b))


class ZipBackend:
    name = 'zip'

    def __init__(self, path):
        try:
            self.z = zipfile.ZipFile(path)
        except zipfile.BadZipFile as e:
            raise Problem('ARCHIVE_UNREADABLE', 'not a readable zip (%s). It may be truncated or the download incomplete; check the file size against the source.' % e)

    def entries(self):
        for i in self.z.infolist():
            kind = 'dir' if i.is_dir() else 'file'
            mode = (i.external_attr >> 16) & 0xFFFF
            if mode and stat.S_ISLNK(mode):
                kind = 'link'
            elif mode and (stat.S_ISCHR(mode) or stat.S_ISBLK(mode) or stat.S_ISFIFO(mode) or stat.S_ISSOCK(mode)):
                kind = 'other'
            yield Entry(i.filename, i.filename, i.file_size, i.compress_size, i.CRC, kind, bool(i.flag_bits & 1), i)

    def open(self, e):
        try:
            return self.z.open(e.ref)
        except RuntimeError as ex:
            raise Problem('ENCRYPTED_ENTRY', 'entry needs a password (%s)' % ex, e.name)
        except NotImplementedError as ex:
            raise Problem('UNSUPPORTED_COMPRESSION', str(ex), e.name)
        except zipfile.BadZipFile as ex:
            raise Problem('ENTRY_CORRUPT', str(ex), e.name)

    def verifies_crc(self):
        return True


class TarBackend:
    name = 'tar'

    def __init__(self, path):
        try:
            self.t = tarfile.open(path, 'r:*')
            self.members = self.t.getmembers()
        except (tarfile.TarError, EOFError, OSError) as e:
            raise Problem('ARCHIVE_UNREADABLE', 'not a readable tar archive (%s). It may be truncated.' % e)

    def entries(self):
        for m in self.members:
            kind = 'dir' if m.isdir() else 'file' if m.isreg() else 'link' if (m.issym() or m.islnk()) else 'other'
            yield Entry(m.name, m.name, m.size, m.size, None, kind, False, m)

    def open(self, e):
        f = self.t.extractfile(e.ref)
        if f is None:
            raise Problem('ENTRY_CORRUPT', 'cannot read entry', e.name)
        return f

    def verifies_crc(self):
        return False


class SevenZipBackend:
    """7z through the `7z` program (host only). Listing uses the technical format; extraction goes to a private temp dir."""
    name = '7z'
    external = True

    def __init__(self, path):
        self.path = path
        self.exe = shutil.which('7z') or shutil.which('7za') or shutil.which('7zz')
        if not self.exe:
            raise Problem('BACKEND_MISSING', '7z is not installed here')
        p = subprocess.run([self.exe, 'l', '-slt', '-spd', '-bd', '-sccUTF-8', '--', path], capture_output=True, text=True, errors='replace', timeout=600)
        self.out = p.stdout
        if p.returncode not in (0, 1) and '----------' not in p.stdout:
            text = (p.stderr or p.stdout).strip()
            raise Problem('ARCHIVE_UNREADABLE', '7z could not open the archive: ' + (text.splitlines()[-1][:200] if text else 'no output') + '. It may be truncated, damaged or password protected.')
        self.warnings = [l for l in p.stdout.splitlines() if l.startswith(('WARNING:', 'ERROR:'))][:5]
        self.rc = p.returncode

    def entries(self):
        body = self.out.split('\n----------\n', 1)
        if len(body) < 2:
            return
        for block in body[1].split('\n\n'):
            f = dict(l.split(' = ', 1) for l in block.splitlines() if ' = ' in l)
            if 'Path' not in f:
                continue
            attr = f.get('Attributes', '')
            is_dir = f.get('Folder') == '+' or 'D' in attr.split(' ')[0]
            kind = 'dir' if is_dir else 'link' if re.search(r'\bl[rwx-]{9}\b', attr) or f.get('Symbolic Link') else 'file'
            crc = int(f['CRC'], 16) if f.get('CRC') else None
            yield Entry(f['Path'], f['Path'], int(f.get('Size') or 0), int(f.get('Packed Size') or 0), crc, kind, f.get('Encrypted') == '+', None)

    def extract(self, entries, outdir):
        names = os.path.join(outdir, '.names.txt')
        with open(names, 'w', encoding='utf-8') as nf:
            nf.write('\n'.join(e.raw for e in entries) + '\n')
        p = subprocess.run([self.exe, 'x', '-y', '-bd', '-spd', '-aoa', '-scsUTF-8', '-o' + outdir, self.path, '@' + names], capture_output=True, text=True,
                           errors='replace', timeout=4 * 3600)
        os.unlink(names)
        return p.returncode, (p.stdout + p.stderr)

    def verifies_crc(self):
        return True


class UnrarBackend:
    """RAR through RARLAB's `unrar` (the distribution's 7z cannot open RAR). Never prompts for a password."""
    name = 'rar'
    external = True

    def __init__(self, path):
        self.path = path
        self.exe = shutil.which('unrar')
        if not self.exe:
            raise Problem('BACKEND_MISSING', 'unrar is not installed here')
        p = subprocess.run([self.exe, 'lt', '-scf', '-p-', '-y', '--', path], capture_output=True, text=True, errors='replace', timeout=600, stdin=subprocess.DEVNULL)
        self.out = p.stdout
        self.warnings = []
        problems = [l.strip() for l in (p.stdout + p.stderr).splitlines() if l.startswith(('ERROR:', 'Cannot', 'Corrupt', 'Unexpected end'))]
        if p.returncode != 0 and not any(l.startswith('        Name:') for l in p.stdout.splitlines()):
            hint = problems[0] if problems else (p.stderr or p.stdout).strip().splitlines()[-1:] and (p.stderr or p.stdout).strip().splitlines()[-1]
            raise Problem('ARCHIVE_UNREADABLE', 'unrar could not read the archive: %s. It may be truncated, damaged or password protected (headers encrypted).' % str(hint)[:200])
        if p.returncode != 0:
            self.warnings = problems[:3] or ['unrar reported a problem while listing (exit %d); the archive may be damaged' % p.returncode]

    def entries(self):
        for block in re.split(r'\n\s*\n', self.out):
            f = {}
            for line in block.splitlines():
                m = re.match(r'^\s*([A-Za-z0-9 ]+?):\s?(.*)$', line)
                if m:
                    f[m.group(1).strip()] = m.group(2)
            if 'Name' not in f or 'Type' not in f:
                continue
            t = f['Type'].lower()
            kind = 'dir' if 'directory' in t else 'link' if ('link' in t) else 'file' if t == 'file' else 'other'
            crc = int(f['CRC32'], 16) if re.fullmatch(r'[0-9A-Fa-f]{1,8}', f.get('CRC32', '').strip() or 'x') else None
            enc = 'encrypted' in f.get('Flags', '').lower()
            yield Entry(f['Name'], f['Name'], int(f.get('Size') or 0), int(f.get('Packed size') or 0), crc, kind, enc, None)

    def extract(self, entries, outdir):
        names = os.path.join(outdir, '.names.txt')
        with open(names, 'w', encoding='utf-8') as nf:
            nf.write('\n'.join(e.raw for e in entries) + '\n')
        p = subprocess.run([self.exe, 'x', '-y', '-p-', '-o+', '-scf', '-idq', '-r-', '--', self.path, '@' + names, outdir + '/'], capture_output=True, text=True,
                           errors='replace', timeout=4 * 3600, stdin=subprocess.DEVNULL)
        os.unlink(names)
        return p.returncode, (p.stdout + p.stderr)

    def verifies_crc(self):
        return True


def open_backend(path, fmt):
    if fmt == 'zip':
        return ZipBackend(path)
    if fmt == 'tar':
        return TarBackend(path)
    if fmt == 'rar':
        return UnrarBackend(path)
    if fmt == '7z':
        return SevenZipBackend(path)
    raise Problem('UNSUPPORTED_FORMAT', 'unsupported or unrecognised archive format (%s). Supported: zip, tar/tgz/txz, 7z, rar.' % fmt)


def needs_host(fmt):
    if fmt == 'rar':
        return not shutil.which('unrar')
    return fmt == '7z' and not (shutil.which('7z') or shutil.which('7za') or shutil.which('7zz'))


# ---------------------------------------------------------------- analysis shared by every op
def load_entries(backend, res, strip=0, include_junk=False):
    """Return (selectable entries, all). Flags per-entry problems on `res`."""
    out, seen, lower, n = [], {}, {}, 0
    for e in backend.entries():
        n += 1
        if n > LIMITS['max_entries']:
            res.error('TOO_MANY_ENTRIES', 'archive has more than %d entries' % LIMITS['max_entries'])
            break
        try:
            e.name = norm_entry(e.raw)
        except Problem as p:
            res.error(p.code, str(p), e.raw[:200])
            continue
        if e.kind in ('link', 'other'):
            res.warn('UNSUPPORTED_ENTRY_TYPE', 'skipped (%s entries are never extracted)' % ('symlink/hardlink' if e.kind == 'link' else 'special file'), e.name)
            continue
        if e.kind == 'dir':
            continue
        if not include_junk and is_junk(e.name):
            res.d['junk_skipped'] = res.d.get('junk_skipped', 0) + 1
            continue
        if e.encrypted:
            res.error('ENCRYPTED_ENTRY', 'entry is password protected; ask the owner for the password', e.name)
            continue
        if e.name in seen:
            res.warn('DUPLICATE_ENTRY', 'same path appears twice; the later one wins', e.name)
        seen[e.name] = e
        out.append(e)
    final = {}
    for e in out:
        final[e.name] = e
    out = list(final.values())
    for e in out:
        k = e.name.lower()
        if k in lower and lower[k] != e.name:
            res.error('CASE_CLASH', 'differs only by letter case from %r; both cannot exist on Windows/macOS' % lower[k], e.name)
        lower.setdefault(k, e.name)
    return out


def apply_selection(entries, match, strip):
    sel = []
    for e in entries:
        if not match(e.name):
            continue
        parts = e.name.split('/')
        if strip and len(parts) <= strip:
            continue
        sel.append(e)
    return sel


def rel_of(e, strip):
    parts = e.name.split('/')
    return '/'.join(parts[strip:]) if strip else e.name


def entry_view(e):
    return {'path': e.name, 'size': e.size, 'packed': e.packed}


def size_checks(res, sel, pol, archive_size, force_large):
    total = sum(e.size for e in sel)
    res.d['selected'] = {'files': len(sel), 'bytes': total}
    big = [e for e in sel if e.size > pol.limits['max_file_bytes']]
    for e in big[:20]:
        res.error('FILE_TOO_LARGE', 'single file is %d bytes (limit %d)' % (e.size, pol.limits['max_file_bytes']), e.name)
    if total > pol.limits['max_total_bytes'] and not force_large:
        res.error('SELECTION_TOO_LARGE', 'selected content is %.1f GiB (limit %.0f GiB). Select a subset, or pass --force-large if the owner approved it.'
                  % (total / 2**30, pol.limits['max_total_bytes'] / 2**30))
    if archive_size and total > pol.limits['bomb_min_bytes'] and total / max(archive_size, 1) > pol.limits['bomb_ratio'] and not force_large:
        res.error('BOMB_SUSPECT', 'expands %.0fx; this looks like a decompression bomb' % (total / archive_size))
    return total


# ---------------------------------------------------------------- operations
def op_list(args, pol, res, backend, entries):
    sel = apply_selection(entries, make_selector(args.select, args.exclude, args.prefix, args.ext), 0)
    sel.sort(key=lambda e: e.name)
    limit = args.limit if args.limit is not None else pol.limits['list_limit']
    res.d['entries'] = [entry_view(e) for e in sel[:limit]]
    res.d['matched'] = {'files': len(sel), 'bytes': sum(e.size for e in sel)}
    if len(sel) > limit:
        res.d['truncated'] = True
        res.d['next_steps'] = ['%d more entries match; narrow with --select/--prefix/--ext or raise --limit' % (len(sel) - limit)]
    res.d['summary'] = '%d file(s) match (%.1f MiB)' % (len(sel), res.d['matched']['bytes'] / 2**20)


def op_inspect(args, pol, res, backend, entries):
    folders = collections.Counter(e.name.split('/')[0] if '/' in e.name else '(root)' for e in entries)
    exts = collections.Counter(os.path.splitext(e.name)[1].lower() or '(none)' for e in entries)
    total = sum(e.size for e in entries)
    res.d['inspect'] = {'files': len(entries), 'uncompressed_bytes': total, 'top_folders': folders.most_common(15), 'extensions': exts.most_common(15),
                        'largest': [entry_view(e) for e in sorted(entries, key=lambda x: -x.size)[:10]],
                        'nested_archives': [e.name for e in entries if os.path.splitext(e.name)[1].lower() in ('.zip', '.rar', '.7z', '.tar', '.gz')][:20]}
    if args.test:
        bad = 0
        for e in entries:
            try:
                crc, size = 0, 0
                if getattr(backend, 'external', False):
                    break
                with backend.open(e) as f:
                    while True:
                        b = f.read(CHUNK)
                        if not b:
                            break
                        crc = zlib.crc32(b, crc); size += len(b)
                if size != e.size or (e.crc is not None and crc != e.crc):
                    raise Problem('ENTRY_CORRUPT', 'content does not match its recorded size/CRC', e.name)
            except Problem as p:
                res.error(p.code, str(p), p.entry or e.name); bad += 1
            except (zipfile.BadZipFile, EOFError, OSError, tarfile.TarError) as ex:
                res.error('ENTRY_CORRUPT', str(ex)[:200], e.name); bad += 1
        res.d['inspect']['tested'] = {'files': len(entries), 'bad': bad} if not getattr(backend, 'external', False) else 'use extract --dry-run; external extractors verify while extracting'
    res.d['summary'] = '%d file(s), %.1f MiB uncompressed, %d error(s)' % (len(entries), total / 2**20, len(res.d['errors']))


def op_read(args, pol, res, backend, entries):
    want = norm_entry(args.entry)
    hit = [e for e in entries if e.name == want]
    if not hit:
        close = [e.name for e in entries if want.lower() in e.name.lower()][:5]
        res.error('ENTRY_NOT_FOUND', 'no such entry %r%s' % (want, '; similar: ' + ', '.join(close) if close else ''))
        return
    e = hit[0]
    cap = min(args.max_bytes or pol.limits['read_max'], pol.limits['read_max'])
    data = b''
    if getattr(backend, 'external', False):
        with tempfile.TemporaryDirectory() as td:
            rc, out = backend.extract([e], td)
            p = os.path.join(td, e.raw)
            if rc != 0 or not os.path.isfile(p) or os.path.islink(p):
                res.error('EXTRACT_FAILED', 'the extractor failed to read the entry: ' + (out.strip().splitlines()[-1][:200] if out.strip() else 'no output'), e.name)
                return
            with open(p, 'rb') as f:
                data = f.read(cap + 1)
    else:
        try:
            with backend.open(e) as f:
                data = f.read(cap + 1)
                if len(data) <= cap:
                    f.read()  # drive the CRC check to the end of the entry
        except Problem as p:
            res.error(p.code, str(p), e.name); return
        except (zipfile.BadZipFile, EOFError, OSError) as ex:
            res.error('ENTRY_CORRUPT', str(ex)[:200], e.name); return
    truncated = len(data) > cap
    data = data[:cap]
    is_text = b'\0' not in data[:4096]
    res.d['entry'] = {'path': e.name, 'size': e.size, 'bytes_returned': len(data), 'truncated': truncated, 'binary': not is_text}
    if args.base64 or not is_text:
        if args.base64:
            res.d['entry']['base64'] = base64.b64encode(data).decode()
        else:
            res.d['entry']['note'] = 'binary content not shown; use --base64 or extract it'
    else:
        res.d['entry']['text'] = data.decode('utf-8', 'replace')
    res.d['summary'] = 'read %d byte(s) of %s%s' % (len(data), e.name, ' (truncated)' if truncated else '')


def same_file(path, e, crc_of):
    try:
        if os.path.getsize(path) != e.size:
            return False
        return e.crc is None or crc_of(path) == e.crc
    except OSError:
        return False


def file_crc(path):
    crc = 0
    with open(path, 'rb') as f:
        while True:
            b = f.read(CHUNK)
            if not b:
                return crc
            crc = zlib.crc32(b, crc)


def finish_file(part, target, e, res, stats):
    os.chmod(part, 0o660)
    os.replace(part, target)
    stats['extracted'] += 1
    stats['bytes'] += e.size


def op_extract(args, pol, res, backend, entries, archive_path, rid):
    project = pol.project_path(args.project)
    stem = re.sub(r'\.(tar\.(gz|xz|bz2)|tgz|txz|zip|rar|7z|tar)$', '', os.path.basename(archive_path), flags=re.I)
    dest_rel = args.dest or ('Assets/' + re.sub(r'[^A-Za-z0-9._ -]+', '_', stem))
    dest = pol.dest_path(project, dest_rel)
    strip = args.strip or 0
    sel = apply_selection(entries, make_selector(args.select, args.exclude, args.prefix, args.ext), strip)
    res.d['project'] = project
    res.d['dest'] = dest
    if not sel:
        res.error('NOTHING_SELECTED', 'no files matched your selection (strip=%d). Use `list` to see the entry paths.' % strip)
        return
    if args.max_files and len(sel) > args.max_files:
        res.error('TOO_MANY_FILES', '%d files selected, more than --max-files %d' % (len(sel), args.max_files))
        return
    size_checks(res, sel, pol, os.path.getsize(archive_path), args.force_large)
    # destination clashes inside the selection after stripping
    targets, low = {}, {}
    for e in sel:
        rel = rel_of(e, strip)
        try:
            rel = norm_entry(rel)
        except Problem as p:
            res.error(p.code, str(p), e.name); continue
        if rel.lower() in low and low[rel.lower()] != e.name:
            res.error('DEST_CLASH', 'two entries map to the same destination path %r' % rel, e.name); continue
        low[rel.lower()] = e.name
        targets[e.name] = rel
    if not res.d['ok'] and not args.partial_ok:
        res.d['summary'] = 'not extracted: fix the errors above first (or pass --partial-ok to extract the clean entries)'
        return
    sel = [e for e in sel if e.name in targets]
    free = shutil.disk_usage(project).free
    need = sum(e.size for e in sel)
    if free < need * 1.1 + (1 << 30):
        res.error('DISK_FULL', 'needs about %.1f GiB but only %.1f GiB is free' % (need / 2**30, free / 2**30))
        return
    stats = {'extracted': 0, 'bytes': 0, 'unchanged': 0, 'conflicts': 0}
    planned, extracted_names = [], []
    real_dest = os.path.realpath(dest)
    plan = []
    for e in sel:
        target = os.path.join(dest, *targets[e.name].split('/'))
        parent_real = os.path.realpath(os.path.dirname(target))
        if not (parent_real + os.sep).startswith(real_dest + os.sep) and parent_real != real_dest:
            res.error('UNSAFE_NAME', 'resolves outside the destination', e.name); continue
        if os.path.islink(target):
            res.error('DEST_NOT_ALLOWED', 'destination is a symlink', e.name); continue
        if os.path.isdir(target):
            res.error('DEST_CONFLICT', 'a folder already exists where this file would go', e.name); continue
        if os.path.exists(target):
            if same_file(target, e, file_crc):
                stats['unchanged'] += 1; continue
            if not args.overwrite:
                stats['conflicts'] += 1
                res.error('DEST_CONFLICT', 'a different file already exists; pass --overwrite to replace it', targets[e.name]); continue
        plan.append((e, target))
    res.d['plan'] = {'to_extract': len(plan), 'unchanged': stats['unchanged'], 'bytes': sum(e.size for e, _ in plan)}
    if args.dry_run:
        res.d['dry_run'] = True
        res.d['would_extract'] = [targets[e.name] for e, _ in plan][:200]
        res.d['summary'] = 'dry run: %d file(s) would be extracted (%.1f MiB), %d unchanged, %d error(s)' % (len(plan), res.d['plan']['bytes'] / 2**20, stats['unchanged'], len(res.d['errors']))
        return
    if not res.d['ok'] and not args.partial_ok:
        res.d['summary'] = 'not extracted: resolve the errors above'
        return
    os.makedirs(dest, mode=0o770, exist_ok=True)
    if not plan:
        pass
    elif getattr(backend, 'external', False):
        extract_external(backend, plan, project, rid, res, stats, extracted_names, targets)
    else:
        for e, target in plan:
            os.makedirs(os.path.dirname(target), mode=0o770, exist_ok=True)
            part = target + '.part-' + rid
            try:
                crc, size = 0, 0
                with backend.open(e) as src, open(part, 'wb') as out:
                    while True:
                        b = src.read(CHUNK)
                        if not b:
                            break
                        out.write(b); crc = zlib.crc32(b, crc); size += len(b)
                if size != e.size:
                    raise Problem('SIZE_MISMATCH', 'extracted %d bytes, archive says %d (truncated archive?)' % (size, e.size), e.name)
                if e.crc is not None and crc != e.crc:
                    raise Problem('CRC_MISMATCH', 'checksum does not match; the entry is corrupt', e.name)
                finish_file(part, target, e, res, stats); extracted_names.append(targets[e.name])
            except Problem as p:
                res.error(p.code, str(p), p.entry or e.name)
            except (zipfile.BadZipFile, EOFError, tarfile.TarError) as ex:
                res.error('ENTRY_CORRUPT', str(ex)[:200], e.name)
            except OSError as ex:
                res.error('WRITE_FAILED', '%s' % ex, e.name)
            finally:
                if os.path.exists(part):
                    os.unlink(part)
    receipt = write_receipt(project, rid, archive_path, args, dest, stats, extracted_names, res)
    res.d['extracted'] = {'files': stats['extracted'], 'bytes': stats['bytes'], 'unchanged': stats['unchanged'], 'sample': extracted_names[:50]}
    res.d['receipt'] = receipt
    res.d['summary'] = 'extracted %d file(s) (%.1f MiB) to %s; %d unchanged; %d error(s), %d warning(s)' % (
        stats['extracted'], stats['bytes'] / 2**20, os.path.relpath(dest, project), stats['unchanged'], len(res.d['errors']), len(res.d['warnings']))
    res.d['next_steps'] = ['Re-run the project import job so Godot imports the new files.'] if stats['extracted'] else []
    if not res.d['ok']:
        res.d['next_steps'].insert(0, 'Some entries failed (see errors). Do not treat the asset as complete; the archive may be corrupt or incomplete.')


def extract_external(backend, plan, project, rid, res, stats, extracted_names, targets):
    tmp_root = os.path.join(project, '.opencode', 'tmp')
    os.makedirs(tmp_root, mode=0o770, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix='extract-' + rid + '-', dir=tmp_root)
    try:
        rc, out = backend.extract([e for e, _ in plan], tmp)
        if rc not in (0, 1):
            tail = [l for l in out.splitlines() if l.strip()][-3:]
            res.error('EXTRACT_FAILED', 'the extractor exited with %d: %s' % (rc, ' | '.join(tail)[:300]))
        for line in out.splitlines():
            if line.startswith(('ERROR:', 'WARNING:')) and len(res.d['errors']) < 50:
                res.warn('EXTRACTOR_MESSAGE', line[:200])
        for e, target in plan:
            src = os.path.join(tmp, *e.raw.replace('\\', '/').split('/'))
            if os.path.islink(src) or not os.path.isfile(src):
                res.error('EXTRACT_FAILED' if not os.path.islink(src) else 'UNSAFE_ENTRY', 'entry was not produced as a regular file', e.name); continue
            if not os.path.realpath(src).startswith(os.path.realpath(tmp) + os.sep):
                res.error('UNSAFE_NAME', 'resolves outside the extraction folder', e.name); continue
            if os.path.getsize(src) != e.size:
                res.error('SIZE_MISMATCH', 'extracted %d bytes, archive says %d' % (os.path.getsize(src), e.size), e.name); continue
            if e.crc is not None and file_crc(src) != e.crc:
                res.error('CRC_MISMATCH', 'checksum does not match; the entry is corrupt', e.name); continue
            os.makedirs(os.path.dirname(target), mode=0o770, exist_ok=True)
            os.chmod(src, 0o660)
            os.replace(src, target)
            stats['extracted'] += 1; stats['bytes'] += e.size; extracted_names.append(targets[e.name])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def write_receipt(project, rid, archive_path, args, dest, stats, names, res):
    d = os.path.join(project, '.opencode', 'asset-extractions')
    try:
        os.makedirs(d, mode=0o770, exist_ok=True)
        path = os.path.join(d, rid + '.json')
        doc = {'schema': 1, 'id': rid, 'time': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'archive': archive_path,
               'archive_bytes': os.path.getsize(archive_path), 'dest': os.path.relpath(dest, project), 'selection': {'select': args.select, 'exclude': args.exclude,
               'prefix': args.prefix, 'ext': args.ext, 'strip': args.strip}, 'extracted': stats['extracted'], 'unchanged': stats['unchanged'],
               'ok': res.d['ok'], 'errors': res.d['errors'][:20], 'files': names[:2000], 'note': args.note or ''}
        tmp = path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(doc, f, indent=1)
        os.chmod(tmp, 0o660)
        os.replace(tmp, path)
        return os.path.relpath(path, project)
    except OSError as ex:
        res.warn('RECEIPT_FAILED', 'could not write the extraction receipt: %s' % ex)
        return None


# ---------------------------------------------------------------- driver and queue
def run(args, pol, rid=None, via=None):
    rid = rid or 'ar-%s-%s' % (time.strftime('%Y%m%d%H%M%S'), secrets.token_hex(3))
    res = Result(args.op)
    res.d['id'] = rid
    if via:
        res.d['via'] = via
    t0 = time.time()
    try:
        path = pol.archive_path(args.archive)
        res.d['archive'] = {'path': path, 'bytes': os.path.getsize(path)}
        fmt = detect_format(path)
        res.d['archive']['format'] = fmt
        if multipart_hint(path):
            res.warn('MULTIPART_ARCHIVE', 'this looks like one part of a multi-part archive; give the FIRST part and make sure every part is present')
        if via is None and needs_host(fmt):
            return submit_and_wait(args, pol, rid)
        backend = open_backend(path, fmt)
        if getattr(backend, 'external', False):
            for w in backend.warnings:
                res.warn('EXTRACTOR_MESSAGE', w[:200])
        entries = load_entries(backend, res, getattr(args, 'strip', 0) or 0, getattr(args, 'include_junk', False))
        if args.op == 'list':
            op_list(args, pol, res, backend, entries)
        elif args.op == 'inspect':
            op_inspect(args, pol, res, backend, entries)
        elif args.op == 'read':
            op_read(args, pol, res, backend, entries)
        elif args.op == 'extract':
            if not args.project:
                raise Problem('USAGE', '--project is required for extract')
            op_extract(args, pol, res, backend, entries, path, rid)
    except Problem as p:
        res.error(p.code, str(p), p.entry)
    except (OSError, tarfile.TarError, zipfile.BadZipFile, EOFError, subprocess.TimeoutExpired) as ex:
        res.error('IO_ERROR', '%s: %s' % (type(ex).__name__, str(ex)[:200]))
    if not res.d['summary']:
        res.d['summary'] = 'failed: ' + (res.d['errors'][0]['message'] if res.d['errors'] else 'unknown')
    res.d['seconds'] = round(time.time() - t0, 2)
    if res.d['errors'] and 'next_steps' not in res.d:
        res.d['next_steps'] = ['Report these errors to the owner; the archive may be corrupt, incomplete, password protected or unsafe.']
    return res.d


REQUEST_FIELDS = ('op', 'archive', 'project', 'dest', 'select', 'exclude', 'prefix', 'ext', 'strip', 'entry', 'max_bytes', 'base64', 'limit', 'dry_run',
                  'overwrite', 'partial_ok', 'force_large', 'max_files', 'include_junk', 'test', 'note')


def args_from_dict(d):
    a = argparse.Namespace(op=None, archive=None, project=None, dest=None, select=[], exclude=[], prefix=None, ext=None, strip=0, entry=None, max_bytes=None,
                           base64=False, limit=None, dry_run=False, overwrite=False, partial_ok=False, force_large=False, max_files=None, include_junk=False,
                           test=False, note=None)
    for k in REQUEST_FIELDS:
        if k in d:
            setattr(a, k, d[k])
    if a.op not in ('list', 'inspect', 'read', 'extract'):
        raise Problem('USAGE', 'bad op')
    for k in ('select', 'exclude'):
        if not isinstance(getattr(a, k), list) or not all(isinstance(x, str) for x in getattr(a, k)):
            raise Problem('USAGE', k + ' must be a list of strings')
    return a


def queue_dir_for(args, pol):
    if args.project:
        try:
            return os.path.join(pol.project_path(args.project), PROJECT_QUEUE)
        except Problem:
            pass
    return pol.global_queue


def submit_and_wait(args, pol, rid):
    qd = queue_dir_for(args, pol)
    os.makedirs(qd, mode=0o770, exist_ok=True)
    req = {'schema': 1, 'id': rid, 'submitted': time.time()}
    for k in REQUEST_FIELDS:
        req[k] = getattr(args, k, None)
    path = os.path.join(qd, rid + '.request.json')
    with open(path + '.tmp', 'w') as f:
        json.dump(req, f)
    os.replace(path + '.tmp', path)
    result = os.path.join(qd, rid + '.result.json')
    deadline = time.time() + (getattr(args, 'wait', 0) or 180)
    while time.time() < deadline:
        if os.path.exists(result):
            try:
                with open(result) as f:
                    return json.load(f)
            except (OSError, ValueError):
                pass
        time.sleep(1)
    return {'ok': False, 'op': args.op, 'id': rid, 'pending': True, 'request': path, 'errors': [], 'warnings': [],
            'summary': 'still running on the host worker; check later with: asset_archive.py status %s' % rid,
            'next_steps': ['asset_archive.py status ' + rid]}


def serve_once(pol, queues):
    done = 0
    for qd in queues:
        if not os.path.isdir(qd):
            continue
        for name in sorted(os.listdir(qd)):
            if not name.endswith('.request.json'):
                continue
            rid = name[:-len('.request.json')]
            req_path, res_path, lock = (os.path.join(qd, rid + s) for s in ('.request.json', '.result.json', '.lock'))
            if os.path.exists(res_path):
                continue
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o660)
                os.close(fd)
            except FileExistsError:
                if time.time() - os.path.getmtime(lock) > 6 * 3600:
                    os.unlink(lock)
                continue
            try:
                if os.path.getsize(req_path) > 65536:
                    raise Problem('USAGE', 'request too large')
                with open(req_path) as f:
                    req = json.load(f)
                args = args_from_dict(req)
                if not re.fullmatch(r'ar-[0-9]{14}-[0-9a-f]{6}', str(req.get('id', ''))) or req['id'] != rid:
                    raise Problem('USAGE', 'bad request id')
                if qd != pol.global_queue:  # project queue: the request may only act on its own project
                    own = os.path.realpath(os.path.join(qd, '..', '..'))
                    if args.op == 'extract' and (not args.project or pol.project_path(args.project) != own):
                        raise Problem('PROJECT_NOT_ALLOWED', 'a project queue request may only extract into its own project')
                out = run(args, pol, rid=rid, via='host-worker')
            except (Problem, OSError, ValueError) as ex:
                out = {'ok': False, 'op': 'unknown', 'id': rid, 'errors': [{'code': getattr(ex, 'code', 'BAD_REQUEST'), 'message': str(ex)[:300]}], 'warnings': [],
                       'summary': 'request rejected'}
            tmp = res_path + '.tmp'
            with open(tmp, 'w') as f:
                json.dump(out, f)
            os.chmod(tmp, 0o660)
            os.replace(tmp, res_path)
            try:
                os.unlink(lock)
            except OSError:
                pass
            done += 1
    return done


def project_queues(pol):
    root = pol.project_root
    out = [pol.global_queue]
    try:
        for cat in sorted(os.listdir(root)):
            cdir = os.path.join(root, cat)
            if os.path.isdir(cdir) and not os.path.islink(cdir):
                for proj in sorted(os.listdir(cdir)):
                    q = os.path.join(cdir, proj, PROJECT_QUEUE)
                    if os.path.isdir(q) and not os.path.islink(q):
                        out.append(q)
    except OSError:
        pass
    return out


def find_result(pol, rid):
    for qd in project_queues(pol):
        p = os.path.join(qd, rid + '.result.json')
        if os.path.exists(p):
            with open(p) as f:
                return json.load(f)
        if os.path.exists(os.path.join(qd, rid + '.request.json')):
            return {'ok': False, 'id': rid, 'pending': True, 'summary': 'request is queued or running on the host worker', 'errors': [], 'warnings': []}
    return {'ok': False, 'id': rid, 'errors': [{'code': 'REQUEST_NOT_FOUND', 'message': 'no request with that id'}], 'warnings': [], 'summary': 'unknown request id'}


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='op', required=True)

    def common(p, project=False):
        p.add_argument('archive')
        p.add_argument('--select', action='append', default=[], metavar='GLOB', help='keep entries matching this glob (repeatable; ** crosses folders)')
        p.add_argument('--exclude', action='append', default=[], metavar='GLOB')
        p.add_argument('--prefix', help='shorthand for --select PREFIX/**')
        p.add_argument('--ext', help='comma list of extensions, e.g. png,jpg,glb')
        p.add_argument('--include-junk', action='store_true', help='keep __MACOSX, .DS_Store, Thumbs.db')
        p.add_argument('--wait', type=int, default=180, help='seconds to wait for the host worker (7z/rar)')
    p = sub.add_parser('list'); common(p); p.add_argument('--limit', type=int)
    p = sub.add_parser('inspect'); common(p); p.add_argument('--test', action='store_true', help='read every entry and verify size/CRC')
    p = sub.add_parser('read'); common(p); p.add_argument('--entry', required=True); p.add_argument('--max-bytes', type=int); p.add_argument('--base64', action='store_true')
    p = sub.add_parser('extract'); common(p)
    p.add_argument('--project', required=True, help='project folder name or absolute path under /data/ai/projects/<category>/<name>')
    p.add_argument('--dest', help='folder inside the project (default Assets/<archive name>)')
    p.add_argument('--strip', type=int, default=0, help='drop this many leading folders from each entry path')
    p.add_argument('--dry-run', action='store_true'); p.add_argument('--overwrite', action='store_true')
    p.add_argument('--partial-ok', action='store_true', help='extract the clean entries even if others have errors')
    p.add_argument('--force-large', action='store_true', help='allow selections above the size/bomb limits (owner approved)')
    p.add_argument('--max-files', type=int); p.add_argument('--note')
    p = sub.add_parser('status'); p.add_argument('request_id')
    p = sub.add_parser('serve'); p.add_argument('--once', action='store_true'); p.add_argument('--interval', type=float, default=5)
    return ap


def main(argv=None):
    ap = build_parser()
    a = ap.parse_args(argv)
    pol = Policy()
    if a.op == 'serve':
        while True:
            serve_once(pol, project_queues(pol))
            if a.once:
                return 0
            time.sleep(a.interval)
    if a.op == 'status':
        out = find_result(pol, a.request_id)
    else:
        for k, v in (('base64', False), ('limit', None), ('test', False), ('max_bytes', None), ('entry', None), ('project', None), ('dest', None), ('strip', 0),
                     ('dry_run', False), ('overwrite', False), ('partial_ok', False), ('force_large', False), ('max_files', None), ('note', None)):
            if not hasattr(a, k):
                setattr(a, k, v)
        out = run(a, pol)
    print(json.dumps(out, indent=1))
    return 0 if out.get('ok') else 1


if __name__ == '__main__':
    sys.exit(main())
