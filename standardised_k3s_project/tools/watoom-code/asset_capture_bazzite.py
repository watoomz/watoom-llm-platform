#!/usr/bin/env python3
"""Operator-only declarative asset capture on the Bazzite worker (keeps the 4 GiB Blender capture off the homelab server).

Same manifest contract, 4 GiB cgroup, pinned Blender, trusted Blender-side script and output validation as asset_capture.py.
The source's folder (the .blend/.glb and its textures) plus the few absolute files the manifest or the .blend name are mirrored
to Bazzite at the SAME absolute paths, so the Blender-side script runs unchanged. It runs in rootless podman (toolkit image,
no network, read-only root, all capabilities dropped). Only the capture's output folder comes back, checked by the shared
asset_capture.check_outputs(). MP4 encoding runs on the Bazzite host afterwards (the image has no ffmpeg).

Exit 75 with status NOT_STARTED = nothing was launched (the dispatcher waits and retries); after the launch there is no
fallback and no replay.
"""
import argparse, hashlib, json, os, pathlib, re, shlex, shutil, subprocess, sys, tempfile, time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / 'ansible/roles/watoom-code/files/skills/watoom-fab-owned-assets/scripts/unreal-export'))
from asset_capture import CONFIG, check_outputs
from asset_capture_contract import manifest, sha, contained
from blender_bazzite import ready, NOT_STARTED, IMAGE_TAG, R_BLENDER, BLENDER, BLENDER_SHA
import bazzite as bz

CAP_UID = 1001           # the unprivileged capture user of the server unit: owner of the returned outputs
IMAGE_UID = 1009         # the toolkit image's user; keep-id maps the Bazzite worker user onto it
MEMORY_GIB = 4           # exactly 4 GiB: the Blender-side script verifies the cgroup limit
CPUS = 2
DEADLINE = 900
R_ROOT = 'watoom-capture'
R_REPO = R_ROOT + '/repo'
R_SHIM = R_ROOT + '/shim'
MAX_SYNC_BYTES = 6 * 1024 ** 3
MAX_SYNC_FILES = 60000
MAX_OUT_FILES = 400
MAX_OUT_BYTES = 2 * 1024 ** 3
IMAGE_EXT = r'png|jpg|jpeg|exr|hdr|tga|tif|tiff|webp|bmp|dds|gif'


def atomic(path, value):
    tmp = pathlib.Path(str(path) + '.tmp')
    tmp.write_text(json.dumps(value, indent=2))
    tmp.replace(path)


def tree_size(root):
    """(bytes, files) of regular files under root, links ignored."""
    total = count = 0
    for d, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [x for x in dirs if not os.path.islink(os.path.join(d, x))]
        for n in files:
            f = os.path.join(d, n)
            if os.path.islink(f):
                continue
            total += os.lstat(f).st_size
            count += 1
            if total > MAX_SYNC_BYTES or count > MAX_SYNC_FILES:
                return total, count
    return total, count


def absolute_strings(value):
    if isinstance(value, str):
        if value.startswith('/'):
            yield value
    elif isinstance(value, dict):
        for x in value.values():
            yield from absolute_strings(x)
    elif isinstance(value, list):
        for x in value:
            yield from absolute_strings(x)


def dependencies(v, roots):
    """Absolute files outside the source folder that the manifest or the .blend names (textures, clips); only under roots."""
    src = pathlib.Path(v['source'])
    found = set()
    for text in absolute_strings(v):
        found.add(text)
    if src.suffix.lower() == '.blend':
        try:
            blob = src.read_bytes()
            for m in re.finditer(rb'/[A-Za-z0-9_./ +@()-]{1,400}\.(?:%s)' % IMAGE_EXT.encode(), blob, re.I):
                found.add(m.group(0).decode('utf-8', 'ignore'))
        except OSError:
            pass
    out = []
    for text in sorted(found):
        p = pathlib.Path(text)
        try:
            if p.is_file() and not p.is_symlink() and p.resolve() == p and any(p.is_relative_to(r) for r in roots) and not p.is_relative_to(src.parent):
                out.append(p)
        except OSError:
            pass
    return out


