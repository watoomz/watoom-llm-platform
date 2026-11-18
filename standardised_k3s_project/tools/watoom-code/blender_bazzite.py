#!/usr/bin/env python3
"""Operator-only headless Blender job on the Bazzite worker (keeps Blender off the homelab server and its model).

Same request contract, limits and receipts as game_blender.py (the pinned Blender 'server-cpu' profile: 2 threads, the
requested memory_gib cgroup, no network, project read-only, .opencode/blender-out/<job>/ the only writable folder).
The project (without .opencode/.git) is mirrored to Bazzite and verified file by file against the source manifest; the
pinned Blender runs in rootless podman (toolkit image, no network, read-only root, all capabilities dropped) inside a bounded
user unit while a root-owned sleep inhibitor is held. Only the job's output folder comes back.

  blender_bazzite.py stage                       one-time: copy the pinned Blender to Bazzite and mark it ready
  blender_bazzite.py --project P --evidence E --blender-job J --i-approve    run one job (the dispatcher's call)

Exit 75 with status NOT_STARTED = nothing was launched (the dispatcher queues and retries); after the launch there is no
fallback and no replay.
"""
import argparse, hashlib, json, os, pathlib, shlex, shutil, subprocess, sys, tempfile, time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / 'ansible/roles/watoom-code/files/skills/watoom-fab-owned-assets/scripts/unreal-export'))
import blender_job_spec
from game_blender import PROFILE, BLENDER, BLENDER_SHA, WORKER, BOOT, diagnose, atomic, is_oom
from game_validation import manifest
from game_bazzite import remote_manifest, EXCLUDE_SYNC
import bazzite as bz

NOT_STARTED = 75
CPUS = 2  # the qualified server-cpu profile uses 2 threads; identical behaviour on both workers
R_ROOT = 'watoom-blender'
VERSION = '.'.join(map(str, PROFILE['version']))
R_BLENDER = R_ROOT + '/' + VERSION                      # holds the whole pinned distribution folder
R_READY = R_ROOT + '/' + VERSION + '.ready.json'
R_SKILLS = R_ROOT + '/skills'
BLENDER_DIR = BLENDER.parent
MAX_OUT_FILES = 5000
MAX_OUT_BYTES = 1024 ** 3
MAX_INPUT_BYTES = 8 * 1024 ** 2
IMAGE_TAG = 'localhost/watoom-toolkit:latest'


def ready():
    """The staged-Blender marker if Bazzite holds exactly the pinned build, else None."""
    r = bz.require_reachable(bz.sh('cat ~/%s 2>/dev/null' % R_READY, timeout=60))
    try:
        doc = json.loads(r.stdout)
    except ValueError:
        return None
    return doc if doc.get('sha256') == BLENDER_SHA and doc.get('version') == VERSION else None


def stage():
    """Copy the pinned Blender distribution to Bazzite, verify its executable, label it for containers, mark it ready."""
    if sha256_of(BLENDER) != BLENDER_SHA:
        raise SystemExit('pinned Blender changed; operator requalification required')
    held = bz.inhibit('watoom-blender-stage', 3 * 3600, 'Staging Blender from the homelab')
    try:
        bz.sh('mkdir -p ~/%s' % R_BLENDER, timeout=60, check=True)
        r = bz.push(str(BLENDER_DIR) + '/', R_BLENDER + '/', ['--delete'], timeout=3 * 3600, attempts=40)
        if r.returncode:
            raise SystemExit('Blender push failed: ' + r.stderr[-500:])
        got = bz.sh('sha256sum ~/%s/%s' % (R_BLENDER, BLENDER.name), timeout=900, check=True).stdout.split()[0]
        if got != BLENDER_SHA:
            raise SystemExit('Blender hash mismatch on Bazzite')
        # label once so every run can mount it read-only without a recursive relabel
        bz.sh('chcon -R -t container_file_t ~/%s' % R_BLENDER, timeout=900, check=True)
        doc = {'version': VERSION, 'sha256': BLENDER_SHA, 'binary': R_BLENDER + '/' + BLENDER.name}
        bz.sh("printf '%%s\\n' %s > ~/%s" % (shlex.quote(json.dumps(doc)), R_READY), timeout=60, check=True)
        print(json.dumps(doc))
    finally:
        bz.release(held)


