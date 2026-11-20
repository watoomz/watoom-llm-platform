#!/usr/bin/env python3
"""Operator-side typed watoom-godot-game job for a native game-worker request; the root dispatcher is the only caller.

Runs the fixed list of skill commands from godot_game_spec.py on the Bazzite worker (never the homelab server) in rootless podman: no network, read-only root,
no GPU (Mesa llvmpipe, gl_compatibility styles only), the pinned Godot at /godot, the installed skill and its sibling watoom-texture-layering read-only under /skills, a staged COPY of the game
project at /project (spec project_dir under .opencode/tmp/, never the live source). Results come back to .opencode/godot-game-out/<job>/ (app-readable,
files over 100 MB skipped and listed). Writes <evidence>/result.json; exit 0 on PASS. A start is never replayed after the launch.
Prerequisite on Bazzite (probed first, fails before anything runs when missing): the Xvfb capture image must have python3 with numpy and Pillow (it does, 2026-11-17).
"""
import argparse, hashlib, json, os, pathlib, shlex, subprocess, sys, time
import godot_game_spec
from game_validation import GODOT, GODOT_SHA

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / 'ansible/roles/watoom-code/files/skills/watoom-fab-owned-assets/scripts/unreal-export'))
import bazzite as bz  # noqa: E402

R_GODOT = 'watoom-godot/bin/godot-' + GODOT_SHA[:12]
WORKER = 1009
MIN_FREE_GIB, RESERVE_GIB, CPUS = 6, 2, 4
MAX_FILE = '100m'
NEEDED_SKILLS = ('watoom-godot-game', 'watoom-texture-layering')   # gg_terrain.py loads layer_masks.py from the sibling skill next to it
SKIP_SKILL = ['--exclude=__pycache__/', '--exclude=test_*.py', '--exclude=fixtures/', '--exclude=*.pyc']
SKIP_PULL = ['--exclude=.godot/', '--exclude=gg_data/jobs/', '--exclude=gg_data/export/stage/', '--exclude=gg_data/selftest*/']
# gg_data holds cross-step continuity (style.resolved.json, world/, census.json, scatter/) that a chained from_project
# job needs to see from the job before it; only the scratch/job-history subdirs are excluded, same as SKIP_PULL.
SKIP_FROM_PROJECT_GG_DATA = ['--exclude=/gg_data/jobs/', '--exclude=/gg_data/export/stage/', '--exclude=/gg_data/selftest*/']



def check_staging_path(project, staging):
    """The staging folder and every existing folder above it up to the project are real directories, and it resolves inside .opencode/tmp.
    The app user can write there, so root re-checks right before it creates, copies into and chowns it (a swapped-in link would otherwise redirect root)."""
    project, staging = pathlib.Path(project), pathlib.Path(staging)
    base = project / '.opencode' / 'tmp'
    for q in [staging, *staging.parents]:
        if q == project: break
        if q.is_symlink(): raise ValueError('a link sits on the staging path: ' + str(q.relative_to(project)))
    if base.is_symlink(): raise ValueError('.opencode/tmp must be a real folder')
    resolved = staging.resolve()
    if base.resolve() not in (resolved, *resolved.parents): raise ValueError('the staging folder resolves outside .opencode/tmp')

def atomic(path, value):
    tmp = path.with_name('.' + path.name + '.tmp'); tmp.write_text(json.dumps(value, indent=2)); os.chmod(tmp, 0o644); os.replace(tmp, path)


def tree_hash(root):
    """sha256 over (relative path, content hash) of every file under root; refuses links."""
    rows = []
    for p in sorted(root.rglob('*')):
        if p.is_symlink(): raise ValueError('Unsafe staging entry (link): ' + str(p))
        if p.is_file(): rows.append([str(p.relative_to(root)), hashlib.sha256(p.read_bytes()).hexdigest()])
    return hashlib.sha256(json.dumps(rows, separators=(',', ':')).encode()).hexdigest()