def run(a):
    if os.geteuid() != 0:
        raise PermissionError('Operator only')
    cfg = json.loads(CONFIG.read_text())
    p = pathlib.Path(a.project)
    if str(p) not in cfg['projects'] or not p.is_dir() or p.resolve() != p:
        raise ValueError('Unapproved project')
    if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}', a.job):
        raise ValueError('Invalid job')
    ev = pathlib.Path(a.evidence)
    ev.mkdir(parents=True, exist_ok=False)
    result = {'status': 'FAIL', 'worker': 'bazzite', 'memory_limit': MEMORY_GIB * 1024 ** 3}

    def finish(code):
        if result.get('status') != 'PASS' and not result.get('failure_stage'):
            reason = str(result.get('error') or '').lower()
            if result.get('exit_code') == 124 or 'timed out' in reason or 'deadline' in reason:
                result.update(failure_stage='run', failure_code='timeout')
            elif result.get('exit_code') == 137 or 'out of memory' in reason or 'oom' in reason:
                result.update(failure_stage='run', failure_code='oom')
            elif 'source revision mismatch' in reason:
                result.update(failure_stage='request', failure_code='source_changed')
            elif 'pull_failed' in reason or 'pull failed' in reason:
                result.update(failure_stage='pull', failure_code='worker_error')
            elif 'read-only file system' in reason or 'could not write' in reason or 'script raised' in reason:
                result.update(failure_stage='run', failure_code='script_error')
            else:
                result.update(failure_stage='run', failure_code='worker_error')
        atomic(ev / 'result.json', result)
        os.chmod(ev / 'result.json', 0o644)
        print(json.dumps({k: result.get(k) for k in ('status', 'worker', 'error', 'exit_code')}))
        raise SystemExit(code)

    # ---- request errors: a normal FAIL receipt, never NOT_STARTED ----
    try:
        roots = cfg['source_roots'] + [str(p)]
        mf = contained(p / '.opencode/capture-jobs' / a.job / 'request.json', [str(p)])
        if mf.stat().st_size > 65536:
            raise ValueError('Oversize manifest')
        raw = mf.read_bytes()
        if a.expected_manifest_sha256 and hashlib.sha256(raw).hexdigest() != a.expected_manifest_sha256:
            raise ValueError('Manifest changed after native authorization')
        v = manifest(json.loads(raw), roots)
        if sha(v['source']) != v['source_sha256']:
            raise ValueError('Source revision mismatch')
        if cfg['blender_sha256'] != BLENDER_SHA or sha(BLENDER) != BLENDER_SHA:
            raise ValueError('Unqualified Blender binary')
        out = p / '.opencode/captures' / a.job
        if out.exists():
            raise ValueError('Output already exists; inspect it, never replay')
        if out.parent.exists() and out.parent.resolve() != out.parent:
            raise ValueError('Indirect output')
        src_dir = pathlib.Path(v['source']).parent
        size, count = tree_size(src_dir)
        if size > MAX_SYNC_BYTES or count > MAX_SYNC_FILES:
            raise ValueError('Source folder %s is larger than %d GiB or %d files; put the asset in its own folder' % (src_dir, MAX_SYNC_BYTES >> 30, MAX_SYNC_FILES))
        extra = dependencies(v, roots)
        if sum(f.stat().st_size for f in extra) > MAX_SYNC_BYTES:
            raise ValueError('Referenced files exceed the sync budget')
    except (ValueError, OSError, KeyError) as e:
        result['error'] = str(e)[:500]
        result.update(failure_stage='request', failure_code='unknown')
        finish(1)
    result.update(source=v['source'], source_sha256=v['source_sha256'], manifest_sha256=hashlib.sha256(raw).hexdigest(),
                  runner_sha256=sha(__file__), worker_sha256=sha(HERE / 'asset_capture_blender.py'), output=str(out))

    unit = 'watoom-capture-bz-' + hashlib.sha256((str(out) + str(time.time_ns())).encode()).hexdigest()[:16]
    result['unit'] = unit
    r_job = R_ROOT + '/jobs/' + unit
    tree = r_job + '/tree'
    held = None

    def not_started(reason):
        if held:
            bz.release(held)
        shutil.rmtree(ev, ignore_errors=True)  # nothing ran: leave no evidence that would block the retry
        text = str(reason); lower = text.lower()
        code = 'unreachable' if '255' in lower or 'ssh' in lower and ('timeout' in lower or 'timed out' in lower) else 'not_staged' if 'not staged' in lower or 'missing' in lower else 'worker_error'
        safe = 'Bazzite access command failed (%s).' % code if text.startswith("Command '[") else text[:300]
        print(json.dumps({'status': 'NOT_STARTED', 'worker': 'bazzite', 'reason': safe, 'failure_stage': 'stage', 'failure_code': code}))
        raise SystemExit(NOT_STARTED)

    # ---- preparation: any failure here is NOT_STARTED ----
    try:
        if not bz.runtime_ready():
            raise RuntimeError('Bazzite toolkit image not staged (bazzite.py stage-runtime)')
        if not ready():
            raise RuntimeError('Bazzite Blender not staged (blender_bazzite.py stage)')
        ram, disk = bz.free()
        if ram < (MEMORY_GIB + 2) * 1024 ** 3:
            raise RuntimeError('Bazzite has %.1f GiB free RAM' % (ram / 1024 ** 3))
        if disk < size + 20 * 1024 ** 3:
            raise RuntimeError('Bazzite has %.1f GiB free disk' % (disk / 1024 ** 3))
        held = bz.inhibit(unit, DEADLINE + 1800, 'Asset capture ' + a.job)
        home = bz.sh('printf %s "$HOME"', timeout=60, check=True).stdout.strip()
        bz.sh('mkdir -p ~/%s ~/%s/tools/watoom-code ~/%s/tools/ts4-animation ~/%s' % (tree, R_REPO, R_REPO, R_SHIM), timeout=60, check=True)
        # trusted code: the Blender-side script and its helpers, laid out as in the repository
        for sub in ('watoom-code', 'ts4-animation'):
            r = bz.push(str(HERE.parent / sub) + '/', '%s/tools/%s/' % (R_REPO, sub),
                        ['--delete', '--prune-empty-dirs', '--include=*/', '--include=*.py', '--exclude=*', '--exclude=__pycache__'], timeout=300, attempts=3)
            if r.returncode:
                raise RuntimeError('code sync failed: ' + r.stderr[-300:])
        # the image has no ffmpeg: this stub lets the Blender script finish; the real encode runs on the host afterwards
        bz.sh("printf '#!/bin/sh\\nexit 0\\n' > ~/%s/ffmpeg && chmod 0755 ~/%s/ffmpeg" % (R_SHIM, R_SHIM), timeout=60, check=True)
        # data: mirrored at the same absolute paths; --relative recreates /data/... under the tree root
        for item in [src_dir, *extra]:
            r = bz.push(str(item), tree + '/', ['--relative', '--no-links', *(['--delete'] if item == src_dir else [])], timeout=1800, attempts=5)
            if r.returncode:
                raise RuntimeError('data sync failed: ' + r.stderr[-300:])
        remote_source = home + '/' + tree + v['source']
        got = bz.sh('sha256sum ' + shlex.quote(remote_source), timeout=900, check=True).stdout.split()[0]
        if got != v['source_sha256']:
            raise RuntimeError('Source hash mismatch on Bazzite')
        if sha(v['source']) != v['source_sha256']:
            raise RuntimeError('Live source changed during sync')
        plan = {'manifest': v, 'source_roots': roots, 'ffmpeg': '/shim/ffmpeg'}
        plan_file = ev / 'plan.json'
        plan_file.write_text(json.dumps(plan, indent=2))
        bz.sh('mkdir -p ' + shlex.quote(home + '/' + tree + str(out)), timeout=60, check=True)
        r = bz.push(str(plan_file), tree + str(out) + '/plan.json', timeout=120, attempts=3)
        if r.returncode:
            raise RuntimeError('plan sync failed: ' + r.stderr[-300:])
        tops = sorted({pathlib.PurePosixPath(str(x)).parts[1] for x in [src_dir, out, *extra]})
        mounts = []
        for t in tops:
            mounts += ['-v', '%s/%s/%s:/%s:ro,z' % (home, tree, t, t)]
        out_in = str(out)
        podman = ['podman', 'run', '--rm', '--name', unit, '--network', 'none', '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                  '--userns', 'keep-id:uid=%d,gid=%d' % (IMAGE_UID, IMAGE_UID), '--memory', '%dg' % MEMORY_GIB, '--memory-swap', '%dg' % MEMORY_GIB, '--cpus', str(CPUS),
                  '--pids-limit', '128', '--timeout', str(DEADLINE), '--tmpfs', '/tmp:rw,size=2g,mode=1777',
                  '-e', 'HOME=/tmp', '-e', 'XDG_CACHE_HOME=/tmp', '-e', 'OMP_NUM_THREADS=2', '-e', 'OPENBLAS_NUM_THREADS=2',
                  '-v', '%s/%s:/blender:ro' % (home, R_BLENDER), '-v', '%s/%s:/repo:ro,z' % (home, R_REPO), '-v', '%s/%s:/shim:ro,z' % (home, R_SHIM),
                  *mounts, '-v', '%s/%s%s:%s:z' % (home, tree, out_in, out_in),
                  '--entrypoint', '/blender/' + BLENDER.name, IMAGE_TAG,
                  '--background', '--factory-startup', '--disable-autoexec', '--python-exit-code', '1',
                  '--python', '/repo/tools/watoom-code/asset_capture_blender.py', '--', out_in + '/plan.json']
        job_dir = home + '/' + r_job
        script = '%s > %s 2>&1; echo $? > %s' % (' '.join(shlex.quote(x) for x in podman), shlex.quote(job_dir + '/worker.log'), shlex.quote(job_dir + '/exit_code'))
        launch = ['systemd-run', '--user', '--unit=' + unit, '--collect', '-p', 'MemoryMax=%dG' % (MEMORY_GIB + 1), '-p', 'CPUQuota=%d%%' % (CPUS * 100), '-p', 'Nice=10',
                  '-p', 'RuntimeMaxSec=%d' % (DEADLINE + 60), '-p', 'MemorySwapMax=0', '-p', 'TimeoutStopSec=10', '-p', 'KillMode=control-group',
                  '/bin/bash', '-c', script]
        atomic(ev / 'prepared.json', {'unit': unit, 'worker': 'bazzite', 'source': v['source'], 'sync_bytes': size, 'extra_files': [str(x) for x in extra]})
    except SystemExit:
        raise
    except Exception as e:
        not_started(e)

    # ---- launch: from here on there is no fallback ----
    started = time.time()
    try:
        r = bz.sh(' '.join(shlex.quote(x) for x in launch), timeout=120)
        launch_state = 'ok' if r.returncode == 0 else 'error: ' + r.stderr[-300:]
    except Exception as e:
        launch_state = 'uncertain: ' + str(e)[:300]
    code = None
    while time.time() - started < DEADLINE + 120:
        try:
            r = bz.sh('cat ~/%s/exit_code 2>/dev/null; systemctl --user is-active %s.service' % (r_job, unit), timeout=60)
            words = r.stdout.split()
            if words and words[0].lstrip('-').isdigit():
                code = int(words[0])
                break
            if words and words[-1] in ('inactive', 'failed'):
                break
        except Exception:
            pass
        time.sleep(10)
    result['launch'] = launch_state
    result['elapsed_sec'] = round(time.time() - started, 1)

    try:
        bz.pull(r_job + '/worker.log', str(ev / 'worker.log'), timeout=300, attempts=2)
    except Exception:
        pass
    # MP4: the Blender script wrote the frames and ran the stub; encode here with the host's ffmpeg
    remote_out = tree + str(out)
    if code == 0 and v.get('output_format') == 'mp4':
        try:
            fps = int(v.get('fps', 24))
            enc = ['ffmpeg', '-nostdin', '-v', 'error', '-framerate', str(fps), '-i', 'frame-%04d.png', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', 'capture.mp4']
            e = bz.sh('cd ~/%s && %s' % (remote_out, ' '.join(shlex.quote(x) for x in enc)), timeout=240)
            if e.returncode:
                code = 1
                result['error'] = 'MP4 encoding failed: ' + e.stderr[-300:]
        except Exception as e:
            code = 1
            result['error'] = 'MP4 encoding failed: ' + str(e)[:300]

    # ---- bring back only the output folder, checked: flat regular files, bounded ----
    staging = pathlib.Path(tempfile.mkdtemp(prefix='bz-capture-out-', dir=str(ev)))
    pull_error = None
    try:
        r = bz.pull(remote_out + '/', str(staging) + '/', ['--no-links', '--no-specials', '--no-devices', '--exclude=plan.json'], timeout=1200, attempts=3)
        if r.returncode:
            pull_error = 'OUTPUT_PULL_FAILED: ' + r.stderr[-300:]
        found = list(staging.rglob('*'))
        if any(x.is_symlink() for x in found) or sum(1 for x in found if x.is_file()) > MAX_OUT_FILES or sum(x.stat().st_size for x in found if x.is_file()) > MAX_OUT_BYTES:
            pull_error = 'OUTPUT_REJECTED: links or more than %d files / %d MiB' % (MAX_OUT_FILES, MAX_OUT_BYTES >> 20)
    except Exception as e:
        pull_error = 'OUTPUT_PULL_FAILED: ' + str(e)[:300]
    try:
        if pull_error:
            result['error'] = pull_error
        else:
            out.parent.mkdir(parents=True, exist_ok=True)
            if out.parent.resolve() != out.parent:
                raise ValueError('Indirect output')
            out.mkdir()
            os.chown(out, CAP_UID, CAP_UID)
            subprocess.run(['rsync', '-a', '--no-links', '--chown=%d:%d' % (CAP_UID, CAP_UID), str(staging) + '/', str(out) + '/'], check=True, timeout=900)
            (out / 'plan.json').write_text(json.dumps(plan, indent=2))
            os.chmod(out / 'plan.json', 0o644)
            check_outputs(v, out, result, code if code is not None else 1)
    except Exception as e:
        result.update(status='FAIL', error=str(e)[:500])
    shutil.rmtree(staging, ignore_errors=True)
    result.setdefault('exit_code', code)
    try:
        bz.sh('rm -rf ~/%s' % r_job, timeout=180)
    finally:
        bz.release(held)
    finish(0 if result['status'] in ('PASS', 'CAPTURED_VISUAL_REVIEW_PENDING', 'PREPARED_REVIEW_PENDING') else 1)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--project', required=True)
    ap.add_argument('--job', required=True)
    ap.add_argument('--evidence', required=True)
    ap.add_argument('--i-approve', action='store_true')
    ap.add_argument('--expected-manifest-sha256')
    ap.add_argument('--config', type=pathlib.Path, default=CONFIG)
    v = ap.parse_args()
    if not v.i_approve:
        ap.error('Explicit operator approval required')
    run(v)
