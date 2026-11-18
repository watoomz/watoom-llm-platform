#!/usr/bin/env python3
"""Operator-owned, isolated CPU Godot regression against a stable project snapshot."""
import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import time

GODOT = pathlib.Path('/data/ai/projects/llm/watoom-code/prompt-builder-20261020/toolchain/godot')
GODOT_SHA = '8d106cbe6144c2dc7e881d61d2429c1a8a76e6b22ef48bd5e48dcf934953f71e'


def atomic(path, value):
    temporary = path.with_suffix('.tmp')
    fd = os.open(temporary, os.O_CREAT | os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(value, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporary, path)


MANIFEST_CACHE_ROOT = pathlib.Path('/data/ai/private/manifest-cache')
# A file touched within this many seconds of "now" is always rehashed: size+mtime alone cannot tell apart two
# distinct writes landing in the same tick, and this is a source-change security check, not just a cache.
MANIFEST_CACHE_MIN_AGE_SEC = 2


def _manifest_cache_path(project):
    return MANIFEST_CACHE_ROOT / (hashlib.sha256(str(pathlib.Path(project).resolve()).encode()).hexdigest()[:32] + '.json')


def manifest(project):
    """Full-content sha256 of every regular file under project (same return shape as before: {relpath: sha256}).
    Backed by a (size, mtime_ns) cache kept OUTSIDE project itself -- project may be a frozen read-only
    snapshot, so this never writes into the directory it is hashing. Caching is a pure perf optimization: on
    any doubt (missing/corrupt cache, a file younger than MANIFEST_CACHE_MIN_AGE_SEC, a cache write failure)
    it falls back to reading and hashing, never to trusting an unverified result."""
    cache_file = _manifest_cache_path(project)
    try:
        cache = json.loads(cache_file.read_text())
    except (OSError, ValueError):
        cache = {}
    now = time.time()
    result = {}
    seen = set()
    changed = False
    for root, dirs, files in os.walk(project, followlinks=False):
        dirs[:] = [x for x in dirs if x not in {'.godot', '.opencode', '.git', 'magpie-final'}]
        for name in files:
            path = pathlib.Path(root) / name
            if path.is_symlink():
                raise ValueError('Snapshot requires regular contained source files: ' + str(path))
            rel = str(path.relative_to(project))
            seen.add(rel)
            st = path.stat()
            cached = cache.get(rel)
            if (cached and cached['size'] == st.st_size and cached['mtime_ns'] == st.st_mtime_ns
                    and now - st.st_mtime >= MANIFEST_CACHE_MIN_AGE_SEC):
                result[rel] = cached['sha256']
                continue
            with path.open('rb') as f:
                digest = hashlib.file_digest(f, 'sha256').hexdigest()
            result[rel] = digest
            if cached != {'size': st.st_size, 'mtime_ns': st.st_mtime_ns, 'sha256': digest}:
                changed = True
            cache[rel] = {'size': st.st_size, 'mtime_ns': st.st_mtime_ns, 'sha256': digest}
    stale = set(cache) - seen
    if stale:
        changed = True
        for k in stale:
            del cache[k]
    if changed:
        try:
            MANIFEST_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
            atomic(cache_file, cache)
        except OSError:
            pass
    return result


def finalize(directory):
    state = json.loads((directory / 'prepared.json').read_text())
    unit = state['unit']
    if not re.fullmatch(r'watoom-godot-check-[0-9]+', unit):
        raise ValueError('Owned unit required')
    log = directory / 'godot.log'
    text = subprocess.run(['journalctl', '-u', unit, '--no-pager', '-o', 'cat'], capture_output=True, text=True).stdout[-2000000:]
    log.write_text(text)
    matches = re.findall(r'^passed=(\d+) failed=(\d+) total=(\d+)$', text, re.M)
    summary = tuple(map(int, matches[-1])) if matches else None
    runtime_errors = len(godot_errors(text))
    success = os.environ.get('SERVICE_RESULT') == 'success' and os.environ.get('EXIT_STATUS') == '0'
    peak = subprocess.run(['systemctl', 'show', unit, '-p', 'MemoryPeak', '--value'], capture_output=True, text=True).stdout.strip()
    result = {'status': 'PASS' if success and summary and summary[1] == 0 and summary[0] == summary[2] and summary[2] > 0 and runtime_errors == 0 else 'FAIL',
              'runtime_error_count': runtime_errors, 'service_result': os.environ.get('SERVICE_RESULT'), 'exit_status': os.environ.get('EXIT_STATUS'),
              'summary': {'passed': summary[0], 'failed': summary[1], 'total': summary[2]} if summary else None,
              'failure_reason': None if success else 'worker-exit',
              'memory_limit': state['memory_limit'], 'memory_peak_bytes': peak, 'source_manifest': 'source-manifest.json',
              'snapshot': str(directory / 'snapshot'), 'log': str(log), 'original_project_untouched': True}
    if result['status'] != 'PASS' and success:
        result['failure_reason'] = regression_failure_reason(summary, runtime_errors)
    if result['status'] != 'PASS':
        if str(os.environ.get('EXIT_STATUS')) == '137':
            result.update(failure_stage='run', failure_code='oom')
        elif runtime_errors:
            result.update(failure_stage='run', failure_code='script_error')
        else:
            result.update(failure_stage='run', failure_code='worker_error')
    atomic(directory / 'result.json', result)


SUMMARY_LINE = 'passed=N failed=N total=N'
ERROR_PREFIXES = ('ERROR:', 'SCRIPT ERROR:', 'SHADER ERROR:')


def godot_errors(text):
    """Godot error lines, each with the file:line from its following "at:" line when Godot printed one.
    SHADER ERROR carries the real cause of a bare "ERROR: Shader compilation failed." (e.g. an unknown identifier at
    res://shader.gdshader:39), so it is kept too. Distinct, in log order."""
    lines = text.splitlines();found = []
    for i, line in enumerate(lines):
        if not line.startswith(ERROR_PREFIXES): continue
        where = lines[i + 1].strip() if i + 1 < len(lines) and lines[i + 1].strip().startswith('at:') else ''
        found.append(line + (' [' + where + ']' if where and where not in line else ''))
    return list(dict.fromkeys(found))


def godot_output_tail(text, limit=40, maxlen=400):
    """Trailing non-empty lines of the merged stdout+stderr log, so GDScript print()
    and other debug output reach the receipt — not only error-pattern lines. The
    worker already captures both streams to the log; errors[] surfaces only the
    error lines, which left print()/debug output invisible to the reading agent."""
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    return [l[:maxlen] for l in lines[-limit:]]


def regression_failure_reason(summary, runtime_errors):
    """Name why a run that exited cleanly is still FAIL, so the app sees an actionable cause."""
    if summary is None:
        return 'test runner printed no final "' + SUMMARY_LINE + '" line, so no tests could be counted; print it as the last line'
    if summary[1]:
        return '%d of %d tests failed' % (summary[1], summary[2])
    if summary[2] == 0 or summary[0] != summary[2]:
        return 'summary line is inconsistent: passed=%d failed=%d total=%d' % summary
    if runtime_errors:
        return '%d runtime error lines (ERROR, SCRIPT ERROR or SHADER ERROR) in the log; see runtime_error_examples' % runtime_errors
    return None


HINTS = (
    (re.compile(r"res://(\.\./)+|[/\\]Users[/\\]|\b[A-Z]:[\\/](?!/)"),
     'An FBX/glTF references textures on the author\'s machine. Do not byte-patch it: run a blender job with script '
     'skill:blender-export-pipelines/scripts/fbx_relink_to_glb.py (--input <fbx or folder> --textures <folders> --output {out}) and use the GLBs.'),
    (re.compile(r'Unrecognized UID'),
     'Scenes reference uid:// values that no longer exist (assets were copied or re-imported with new .import/.uid files). '
     'In each [ext_resource] line named by the error, remove the uid="uid://..." attribute and keep path=, or restore the original .import/.uid files.'),
    (re.compile(r'Resource file not found: res://\S+\.(fbx|glb|gltf|blend|obj)', re.I),
     'A scene loads a model file that is not in the project at that path: copy the file there or fix the [ext_resource] path.'),
    (re.compile(r'SHADER ERROR'),
     'A shader failed to compile; the SHADER ERROR line gives the identifier and file:line. Check the built-in name exists in that '
     'shader stage for Godot 4 (e.g. WORLD_POSITION is not a vertex built-in; use (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz).'),
    (re.compile(r'Parse Error|Parser Error'),
     'A .tscn/.tres/.gd file failed to parse; fix the file and line named in the error before re-running.'),
)


def godot_hints(errors):
    """Known-cause guidance for recurring Godot errors, so the agent fixes the cause instead of retrying."""
    text = '\n'.join(errors)
    return [hint for pattern, hint in HINTS if pattern.search(text)]


def import_failure_reason(errors, changes, live, applied):
    """Why an import that exited cleanly is still FAIL, in the order the agent should fix it."""
    if changes: return 'the import changed project source files, so its caches were not applied; see source_changes_by_import'
    if not live: return 'project source changed while the import ran; request a new import once edits are done'
    if errors: return '%d Godot errors during import; see errors (missing or external resource paths are the usual cause)' % len(errors)
    if not applied: return 'import caches could not be copied back'
    return None


def publish_receipt(project, directory, result, log_name="godot.log", receipt_folder="operator-godot"):
    """Expose a concise receipt to coding agents without opening private operator reports."""
    target = project / '.opencode' / 'validation' / receipt_folder
    if not target.resolve().is_relative_to(project):
        raise ValueError('Receipt destination must remain inside the project')
    destination = target / (directory.name + '.json')
    result['app_receipt'] = str(destination)
    public = dict(result)
    public['raw_log_access'] = 'operator-only; this receipt is app-readable'
    text = (directory / log_name).read_text(errors='replace')
    public['failed_tests'] = [x for x in text.splitlines() if x.startswith('[FAIL]')][:100]
    public['runtime_error_examples'] = godot_errors(text)[:20]
    # the bridge status the coordinator reads first carries a bounded copy, so the cause is visible without opening files
    result['runtime_error_examples'] = [x[:300] for x in public['runtime_error_examples'][:10]]
    result['hints'] = public['hints'] = godot_hints(godot_errors(text))
    # Walk opened directory descriptors without following project-controlled symlinks.
    parent = os.open(project, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in ('.opencode', 'validation', receipt_folder):
            try:
                os.mkdir(component, 0o755, dir_fd=parent)
            except FileExistsError:
                pass
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = child
        os.fchown(parent, 1009, 1009)
        os.fchmod(parent, 0o755)
        name = directory.name + '.json'
        temporary = '.' + name + '.' + str(time.time_ns()) + '.tmp'
        fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        with os.fdopen(fd, 'w') as stream:
            json.dump(public, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
            os.fchown(stream.fileno(), 1009, 1009)
            os.fchmod(stream.fileno(), 0o644)
        os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
    finally:
        os.close(parent)
    return destination


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--project', type=pathlib.Path)
    p.add_argument('--evidence', type=pathlib.Path)
    p.add_argument('--i-approve', action='store_true')
    p.add_argument('--memory-gib', type=int, choices=[3, 4], default=3)
    p.add_argument('--finalize', type=pathlib.Path)
    p.add_argument('--resume-prepared', action='store_true')
    a = p.parse_args()
    if os.geteuid() != 0:
        raise PermissionError('Trusted operator required')
    if a.finalize:
        return finalize(a.finalize)
    print('RISK: runs one CPU-only Godot snapshot test in a separate '+str(a.memory_gib)+'GiB worker, two CPU cores, no swap/GPU/network and a 300s deadline. App/inference and live game files are preserved.', flush=True)
    if not a.i_approve or not a.project or not a.evidence:
        raise PermissionError('--project --evidence --i-approve required')
    project = a.project.resolve(strict=True)
    if a.project.is_symlink() or not project.is_relative_to('/data/ai/projects/games') or not (project / 'scripts/test_runner.gd').is_file():
        raise ValueError('Existing canonical game/test project required')
    available = int(next(x.split()[1] for x in pathlib.Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'))) * 1024
    if available < (a.memory_gib + 2) * 1024 ** 3:
        raise RuntimeError(str(a.memory_gib)+'GiB worker plus 2GiB host reserve unavailable; wait rather than altering inference')
    with GODOT.open('rb') as f:
        if hashlib.file_digest(f, 'sha256').hexdigest() != GODOT_SHA:
            raise ValueError('Pinned Godot input changed')
    directory = a.evidence.resolve()
    before = manifest(project)
    snapshot = directory / 'snapshot'
    if a.resume_prepared:
        if (directory / 'result.json').exists() or (directory / 'godot.log').exists():
            raise RuntimeError('Only a prepared snapshot with no executed Godot/log may resume')
        if json.loads((directory / 'source-manifest.json').read_text()) != before:
            raise RuntimeError('Source changed since the prepared snapshot')
    else:
        directory.mkdir(parents=True, exist_ok=False, mode=0o750)
        os.chown(directory, 0, 1009)
        atomic(directory / 'source-manifest.json', before)
        subprocess.run(['cp', '--archive', '--reflink=auto', '--', str(project), str(snapshot)], check=True, timeout=120)
    if manifest(project) != before or manifest(snapshot) != before:
        raise RuntimeError('Live source changed during snapshot; retain it and retry later')
    for folder in [snapshot, directory / 'home', directory / 'cache']:
        folder.mkdir(exist_ok=True)
        os.chown(folder, 1009, 1009)
    unit = 'watoom-godot-check-' + str(time.time_ns())
    atomic(directory / 'prepared.json', {'unit': unit, 'project': str(project), 'source_files': len(before), 'godot_sha256': GODOT_SHA, 'memory_limit': str(a.memory_gib)+'GiB'})
    command = ['systemd-run', '--quiet', '--wait', '--collect', '--unit=' + unit,
               '--property=MemoryMax='+str(a.memory_gib)+'G', '--property=MemorySwapMax=0',
               '--property=CPUQuota=200%', '--property=CPUWeight=10', '--property=Nice=10',
               '--property=TasksMax=128', '--property=RuntimeMaxSec=300', '--property=TimeoutStopSec=10',
               '--property=KillMode=control-group', '--property=NoNewPrivileges=yes',
               '--property=PrivateNetwork=yes', '--property=PrivateDevices=yes', '--property=PrivateTmp=yes',
               '--property=ProtectSystem=strict', '--property=ProtectHome=yes',
               '--property=BindPaths=' + str(directory) + ':/tmp/watoom-game-validation',
               '--property=ReadWritePaths=' + str(directory),
               '--property=LimitFSIZE=128M',
               '--property=WorkingDirectory=/tmp/watoom-game-validation/snapshot',
               '--property=ExecStopPost=+/usr/bin/python3 ' + str(pathlib.Path(__file__).resolve()) + ' --finalize ' + str(directory),
               '--setenv=USER=watoom-worker', '--setenv=LOGNAME=watoom-worker',
               '--setenv=HOME=/tmp/watoom-game-validation/home', '--setenv=XDG_CACHE_HOME=/tmp/watoom-game-validation/cache',
               '--', '/usr/sbin/setpriv', '--reuid=1009', '--regid=1009', '--clear-groups', '--bounding-set=-all', '--', str(GODOT), '--headless', '--path', '/tmp/watoom-game-validation/snapshot', '--script', 'res://scripts/test_runner.gd']
    with (directory / 'godot.log').open('wb') as log:
        os.chmod(directory / 'godot.log', 0o600)
        subprocess.run(command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, check=False, timeout=330)
    if not (directory / 'result.json').exists():
        raise RuntimeError('Worker/finalizer did not produce a receipt; inspect the owned unit journal before any retry')
    result = json.loads((directory / 'result.json').read_text())
    result['live_source_still_matches_snapshot'] = manifest(project) == before
    if not result['live_source_still_matches_snapshot']:
        result.update(failure_stage='reconcile', failure_code='source_changed')
    publish_receipt(project, directory, result)
    atomic(directory / 'result.json', result)
    print(json.dumps(result))
    if result['status'] != 'PASS':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