def podman_cmd(name, tag, home, r_job, r_project, r_skill, memory_gib, deadline):
    """Pure: the container command. Source mounts are read-only except /project and /job."""
    env = {'HOME': '/job/home', 'XDG_CACHE_HOME': '/job/cache', 'USER': 'watoom-worker', 'LOGNAME': 'watoom-worker', 'GG_JOB_DIR': '/job', 'GG_SKILL_DIR': '/skills/watoom-godot-game',
           'GG_PROJECT_DIR': '/project', 'GG_GODOT': '/godot', 'LIBGL_ALWAYS_SOFTWARE': '1', 'GALLIUM_DRIVER': 'llvmpipe', 'LP_NUM_THREADS': '4',
           '__EGL_VENDOR_LIBRARY_FILENAMES': '/usr/share/glvnd/egl_vendor.d/50_mesa.json', '__GLX_VENDOR_LIBRARY_NAME': 'mesa'}
    return ['podman', 'run', '--rm', '--name', name, '--network', 'none', '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
            '--userns', 'keep-id:uid=%d,gid=%d' % (WORKER, WORKER), '--memory', '%dg' % memory_gib, '--memory-swap', '%dg' % memory_gib, '--cpus', str(CPUS),
            '--pids-limit', '1024', '--timeout', str(deadline), '--tmpfs', '/tmp:rw,size=1g,mode=1777',
            *sum([['-e', '%s=%s' % kv] for kv in env.items()], []),
            '-v', '%s/%s:/godot:ro,z' % (home, R_GODOT), '-v', '%s/%s:/skills:ro,z' % (home, r_skill), '-v', '%s/%s:/project:z' % (home, r_project), '-v', '%s/%s:/job:z' % (home, r_job),
            '--workdir', '/project', '--entrypoint', 'xvfb-run', tag, '-e', '/job/xvfb.log', '-a', '-s', '-screen 0 1280x800x24',
            'python3', '/job/godot_game_driver.py', str(deadline - 60)]


