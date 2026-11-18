#!/usr/bin/env python3
"""Runs INSIDE the Bazzite container for the godot-game worker operation. Fixed behaviour, no inputs except /job/steps.json (validated by godot_game_spec).

Mounts: /skill (the installed watoom-godot-game skill, read-only), /project (the staged game copy), /job (this folder: steps.json in, driver.json and logs out).
Runs `gg_verify.py selftest` for gl_compatibility first (the container has no GPU, so Vulkan styles cannot run), then each step in order and stops at the
first non-zero exit. Exit 0 only if the selftest and every step exited 0. Skill exit codes: 0 pass, 1 check failed, 2 refused, 3 fatal engine log, 4 no verdict, 5 runner failure.
"""
import json, os, pathlib, subprocess, sys, time

JOB = pathlib.Path(os.environ.get('GG_JOB_DIR', '/job'))
SKILL = pathlib.Path(os.environ.get('GG_SKILL_DIR', '/skill'))
PROJECT = os.environ.get('GG_PROJECT_DIR', '/project')
NO_PROJECT = {('gg_project.py', 'doctor')}


def tail(path, n=25):
    try: return [x[:300] for x in pathlib.Path(path).read_text(errors='replace').splitlines()[-n:]]
    except OSError: return []


def run(cmd, log, timeout, env):
    t = time.time()
    try:
        with open(log, 'w') as f: r = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, timeout=timeout, env=env, cwd=PROJECT)
        return r.returncode, round(time.time() - t, 1), False
    except subprocess.TimeoutExpired:
        return 124, round(time.time() - t, 1), True


def main(deadline):
    steps = json.loads((JOB / 'steps.json').read_text())
    (JOB / 'logs').mkdir(exist_ok=True)
    env = dict(os.environ, GG_GODOT=os.environ.get('GG_GODOT', '/godot'), GG_STATE_DIR=str(JOB / 'state'), PYTHONDONTWRITEBYTECODE='1', HOME=str(JOB / 'home'))
    scripts = SKILL / 'scripts'
    started = time.time()
    report = {'selftest': None, 'steps': [], 'failed_at': None, 'timed_out': False}

    def left(): return max(5, int(deadline - (time.time() - started)))

    code, sec, to = run([sys.executable, str(scripts / 'gg_verify.py'), 'selftest', '--renderer', 'gl_compatibility', '--work', str(JOB / 'selftest')], JOB / 'logs' / '00-selftest.log', left(), env)
    report['selftest'] = {'exit': code, 'sec': sec, 'tail': tail(JOB / 'logs' / '00-selftest.log')}
    ok = code == 0
    if to: report['timed_out'] = True
    for i, s in enumerate(steps, 1):
        if not ok: break
        cmd = [sys.executable, str(scripts / s['script']), s['sub']] + ([] if (s['script'], s['sub']) in NO_PROJECT else ['--project', PROJECT]) + s['args']
        log = JOB / 'logs' / ('%02d-%s-%s.log' % (i, s['script'][:-3], s['sub']))
        code, sec, to = run(cmd, log, left(), env)
        report['steps'].append({'i': i, 'script': s['script'], 'sub': s['sub'], 'args': s['args'], 'exit': code, 'sec': sec, 'tail': tail(log)})
        if code != 0:
            ok = False; report['failed_at'] = i; report['timed_out'] = to
    if not ok and report['failed_at'] is None and report['selftest']['exit'] != 0: report['failed_at'] = 0
    (JOB / 'driver.json').write_text(json.dumps(report, indent=1))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 900))
