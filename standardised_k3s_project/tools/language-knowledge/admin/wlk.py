#!/usr/bin/env python3
"""Offline card administration. All managed paths stay within root.

Snapshots are immutable and content addressed (16 hex digits). Mutations are
serialized with flock; files and symlinks publish with os.replace. `previous`
is a JSON target string (null before the first activation). Rollback exchanges
active and previous, including the original symlink spelling. Each pointer
replacement is atomic; the two replacements are not a crash-atomic transaction.
"""
import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

REQUIRED = set('id product language version kind symbol signature summary params returns aliases constraints examples source license trust_tier status'.split())
# godot/blender (extract/) have a fixed, known kind vocabulary and exact semver versions. Every other product is
# a manuals/<product> card (see manuals/registry.json, the same list sync_manual.py's own products draw from):
# each manual picks its own free-form kind/version taxonomy, so only OFFICIAL_KINDS/the semver regex are enforced
# for official products -- a manual card's kind/version just needs to be the non-empty string already checked above.
OFFICIAL_PRODUCTS = {'godot', 'blender'}
OFFICIAL_KINDS = set('api_class api_method api_property api_signal api_constant api_enum cli_flag operator '
                      'rna_struct rna_property import_option'.split())
MANUAL_PRODUCTS = set(json.loads((Path(__file__).resolve().parent.parent / 'manuals' / 'registry.json').read_text())['products'])
PRODUCTS = OFFICIAL_PRODUCTS | MANUAL_PRODUCTS
STATUSES = {'verified', 'source_checked', 'unverified', 'quarantined'}
# official cards are always first-party vendor data; manual cards are sourced from vendor docs or this repo's own
# internal operational notes (never 'official' -- that tier is reserved for the extractors' direct API dumps).
OFFICIAL_TRUST_TIERS = {'official'}
MANUAL_TRUST_TIERS = {'vendor_doc', 'internal_doc'}


def validate_bytes(data):
    cards, errors, seen = [], [], set()
    for number, line in enumerate(data.decode('utf-8').splitlines(), 1):
        if not line.strip():
            continue
        try:
            c = json.loads(line)
            if not isinstance(c, dict) or REQUIRED - c.keys():
                raise ValueError('missing required keys or non-object card')
            for key in ('id', 'product', 'language', 'version', 'kind', 'symbol', 'signature', 'license'):
                if not isinstance(c[key], str) or not c[key].strip():
                    raise ValueError('invalid ' + key)
            if c['product'] not in PRODUCTS:
                raise ValueError('invalid product/kind')
            official = c['product'] in OFFICIAL_PRODUCTS
            if official and c['kind'] not in OFFICIAL_KINDS:
                raise ValueError('invalid product/kind')
            if official and not re.fullmatch(r'\d+\.\d+\.\d+(?:[-+][\w.-]+)?', c['version']):
                raise ValueError('version must be exact')
            if c['trust_tier'] not in (OFFICIAL_TRUST_TIERS if official else MANUAL_TRUST_TIERS):
                raise ValueError('invalid status/trust_tier')
            if c['id'] != f"{c['product']}.{c['symbol']}@{c['version']}":
                raise ValueError('id does not match product/symbol/version')
            # A bare '/' is a legitimate part of some symbols (e.g. Godot bus-parameter paths like
            # "voice/1/cutoff_hz"); id is never used to build a filesystem path, so only '..' and '\' -- an
            # actual traversal/escape attempt -- are rejected here.
            if '\\' in c['id'] or '..' in c['id']:
                raise ValueError('path traversal in card id')
            if c['id'] in seen:
                raise ValueError('duplicate id')
            seen.add(c['id'])
            if c['status'] not in STATUSES:
                raise ValueError('invalid status/trust_tier')
            if not isinstance(c['summary'], str) or len(c['summary']) > 300:
                raise ValueError('invalid summary')
            for key in ('params', 'aliases', 'constraints', 'examples'):
                if not isinstance(c[key], list):
                    raise ValueError('invalid ' + key)
            if not all(isinstance(x, str) for x in c['aliases']):
                raise ValueError('invalid aliases')
            # official cards carry the extractors' full shape (type/default/doc always present); manual cards
            # (e.g. ansible's module-examples) only ever record the parameter name.
            required_param_keys = {'name', 'type', 'default', 'doc'} if official else {'name'}
            for p in c['params']:
                if not isinstance(p, dict) or not required_param_keys <= p.keys():
                    raise ValueError('invalid parameter')
                if not all(isinstance(p[k], str) for k in required_param_keys if k != 'default'):
                    raise ValueError('invalid parameter type')
            if c['returns'] is not None and not isinstance(c['returns'], str):
                raise ValueError('invalid returns')
            if not isinstance(c['source'], dict) or not all(isinstance(c['source'].get(k), str) and c['source'][k].strip() for k in ('uri', 'revision', 'span')):
                raise ValueError('invalid source')
            if 'deprecated' in c and type(c['deprecated']) is not bool:
                raise ValueError('invalid deprecated')
            cards.append(c)
        except (ValueError, TypeError) as exc:
            errors.append(f'line {number}: {exc}')
    if not cards and not errors:
        errors.append('empty corpus')
    return cards, {'valid': not errors, 'cards': len(cards),
                   'healthy': sum(c['status'] in {'verified', 'source_checked'} for c in cards),
                   'quarantined': sum(c['status'] == 'quarantined' for c in cards),
                   'products': dict(sorted(Counter(c['product'] for c in cards).items())),
                   'kinds': dict(sorted(Counter(c['kind'] for c in cards).items())), 'errors': errors}


