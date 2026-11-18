#!/usr/bin/env python3
"""Operator-side terrain/landscape-to-GLB export for a native game-worker request; the root dispatcher is the
only caller. Runs an existing, project-staged .uproject + in-engine Python script (terrain_spec.py validates
the declarative request) on the Bazzite worker -- never on the homelab server, which runs the production LLM
and other shared services (see export_pack.py's own "keeps big exports off the homelab server's RAM").

Unlike export_pack.py (which exports READ-ONLY purchased-pack Content by asset class), this runs an arbitrary,
already-reviewed project script against a project-staged Unreal project: the whole staged directory is mounted
writable (Unreal needs to write Saved/Intermediate/DerivedDataCache on first open), so integrity is checked by
excluding those UE-generated paths and the designated output/ directory, not by a strict before==after.

Writes <evidence>/result.json; exit 0 on PASS, 1 otherwise. Never replays a start: a launch failure after the
Bazzite inhibitor is held is reported as FAIL, not retried here.
"""
import argparse, hashlib, json, os, pathlib, shlex, subprocess, sys, time
import terrain_spec

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / 'ansible/roles/watoom-code/files/skills/watoom-fab-owned-assets/scripts/unreal-export'))
import bazzite as bz  # noqa: E402

ENGINE = pathlib.Path('/data/ai/toolchains/unreal/5.8.3/runtime-74dc43e1a653')
EXCLUDE_DIRS = {'Saved', 'Intermediate', 'DerivedDataCache', 'output', '.git'}
MIN_FREE_GIB = 8
RESERVE_GIB = 2