def failure_reason(code, driver, pulled):
    """Pure: one actionable sentence for a failed run."""
    if code is None: return 'timeout: the container did not finish; raise deadline_sec (max 1800) or run fewer steps'
    if driver is None: return 'worker exit %s and no driver.json: see native.log' % code
    if driver.get('timed_out'): return 'a step exceeded the deadline; raise deadline_sec (max 1800) or run fewer steps'
    st = driver.get('selftest') or {}
    if st.get('exit') != 0: return 'the verify-loop selftest failed (exit %s): the loop cannot see, nothing after it can be trusted; read the step tail in result.json or the full log at logs/00-selftest.log in this job\'s output directory' % st.get('exit')
    if driver.get('failed_at'):
        s = driver['steps'][driver['failed_at'] - 1]
        return 'step %d (%s %s) exited %s; read its tail in result.json or the full log at logs/%02d-%s-%s.log in this job\'s output directory' % (s['i'], s['script'], s['sub'], s['exit'], s['i'], s['script'][:-3], s['sub'])
    if code != 0: return 'worker exit %s' % code
    if not pulled: return 'the results could not be copied back from Bazzite'
    return 'unknown'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--project', type=pathlib.Path, required=True); p.add_argument('--evidence', type=pathlib.Path, required=True)
    p.add_argument('--i-approve', action='store_true'); p.add_argument('--godot-game-job', required=True)
    a = p.parse_args()
    if os.geteuid() != 0: raise PermissionError('Operator only')
    project = a.project.resolve(strict=True)
    if not a.i_approve or a.project.is_symlink() or project.parent != pathlib.Path('/data/ai/projects/games'):  # the job works on its own scratch copy, so the live project need not be a Godot one
        raise ValueError('Approved existing game project required')
    a.evidence.mkdir(parents=True, exist_ok=False); os.chmod(a.evidence, 0o750)
    receipt = {'status': 'FAIL', 'job': a.godot_game_job, 'worker': 'bazzite', 'scope': 'Typed watoom-godot-game steps on a staged copy, software GL (no GPU); visual and gameplay acceptance stay separate.'}
    held = None

    def fail(reason, **extra):
        if held: bz.release(held)
        receipt.update(failure_reason=str(reason)[:500], **extra)
        atomic(a.evidence / 'result.json', receipt)
        print(json.dumps({k: receipt.get(k) for k in ('status', 'failure_reason')})); raise SystemExit(1)

    try:
        spec = godot_game_spec.load(project, a.godot_game_job)
        staging = project / spec['directory']
        early_out = project / '.opencode' / 'godot-game-out' / a.godot_game_job
        if early_out.exists() or early_out.is_symlink(): raise ValueError('.opencode/godot-game-out/' + a.godot_game_job + ' already exists; use a new job name (checked before the run, so no Bazzite time is spent)')
        check_staging_path(project, staging)   # root creates, copies into and chowns this folder: no link may sit on its path
        if spec.get('create_directory') and not staging.exists():   # an init job named a folder that is not there yet (the model cannot create empty folders)
            st = (project / '.opencode').stat()
            for d in reversed([staging, *[q for q in staging.parents if q != project and not q.exists()]]):
                d.mkdir(mode=0o2770); os.chown(d, st.st_uid, st.st_gid); os.chmod(d, 0o2770)
        if spec.get('from_project'):   # the worker copies the live project itself: the model's tools cannot stage 40+ runtime files by hand
            r = subprocess.run(['rsync', '-a', '--no-links', '--max-size=%dm' % godot_game_spec.COPY_MAX_MB, '--exclude=/.git/', '--exclude=/.godot/', '--exclude=/.opencode/', *SKIP_FROM_PROJECT_GG_DATA, '--exclude=/addons/gg/.import_cache/', str(project) + '/', str(staging) + '/'], capture_output=True, text=True, timeout=300)
            if r.returncode: raise RuntimeError('copying the live project failed: ' + r.stderr[-300:])
            st = (project / '.opencode').stat()
            check_staging_path(project, staging)
            for q in [staging, *staging.rglob('*')]: os.chown(q, st.st_uid, st.st_gid, follow_symlinks=False)
        before = tree_hash(staging)
        with GODOT.open('rb') as f:
            if hashlib.file_digest(f, 'sha256').hexdigest() != GODOT_SHA: raise ValueError('Pinned Godot input changed')
        staged = bz.runtime_ready()
        if not staged: raise RuntimeError('Bazzite toolkit not staged (bazzite.py stage-runtime)')
        tag = bz.capture_image_tag(staged[1]['local_tag'])
        if not bz.capture_image_ready(staged[1]['local_tag']): raise RuntimeError('Bazzite capture image missing (Xvfb + Mesa EGL): run bazzite.py build-capture-image')
        probe = bz.sh("podman run --rm --network none --entrypoint python3 %s -c 'import numpy, PIL; print(\"GG-PY-OK\")'" % shlex.quote(tag), timeout=120)
        if 'GG-PY-OK' not in probe.stdout: raise RuntimeError('Bazzite capture image lacks python3 numpy and Pillow (required by the godot-game scripts): extend the capture image first')
        ram, disk = bz.free()
        need = (spec['memory_gib'] + RESERVE_GIB) * 1024 ** 3
        if ram < need: raise RuntimeError('Bazzite has %.1f GiB free RAM, needs %d' % (ram / 1024 ** 3, spec['memory_gib'] + RESERVE_GIB))
        if disk < MIN_FREE_GIB * 1024 ** 3: raise RuntimeError('Bazzite has %.1f GiB free disk' % (disk / 1024 ** 3))
        name = 'watoom-godotgame-' + hashlib.sha256((str(project) + a.godot_game_job).encode()).hexdigest()[:12]
        held = bz.inhibit(name, spec['deadline_sec'] + 1800, 'Godot game job ' + name)
        home = bz.sh('printf %s "$HOME"', timeout=60, check=True).stdout.strip()
        r_job = 'watoom-godot/jobs/' + name; r_project = 'watoom-godot/gg-projects/' + name
        def skill_files(name):
            root = godot_game_spec.SKILL.parent / name
            return [x for x in sorted(root.rglob('*')) if x.is_file() and '__pycache__' not in x.parts and not x.name.startswith('test_') and 'fixtures' not in x.parts and x.suffix != '.pyc']
        skill_sha = hashlib.sha256(json.dumps([[n, str(x.relative_to(godot_game_spec.SKILL.parent)), hashlib.sha256(x.read_bytes()).hexdigest()] for n in NEEDED_SKILLS for x in skill_files(n)]).encode()).hexdigest()
        r_skill = 'watoom-godot/gg-skill/' + skill_sha[:12]
        bz.sh('rm -rf ~/%s ~/%s && mkdir -p ~/watoom-godot/bin ~/%s/home ~/%s/cache ~/%s ~/%s' % (r_job, r_project, r_job, r_job, r_project, r_skill), timeout=120, check=True)
        r = bz.sh('sha256sum ~/%s 2>/dev/null' % R_GODOT, timeout=120)
        if not r.stdout.startswith(GODOT_SHA):
            r = bz.push(str(GODOT), R_GODOT, timeout=900)
            if r.returncode or not bz.sh('sha256sum ~/%s' % R_GODOT, timeout=120, check=True).stdout.startswith(GODOT_SHA): raise RuntimeError('Godot push failed or hash mismatch on Bazzite')
            bz.sh('chmod 0755 ~/%s' % R_GODOT, timeout=60, check=True)
        for local, remote, extra in ([(str(godot_game_spec.SKILL.parent / n) + '/', r_skill + '/' + n + '/', ['--delete', *SKIP_SKILL]) for n in NEEDED_SKILLS] + [(str(staging) + '/', r_project + '/', ['--delete'])]):
            r = bz.push(local, remote, extra, timeout=900, attempts=3)
            if r.returncode: raise RuntimeError('sync failed: ' + r.stderr[-300:])
        (a.evidence / 'steps.json').write_text(json.dumps(spec['steps']))
        for f, dst in ((a.evidence / 'steps.json', r_job + '/steps.json'), (HERE / 'godot_game_driver.py', r_job + '/godot_game_driver.py')):
            r = bz.push(str(f), dst, timeout=120, attempts=3)
            if r.returncode: raise RuntimeError('job file sync failed: ' + r.stderr[-300:])
        if tree_hash(staging) != before: raise RuntimeError('The staged project changed during sync; submit a new job')
        podman = podman_cmd(name, tag, home, r_job, r_project, r_skill, spec['memory_gib'], spec['deadline_sec'])
        job_dir = home + '/' + r_job
        script = '%s > %s 2>&1; echo $? > %s' % (' '.join(shlex.quote(x) for x in podman), shlex.quote(job_dir + '/native.log'), shlex.quote(job_dir + '/exit_code'))
        launch = ' '.join(shlex.quote(x) for x in ['systemd-run', '--user', '--unit=' + name, '--collect', '-p', 'MemoryMax=%dG' % (spec['memory_gib'] + 1), '-p', 'CPUQuota=%d%%' % (CPUS * 100),
                                                   '-p', 'Nice=10', '-p', 'MemorySwapMax=0', '-p', 'TimeoutStopSec=10', '-p', 'KillMode=control-group', '-p', 'RuntimeMaxSec=%d' % (spec['deadline_sec'] + 60), '/bin/bash', '-c', script])
        atomic(a.evidence / 'prepared.json', {'unit': name, 'project': str(project), 'staging': spec['directory'], 'staging_sha256': before, 'skill_sha256': skill_sha, 'godot_sha256': GODOT_SHA,
                                               'steps': len(spec['steps']), 'memory_limit': '%dGiB' % spec['memory_gib'], 'deadline_sec': spec['deadline_sec'], 'spec_sha256': spec['spec_sha256']})
    except Exception as e:
        fail(e, failure_stage='stage')

    extra = {}
    try:
        r = bz.sh(launch, timeout=120); extra['launch'] = 'ok' if r.returncode == 0 else 'error: ' + r.stderr[-300:]
    except Exception as e:
        extra['launch'] = 'uncertain: ' + str(e)[:300]
    t0 = time.time(); deadline = t0 + spec['deadline_sec'] + 180; code = None
    while time.time() < deadline:
        try:
            lines = bz.sh('cat ~/%s/exit_code 2>/dev/null; systemctl --user is-active %s.service' % (r_job, name), timeout=60).stdout.split()
            if lines and lines[0].lstrip('-').isdigit(): code = int(lines[0]); break
            if lines and lines[-1] in ('inactive', 'failed'): break
        except Exception:
            pass
        time.sleep(15)
    elapsed = round(time.time() - t0, 1)
    out_local = a.evidence / 'output'; out_local.mkdir(exist_ok=True)
    pulled = bz.pull(r_project + '/', str(out_local / 'project') + '/', ['--prune-empty-dirs', '--max-size=' + MAX_FILE, *SKIP_PULL], timeout=1800, attempts=3).returncode == 0
    bz.pull(r_job + '/', str(a.evidence / 'job') + '/', ['--exclude=home/', '--exclude=cache/', '--exclude=selftest/'], timeout=600, attempts=2)
    bz.release(held)
    bz.sh('rm -rf ~/%s ~/%s' % (r_job, r_project), timeout=300)
    driver = None
    dp = a.evidence / 'job' / 'driver.json'
    if dp.is_file():
        try: driver = json.loads(dp.read_text())
        except (OSError, ValueError): driver = None
    try: unchanged = tree_hash(staging) == before
    except (OSError, ValueError): unchanged = False
    status = 'PASS' if code == 0 and driver and not driver.get('failed_at') and pulled and unchanged else 'FAIL'
    receipt.update(status=status, failure_reason=None if status == 'PASS' else ('the staged project changed during the run; submit a new job' if code == 0 and not unchanged else failure_reason(code, driver, pulled)),
                   unit=name, exit=code, elapsed_sec=elapsed, memory_limit='%dGiB' % spec['memory_gib'], deadline_sec=spec['deadline_sec'], staging_unchanged=unchanged,
                   selftest=(driver or {}).get('selftest'), steps=(driver or {}).get('steps'), gpu_used=False, **extra)
    app = project / '.opencode' / 'godot-game-out' / a.godot_game_job
    try:
        st = (project / '.opencode').stat()
        parent = app.parent; parent.mkdir(mode=0o2770, exist_ok=True)
        if parent.is_symlink() or app.exists() or app.is_symlink(): raise ValueError('.opencode/godot-game-out/' + a.godot_game_job + ' already exists; use a new job name')
        app.mkdir(mode=0o2770)
        subprocess.run(['rsync', '-a', '--no-links', str(out_local / 'project') + '/', str(app / 'project') + '/'], check=True, timeout=900) if (out_local / 'project').is_dir() else None
        subprocess.run(['rsync', '-a', '--no-links', str(a.evidence / 'job' / 'logs') + '/', str(app / 'logs') + '/'], check=True, timeout=300) if (a.evidence / 'job' / 'logs').is_dir() else None
        files = [x for x in sorted(app.rglob('*')) if x.is_file() and not x.is_symlink()]
        for x in [parent, app, *app.rglob('*')]:
            if not x.is_symlink(): os.chown(x, st.st_uid, WORKER, follow_symlinks=False)
        receipt.update(output_directory='.opencode/godot-game-out/' + a.godot_game_job, outputs=[{'file': str(x.relative_to(project)), 'bytes': x.stat().st_size} for x in files][:300], outputs_total=len(files))
        atomic(app / 'result.json', receipt); os.chown(app / 'result.json', st.st_uid, WORKER)
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        receipt.update(status='FAIL', failure_reason=('results not published: ' + str(e))[:400])
    atomic(a.evidence / 'result.json', receipt)
    print(json.dumps({k: receipt.get(k) for k in ('status', 'failure_reason', 'output_directory')}))
    raise SystemExit(0 if receipt['status'] == 'PASS' else 1)


if __name__ == '__main__':
    main()