def failure_reason(pull_error, oom, timed_out, mem, deadline, tb, result, code):
    if pull_error:
        return pull_error
    if oom:
        return 'memory limit %dGiB exceeded; raise memory_gib (max 6) or reduce the scene' % mem
    if timed_out:
        return 'deadline %ds exceeded; raise deadline_sec (max 900) or split the job' % deadline
    if tb:
        return 'script raised: ' + tb[-1][:300]
    if isinstance(result, dict) and result.get('error'):
        return 'script reported: ' + str(result['error'])[:300]
    return 'Blender exited %s; see errors and log_tail' % code


def sha256_of(path):
    with open(path, 'rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def run(a):
    if os.geteuid() != 0:
        raise PermissionError('Operator only')
    project = a.project.resolve(strict=True)
    if not a.i_approve or a.project.is_symlink() or project.parent != pathlib.Path('/data/ai/projects/games'):
        raise ValueError('Approved existing game project required')
    directory = a.evidence.resolve()
    directory.mkdir(parents=True, exist_ok=False, mode=0o750)
    os.chown(directory, 0, WORKER)
    receipt = {'status': 'FAIL', 'job': a.blender_job, 'engine': 'Blender ' + VERSION, 'worker': 'bazzite',
               'scope': 'Headless Blender script run; visual, rig and engine acceptance stay separate.'}

    def finish(code):
        if receipt.get('status') != 'PASS' and not receipt.get('failure_stage'):
            reason = str(receipt.get('failure_reason') or '').lower()
            if 'pull_failed' in reason or 'output_rejected' in reason:
                receipt.update(failure_stage='pull', failure_code='worker_error')
            elif 'memory limit' in reason or 'out of memory' in reason:
                receipt.update(failure_stage='run', failure_code='oom')
            elif 'deadline' in reason or receipt.get('timed_out'):
                receipt.update(failure_stage='run', failure_code='timeout')
            elif receipt.get('live_source_still_matches_snapshot') is False:
                receipt.update(failure_stage='reconcile', failure_code='source_changed')
            elif 'script raised' in reason or 'script reported' in reason:
                receipt.update(failure_stage='run', failure_code='script_error')
            elif 'failure_reason' not in receipt:
                receipt.update(failure_stage='request', failure_code='unknown')
            else:
                receipt.update(failure_stage='run', failure_code='worker_error')
        atomic(directory / 'result.json', receipt)
        print(json.dumps({k: receipt.get(k) for k in ('status', 'worker', 'failure_reason', 'exit', 'elapsed_sec')}))
        raise SystemExit(code)

    # ---- request errors are the agent's to fix: a normal FAIL receipt, never NOT_STARTED ----
    try:
        spec = blender_job_spec.load(project, a.blender_job)
        if sha256_of(BLENDER) != BLENDER_SHA:
            raise ValueError('pinned Blender changed; operator requalification required')
        dot = project / '.opencode'
        st = dot.stat()
        parent = dot / 'blender-out'
        out = parent / a.blender_job
        if out.exists() or out.is_symlink():
            raise ValueError('.opencode/blender-out/' + a.blender_job + ' already exists; use a new job name')
        if parent.exists() and (parent.is_symlink() or parent.resolve() != parent):
            raise ValueError('.opencode/blender-out must be a real folder')
    except (ValueError, OSError) as e:
        receipt['failure_reason'] = str(e)[:500]
        receipt.update(failure_stage='request', failure_code='unknown')
        finish(1)
    receipt.update(blend=str(spec['blend'].relative_to(project)) if spec['blend'] else None, script=spec['script_name'],
                   script_sha256=spec['script_sha256'], spec_sha256=spec['spec_sha256'],
                   memory_limit=str(spec['memory_gib']) + 'GiB', deadline_sec=spec['deadline_sec'])

    mem, deadline = spec['memory_gib'], spec['deadline_sec']
    before = manifest(project)
    atomic(directory / 'source-manifest.json', before)
    unit = 'watoom-blender-bz-' + str(time.time_ns())
    r_project = R_ROOT + '/projects/' + project.name
    r_job = R_ROOT + '/jobs/' + unit
    held = None

    def not_started(reason):
        if held:
            bz.release(held)
        shutil.rmtree(directory, ignore_errors=True)  # nothing ran: leave no evidence that would block the retry
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
        if ram < (mem + 2) * 1024 ** 3:
            raise RuntimeError('Bazzite has %.1f GiB free RAM' % (ram / 1024 ** 3))
        if disk < 20 * 1024 ** 3:
            raise RuntimeError('Bazzite has %.1f GiB free disk' % (disk / 1024 ** 3))
        held = bz.inhibit(unit, deadline + 1800, 'Blender ' + a.blender_job + ' ' + project.name)
        home = bz.sh('printf %s "$HOME"', timeout=60, check=True).stdout.strip()
        bz.sh('mkdir -p ~/%s ~/%s/home ~/%s/out' % (r_project, r_job, r_job), timeout=60, check=True)
        r = bz.push(str(project) + '/', r_project + '/', ['--delete', *EXCLUDE_SYNC], timeout=300, attempts=3)
        if r.returncode:
            raise RuntimeError('project sync failed: ' + r.stderr[-300:])
        if remote_manifest(r_project) != before:
            raise RuntimeError('Bazzite mirror does not match the source manifest')
        if manifest(project) != before:
            raise RuntimeError('Live source changed during sync')
        r = bz.push(str(blender_job_spec.SKILLS) + '/', R_SKILLS + '/', ['--delete', '--exclude=__pycache__', '--no-links'], timeout=300, attempts=3)
        if r.returncode:
            raise RuntimeError('skills sync failed: ' + r.stderr[-300:])
        # .opencode is not mirrored: recreate it empty, stage only the checked inputs that live there, and make the
        # output folder's mountpoint (the project mount is read-only, so podman cannot create it)
        bz.sh('rm -rf ~/%s/.opencode && mkdir -p ~/%s/.opencode/blender-out/%s' % (r_project, r_project, a.blender_job), timeout=60, check=True)
        inputs = [spec['script']] + ([spec['blend']] if spec['blend'] else [])
        if spec['script_name'].startswith('.opencode/'):  # sibling helpers are importable next to the script
            inputs += [f for f in spec['script'].parent.glob('*.py') if f != spec['script']]
        for f in inputs:
            rel = f.relative_to(project) if f.is_relative_to(project) else None
            if rel is None or not str(rel).startswith('.opencode/'):
                continue
            if f.is_symlink() or f.resolve() != f or not f.is_file() or f.stat().st_size > MAX_INPUT_BYTES * 8:
                raise RuntimeError('Unsafe job input: ' + str(rel))
            bz.sh('mkdir -p ' + shlex.quote(home + '/' + r_project + '/' + str(rel.parent)), timeout=60, check=True)
            r = bz.push(str(f), r_project + '/' + str(rel), timeout=120, attempts=3)
            if r.returncode:
                raise RuntimeError('job input sync failed: ' + str(rel))
        if spec['script_name'].startswith('skill:'):
            script_in = '/skills/' + str(spec['script'].relative_to(blender_job_spec.SKILLS))
        else:
            script_in = '/project/' + str(spec['script'].relative_to(project))
        out_in = '/project/.opencode/blender-out/' + a.blender_job
        args = [x.replace('{out}', out_in) for x in spec['args']]
        blend_in = ['/project/' + str(spec['blend'].relative_to(project))] if spec['blend'] else []
        podman = ['podman', 'run', '--rm', '--name', unit, '--network', 'none', '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                  '--userns', 'keep-id:uid=%d,gid=%d' % (WORKER, WORKER), '--memory', '%dg' % mem, '--memory-swap', '%dg' % mem, '--cpus', str(CPUS),
                  '--pids-limit', '256', '--timeout', str(deadline), '--tmpfs', '/tmp:rw,size=2g,mode=1777',
                  '-e', 'HOME=/tmp', '-e', 'OMP_NUM_THREADS=2', '-e', 'WATOOM_OUTPUT=' + out_in, '-e', 'WATOOM_SKILLS=/skills',
                  '-v', '%s/%s:/blender:ro' % (home, R_BLENDER),
                  '-v', '%s/%s:/project:ro,z' % (home, r_project),
                  '-v', '%s/%s:/skills:ro,z' % (home, R_SKILLS),
                  '-v', '%s/%s/out:%s:z' % (home, r_job, out_in),
                  '--workdir', '/project', '--entrypoint', '/blender/' + BLENDER.name, IMAGE_TAG,
                  '--background', *blend_in, '--factory-startup', '-noaudio', '--threads', '2', '--python-exit-code', '1',
                  '--python-expr', BOOT.format(script=script_in), '--', *args]
        job_dir = home + '/' + r_job
        script = '%s > %s 2>&1; echo $? > %s' % (' '.join(shlex.quote(x) for x in podman), shlex.quote(job_dir + '/blender.log'), shlex.quote(job_dir + '/exit_code'))
        launch = ['systemd-run', '--user', '--unit=' + unit, '--collect', '-p', 'MemoryMax=%dG' % (mem + 1), '-p', 'CPUQuota=%d%%' % (CPUS * 100), '-p', 'Nice=10',
                  '-p', 'RuntimeMaxSec=%d' % (deadline + 60), '-p', 'MemorySwapMax=0', '-p', 'TimeoutStopSec=10', '-p', 'KillMode=control-group',
                  '/bin/bash', '-c', script]
        atomic(directory / 'prepared.json', {'unit': unit, 'project': str(project), 'source_files': len(before), 'blender_sha256': BLENDER_SHA, 'worker': 'bazzite',
                                             'memory_limit': '%dGiB' % mem, 'cpus': CPUS, 'deadline_seconds': deadline})
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
    while time.time() - started < deadline + 120:
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
    elapsed = round(time.time() - started, 1)

    log = directory / 'blender.log'
    try:
        bz.pull(r_job + '/blender.log', str(log), timeout=300, attempts=2)
        journal = bz.sh('journalctl --user -u %s.service --no-pager -o cat -n 400' % unit, timeout=60).stdout
    except Exception as e:
        journal = 'LOG_PULL_FAILED: ' + str(e)[:300]
    if not log.exists():
        log.write_text('')
    text = log.read_text(errors='replace') + '\n' + journal
    log.write_text(text)
    os.chmod(log, 0o600)
    tb, errors, result = diagnose(text)

    # ---- bring back only the output folder, checked: regular files, bounded count and size ----
    files, pull_error = [], None
    staging = pathlib.Path(tempfile.mkdtemp(prefix='bz-blender-out-', dir=str(directory)))
    try:
        r = bz.pull(r_job + '/out/', str(staging) + '/', ['--no-links', '--no-specials', '--no-devices'], timeout=900, attempts=3)
        if r.returncode:
            pull_error = 'OUTPUT_PULL_FAILED: ' + r.stderr[-300:]
        found = [x for x in sorted(staging.rglob('*')) if x.is_file() or x.is_symlink()]
        if any(x.is_symlink() for x in found) or len(found) > MAX_OUT_FILES or sum(x.stat().st_size for x in found) > MAX_OUT_BYTES:
            pull_error = 'OUTPUT_REJECTED: links, more than %d files or more than %d MiB' % (MAX_OUT_FILES, MAX_OUT_BYTES >> 20)
    except Exception as e:
        pull_error = 'OUTPUT_PULL_FAILED: ' + str(e)[:300]
    if pull_error:
        errors.append(pull_error)
    else:
        for d in (parent, out):
            if not d.exists():
                d.mkdir(mode=0o2770)
            os.chown(d, st.st_uid, WORKER)
            os.chmod(d, 0o2770)
        subprocess.run(['rsync', '-a', '--no-links', '--chown=%d:%d' % (st.st_uid, WORKER), '--chmod=D2770,F660', str(staging) + '/', str(out) + '/'], check=True, timeout=900)
        files = [x for x in sorted(out.rglob('*')) if x.is_file() and not x.is_symlink()]
    shutil.rmtree(staging, ignore_errors=True)

    timed_out = code in (124,) or (code != 0 and elapsed >= deadline - 1)
    oom = is_oom(code, journal)
    live = manifest(project) == before
    receipt.update(unit=unit, launch=launch_state, exit=code, elapsed_sec=elapsed, traceback=tb, errors=errors, script_result=result,
                   output_directory='.opencode/blender-out/' + a.blender_job, source_manifest='source-manifest.json',
                   live_source_still_matches_snapshot=live,
                   outputs=[{'file': str(x.relative_to(project)), 'bytes': x.stat().st_size} for x in files][:200],
                   log_tail=[x[:300] for x in text.splitlines()[-30:]])
    if code == 0 and not pull_error:
        receipt['status'] = 'PASS'
    else:
        receipt['failure_reason'] = failure_reason(pull_error, oom, timed_out, mem, deadline, tb, result, code)
    if out.is_dir() and not out.is_symlink():
        atomic(out / 'result.json', receipt)
        os.chown(out / 'result.json', st.st_uid, WORKER)
        receipt['app_receipt'] = str(out / 'result.json')
    try:
        bz.sh('rm -rf ~/%s ~/%s/.opencode/blender-out/%s' % (r_job, r_project, a.blender_job), timeout=120)
    finally:
        bz.release(held)
    finish(0 if receipt['status'] == 'PASS' else 1)


if __name__ == '__main__':
    if sys.argv[1:] == ['stage']:
        stage()
    else:
        p = argparse.ArgumentParser()
        p.add_argument('--project', type=pathlib.Path, required=True)
        p.add_argument('--evidence', type=pathlib.Path, required=True)
        p.add_argument('--i-approve', action='store_true')
        p.add_argument('--blender-job', required=True)
        run(p.parse_args())