def atomic(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2))
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def directory_hashes(root):
    out = {}
    for path in sorted(root.rglob('*')):
        if path.is_dir() or any(p in EXCLUDE_DIRS for p in path.relative_to(root).parts[:-1]) or path.relative_to(root).parts[0] in EXCLUDE_DIRS:
            continue
        if path.is_symlink() or not path.is_file():
            raise ValueError('Unsafe terrain staging entry: ' + str(path))
        out[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--project', type=pathlib.Path, required=True)
    p.add_argument('--evidence', type=pathlib.Path, required=True)
    p.add_argument('--i-approve', action='store_true')
    p.add_argument('--terrain-job', required=True)
    a = p.parse_args()
    if os.geteuid() != 0:
        raise PermissionError('Operator only')
    project = a.project.resolve(strict=True)
    if not a.i_approve or a.project.is_symlink() or project.parent != pathlib.Path('/data/ai/projects/games') or not (project / 'project.godot').is_file():
        raise ValueError('Approved existing game project required')
    a.evidence.mkdir(parents=True, exist_ok=False)
    os.chmod(a.evidence, 0o750)
    receipt = {'status': 'FAIL', 'scope': 'Terrain/landscape GLB export from a project-staged Unreal project; Godot scene assembly stays separate.', 'job': a.terrain_job}
    held = None
    try:
        spec = terrain_spec.load(project, a.terrain_job)
        staging = project / spec['directory']
        before = directory_hashes(staging)
        image = subprocess.check_output(['kubectl', '-n', 'watoom-code', 'get', 'deploy', 'watoom-toolkit',
                                          '-o', 'jsonpath={.spec.template.spec.containers[0].image}'], text=True).strip()
        if '@sha256:' not in image:
            raise RuntimeError('Production toolkit image is not digest-pinned')
        staged = bz.runtime_ready()
        if not staged:
            raise RuntimeError('Bazzite toolkit not staged (bazzite.py stage-runtime)')
        if staged[1].get('image') != image:
            raise RuntimeError('Bazzite toolkit image differs from production; re-run bazzite.py stage-runtime')
        ram, disk = bz.free()
        need = (spec['memory_gib'] + RESERVE_GIB) * 1024 ** 3
        if ram < need:
            raise RuntimeError('Bazzite has %.1f GiB free RAM, needs %d' % (ram / 1024 ** 3, spec['memory_gib'] + RESERVE_GIB))
        staging_bytes = sum(f.stat().st_size for f in staging.rglob('*') if f.is_file())
        if disk < 2 * staging_bytes + 20 * 1024 ** 3:
            raise RuntimeError('Bazzite has %.1f GiB free disk' % (disk / 1024 ** 3))
        name = 'watoom-terrain-' + hashlib.sha256((str(project) + a.terrain_job).encode()).hexdigest()[:12]
        held = bz.inhibit(name, spec['deadline_sec'] + 1800, 'Terrain export ' + name)
        home = bz.sh('printf %s "$HOME"', timeout=60, check=True).stdout.strip()
        r_job = bz.R_JOBS + '/' + name
        bz.sh('mkdir -p ~/%s' % r_job, timeout=60, check=True)
        r = bz.push(str(staging) + '/', '%s/' % r_job, ['--delete'])
        if r.returncode:
            raise RuntimeError('terrain staging sync failed: ' + r.stderr[-500:])
        remote_hash = bz.sh("cd ~/%s && find . -type f -not -path './Saved/*' -not -path './Intermediate/*' "
                             "-not -path './DerivedDataCache/*' -not -path './output/*' -not -path './.git/*' "
                             "-print0 | xargs -0r sha256sum" % r_job, timeout=600, check=True)
        remote_before = {l[66:].removeprefix('./'): l[:64] for l in remote_hash.stdout.splitlines() if len(l) > 66}
        if remote_before != before:
            raise RuntimeError('terrain staging on Bazzite does not match the local staged copy')
        budget = spec['deadline_sec'] - 60
        editor_cmd = ['/unreal-engine/Engine/Binaries/Linux/UnrealEditor', '/job/' + spec['uproject_file'],
                      '-ExecutePythonScript=/job/' + spec['script'], '-nosplash', '-RenderOffScreen', '-NullRHI',
                      '-unattended', '-nosound', '-nop4', '-stdout', '-ddc=NoZenLocalFallback', '-LocalDataCachePath=/job/DerivedDataCache']
        home_env = {'HOME': '/tmp/home', 'XDG_CACHE_HOME': '/tmp/home/.cache', 'XDG_CONFIG_HOME': '/tmp/home/.config',
                    'XDG_DATA_HOME': '/tmp/home/.local/share', 'SDL_VIDEODRIVER': 'dummy', 'SDL_AUDIODRIVER': 'dummy'}
        podman = ['podman', 'run', '--rm', '--name', name, '--network', 'none', '--read-only', '--cap-drop', 'ALL',
                  '--security-opt', 'no-new-privileges', '--userns', 'keep-id:uid=1009,gid=1009',
                  '--memory', '%dg' % spec['memory_gib'], '--memory-swap', '%dg' % spec['memory_gib'], '--cpus', '4',
                  '--pids-limit', '4096', '--tmpfs', '/tmp:rw,size=2g,mode=1777',
                  *sum([['-e', '%s=%s' % kv] for kv in home_env.items()], []),
                  '-v', '%s/%s:/unreal-engine:ro,z' % (home, bz.R_ENGINE), '-v', '%s/%s:/job:z' % (home, r_job),
                  staged[1]['local_tag'], *editor_cmd]
        job_dir = home + '/' + r_job
        script_line = '%s > %s 2>&1; echo $? > %s' % (' '.join(shlex.quote(x) for x in podman),
                                                        shlex.quote(job_dir + '/native.log'), shlex.quote(job_dir + '/exit_code'))
        unit = ['systemd-run', '--user', '--unit=' + name, '--collect', *bz.UNIT_LIMITS,
                '-p', 'RuntimeMaxSec=%d' % (spec['deadline_sec'] + 60), '/bin/bash', '-c', script_line]
        atomic(a.evidence / 'prepared.json', {'unit': name, 'project': str(project), 'staging': spec['directory'],
                                               'memory_limit': '%dGiB' % spec['memory_gib'], 'deadline_sec': spec['deadline_sec'],
                                               'image': staged[1]['image']})
        launch = ' '.join(shlex.quote(x) for x in unit)
    except Exception as e:
        if held:
            bz.release(held)
        receipt['failure_reason'] = str(e)[:500]
        atomic(a.evidence / 'result.json', receipt)
        print(json.dumps({k: receipt.get(k) for k in ('status', 'failure_reason')}))
        raise SystemExit(1)

    # from the launch on there is no fallback: a launch error may still have started the unit
    extra = {}
    try:
        r = bz.sh(launch, timeout=120)
        extra['launch'] = 'ok' if r.returncode == 0 else 'error: ' + r.stderr[-300:]
    except Exception as e:
        extra['launch'] = 'uncertain: ' + str(e)[:300]
    deadline = time.time() + spec['deadline_sec'] + 180
    code = None
    while time.time() < deadline:
        try:
            r = bz.sh('cat ~/%s/exit_code 2>/dev/null; systemctl --user is-active %s.service' % (r_job, name), timeout=60)
            lines = r.stdout.split()
            if lines and lines[0].lstrip('-').isdigit():
                code = int(lines[0])
                break
            if lines and lines[-1] in ('inactive', 'failed'):
                break
        except Exception:
            pass
        time.sleep(15)
    elapsed = round(time.time() - (deadline - spec['deadline_sec'] - 180), 1)
    r = bz.pull('%s/output/' % r_job, str(a.evidence / 'output') + '/', [])
    pulled_output = r.returncode == 0
    log = a.evidence / 'native.log'
    lr = bz.pull('%s/native.log' % r_job, str(log), [])
    if not log.exists():
        log.write_text('')
    os.chmod(log, 0o600)
    bz.release(held)
    manifest = None
    manifest_path = a.evidence / 'output' / 'manifest.json'
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text())
        except (OSError, ValueError):
            manifest = None
    try:
        remote_after = bz.sh("cd ~/%s && find . -type f -not -path './Saved/*' -not -path './Intermediate/*' "
                              "-not -path './DerivedDataCache/*' -not -path './output/*' -not -path './.git/*' "
                              "-print0 | xargs -0r sha256sum" % r_job, timeout=600, check=True)
        after = {l[66:].removeprefix('./'): l[:64] for l in remote_after.stdout.splitlines() if len(l) > 66}
    except Exception:
        after = None
    source_unchanged = after == before if after is not None else None
    bz.sh('rm -rf ~/%s' % r_job, timeout=300)
    produced = manifest.get('output', {}).get('produced') if manifest else None
    status = 'PASS' if code == 0 and pulled_output and manifest and manifest.get('status') in ('SUCCESS', 'PARTIAL') and produced and source_unchanged else 'FAIL'
    if status == 'FAIL':
        reason = ('timeout' if code is None else 'worker-exit (%s)' % code if code != 0 else
                  'source changed during execution' if source_unchanged is False else
                  'no output produced' if not manifest or not produced else
                  str(manifest.get('status')) if manifest else 'pull failed')
    else:
        reason = None
    receipt.update(status=status, failure_reason=reason, unit=name, exit=code, elapsed_sec=elapsed, memory_limit='%dGiB' % spec['memory_gib'],
                   deadline_sec=spec['deadline_sec'], source_unchanged=source_unchanged, manifest=manifest,
                   output_directory=str(a.evidence / 'output') if pulled_output else None, **extra)
    atomic(a.evidence / 'result.json', receipt)
    print(json.dumps({k: receipt.get(k) for k in ('status', 'failure_reason', 'manifest', 'output_directory')}))
    raise SystemExit(0 if status == 'PASS' else 1)


if __name__ == '__main__':
    main()