def checked(data):
    cards, report = validate_bytes(data)
    if not report['valid']:
        raise ValueError('; '.join(report['errors']))
    return cards, report


def input_bytes(path):
    path = Path(path).absolute()
    if path.resolve() != path or path.is_symlink():
        raise ValueError('symlink input refused')
    return path.read_bytes()


def safe(root, relative):
    path = root / relative
    try:
        path.resolve().relative_to(root)
    except (ValueError, RuntimeError):
        raise ValueError('path escapes root') from None
    # Managed files/directories are never aliases, even aliases within root.
    current = root
    for part in Path(relative).parts:
        if part == '..':
            raise ValueError('path traversal')
        current /= part
        if current.is_symlink():
            raise ValueError('symlink in managed path')
    return path


@contextmanager
def locked(root):
    root = Path(root).absolute()
    if root.is_symlink() or root.resolve() != root:
        raise ValueError('root must not contain symlinks')
    root.mkdir(parents=True, exist_ok=True)
    path = safe(root, '.wlk.lock')
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield root


def atomic(path, data=None, target=None):
    fd, name = tempfile.mkstemp(prefix='.wlk-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            if data is not None:
                out.write(data)
            out.flush()
            os.fsync(out.fileno())
        if target is not None:
            os.unlink(name)
            os.symlink(target, name)
        os.replace(name, path)
    finally:
        if os.path.lexists(name):
            os.unlink(name)


def json_bytes(value):
    return (json.dumps(value, sort_keys=True) + '\n').encode()


def snapshot_id(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{16}', value):
        raise ValueError('invalid snapshot id')
    return value


def inspect_snapshot(root, sid):
    directory = safe(root, 'snapshots/' + snapshot_id(sid))
    data = safe(root, f'snapshots/{sid}/cards.jsonl').read_bytes()
    manifest = json.loads(safe(root, f'snapshots/{sid}/manifest.json').read_text())
    _, report = checked(data)
    digest = hashlib.sha256(data).hexdigest()
    if digest[:16] != sid or manifest.get('sha256') != digest or manifest.get('cards') != report['cards'] or manifest.get('products') != report['products']:
        raise ValueError('snapshot integrity mismatch')
    return directory, manifest


def snapshot(cards_path, root):
    data = input_bytes(cards_path)
    _, report = checked(data)
    digest = hashlib.sha256(data).hexdigest()
    sid = digest[:16]
    with locked(root) as root:
        snapshots = safe(root, 'snapshots')
        snapshots.mkdir(exist_ok=True)
        destination = safe(root, 'snapshots/' + sid)
        if destination.exists():
            _, manifest = inspect_snapshot(root, sid)
            if manifest['sha256'] != digest:
                raise ValueError('snapshot prefix collision')
            return sid
        staging = Path(tempfile.mkdtemp(prefix='.build-', dir=snapshots))
        try:
            atomic(staging / 'cards.jsonl', data)
            atomic(staging / 'manifest.json', json_bytes({'sha256': digest, 'cards': report['cards'], 'products': report['products'], 'created': datetime.now(timezone.utc).isoformat()}))
            os.rename(staging, destination)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    return sid


def target_id(root, target):
    if not isinstance(target, str) or '..' in Path(target).parts:
        raise ValueError('invalid pointer target')
    path = Path(target) if Path(target).is_absolute() else root / target
    try:
        relative = path.relative_to(root)
    except ValueError:
        raise ValueError('pointer escapes root') from None
    if len(relative.parts) != 3 or relative.parts[0] != 'snapshots' or relative.parts[2] != 'cards.jsonl':
        raise ValueError('pointer must name snapshot cards')
    sid = snapshot_id(relative.parts[1])
    inspect_snapshot(root, sid)
    return sid


def pointers(root):
    active = root / 'cards.jsonl'
    if active.is_symlink():
        current = os.readlink(active)
        target_id(root, current)
    elif active.exists():
        raise ValueError('active cards must be a symlink')
    else:
        current = None
    previous_path = safe(root, 'previous')
    previous = json.loads(previous_path.read_text()) if previous_path.exists() else None
    if previous is not None:
        target_id(root, previous)
    return current, previous


def switch(root, target, current):
    previous_path = safe(root, 'previous')
    old = previous_path.read_bytes() if previous_path.exists() else None
    atomic(previous_path, json_bytes(current))
    try:
        if target is None:
            (root / 'cards.jsonl').unlink(missing_ok=True)
        else:
            atomic(root / 'cards.jsonl', target=target)
    except BaseException:
        if old is None:
            previous_path.unlink()
        else:
            atomic(previous_path, old)
        raise


def activate(sid, root):
    with locked(root) as root:
        inspect_snapshot(root, sid)
        current, _ = pointers(root)
        target = f'snapshots/{sid}/cards.jsonl'
        if current is not None and target_id(root, current) == sid:
            return
        switch(root, target, current)


def rollback(root):
    with locked(root) as root:
        current, previous = pointers(root)
        if not safe(root, 'previous').exists():
            raise ValueError('no previous activation')
        switch(root, previous, current)


def inventory(root, keep=None, apply=False):
    if keep is not None and keep < 0:
        raise ValueError('keep must be non-negative')
    with locked(root) as root:
        current, previous = pointers(root)
        protected = {target_id(root, t) for t in (current, previous) if t is not None}
        snapshots = safe(root, 'snapshots')
        rows = []
        for entry in sorted(snapshots.iterdir()) if snapshots.exists() else []:
            if entry.name.startswith('.build-'):
                continue
            _, manifest = inspect_snapshot(root, entry.name)
            rows.append(dict(manifest, id=entry.name, active=current is not None and target_id(root, current) == entry.name, previous=previous is not None and target_id(root, previous) == entry.name))
        rows.sort(key=lambda row: (row['created'], row['id']), reverse=True)
        retained = {row['id'] for row in rows[:keep]} if keep is not None else set()
        for row in rows:
            row['delete'] = keep is not None and row['id'] not in protected | retained
            if row['delete'] and apply:
                shutil.rmtree(safe(root, 'snapshots/' + row['id']))
        return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('validate').add_argument('cards')
    snap = commands.add_parser('snapshot')
    snap.add_argument('--cards', required=True)
    snap.add_argument('--root', required=True)
    act = commands.add_parser('activate')
    act.add_argument('snapshot_id')
    for name in ('rollback', 'list', 'gc'):
        sub = commands.add_parser(name)
        sub.add_argument('--root', required=True)
        if name == 'gc':
            sub.add_argument('--keep', required=True, type=int)
            sub.add_argument('--apply', action='store_true')
    act.add_argument('--root', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'validate':
            _, result = validate_bytes(input_bytes(args.cards))
            print(json.dumps(result, sort_keys=True))
            return 0 if result['valid'] else 1
        if args.command == 'snapshot':
            result = {'id': snapshot(args.cards, args.root)}
        elif args.command == 'activate':
            activate(args.snapshot_id, args.root)
            result = {'active': args.snapshot_id}
        elif args.command == 'rollback':
            rollback(args.root)
            result = {'rolled_back': True}
        else:
            result = inventory(args.root, getattr(args, 'keep', None), getattr(args, 'apply', False))
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f'wlk: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
