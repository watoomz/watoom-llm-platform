#!/usr/bin/python3 -I
"""Owned native activation, with independent systemd finalization and rollback."""
import argparse
import base64
import hashlib
import json
import os
import pathlib
import secrets
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from runtime import atomic
from maintenance_guard import Maintenance
import release_guard

HOME = pathlib.Path('/data/ai/helper-scripts/dev-workspace')
CONFIG = pathlib.Path('/data/ai/watoom-code/config/opencode.json')
AGENT = CONFIG.parent / 'agents/watoom-dev.md'
JOURNAL = HOME / 'activation.json'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write(path, data, uid=1001, gid=1001):
    temporary = path.with_name('.' + path.name + '.dev-activation')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchown(stream.fileno(), uid, gid)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    subprocess.run(['restorecon', str(path)], check=True, capture_output=True)


def manager(out):
    return Maintenance('watoom-code', 'watoom-code', out, True, True)


def recover(only_idle=False):
    if not JOURNAL.exists():
        return
    state = json.loads(JOURNAL.read_text())
    if state['phase'] in {'COMPLETE', 'ROLLED_BACK'}:
        return
    if only_idle:
        process = pathlib.Path('/proc') / str(state.get('controller_pid', state.get('launcher_pid', -1))) / 'stat'
        if process.exists() and process.read_text().split()[21] == state.get('controller_birth', state.get('launcher_birth')):
            return
    # The backend stays closed during every incomplete native activation.
    runtime = json.loads((HOME / 'config.json').read_text())
    runtime['enabled'] = False
    atomic(HOME / 'config.json', runtime)
    old, new = base64.b64decode(state['before']), base64.b64decode(state['after'])
    current = CONFIG.read_bytes()
    if current == new:
        write(CONFIG, old)
    elif current != old:
        state['concurrent_config_change'] = True
    if AGENT.exists() and digest(AGENT.read_bytes()) == state['agent_sha']:
        # Preserve the owned definition as evidence instead of deleting it.
        AGENT.rename(pathlib.Path(state['evidence']) / 'rolled-back-agent.md')
    if state.get('owner'):
        m = manager(state['evidence'])
        guard = m.request('/api/session/deployment-guard')
        if guard.get('data', {}).get('held'):
            release_guard.release(m.request, lambda p, b: m.request(p, b), state['owner'])
    state.update(phase='ROLLED_BACK', recovered=time.time(), runtime_enabled=False)
    atomic(JOURNAL, state)


def run():
    state = json.loads(JOURNAL.read_text())
    if state['phase'] != 'PREPARED':
        raise RuntimeError('Fresh owned preparation required')
    state.update(controller_pid=os.getpid(), controller_birth=pathlib.Path('/proc/self/stat').read_text().split()[21])
    atomic(JOURNAL, state)
    out = pathlib.Path(state['evidence'])
    m = manager(out)

    def clearance():
        release_guard.active_clear(m.request('/api/session/active'))
        release_guard.durable_clearance(pathlib.Path('/data/ai/watoom-code/application.sqlite'))
        if any(j.get('status', {}).get('active') for j in m.kub('get', 'jobs')['items']):
            raise RuntimeError('Active worker Job; activation postponed')

    def save(owner):
        state.update(owner=owner, phase='ACQUIRING')
        atomic(JOURNAL, state)

    try:
        clearance()
        before_agents = m.request('/api/agent?directory=/workspace')
        (out / 'agents-before.json').write_text(json.dumps(before_agents))
        owner = release_guard.acquire(m.request, lambda p, b: m.request(p, b), save, clearance)
        state['phase'] = 'APPLYING'
        atomic(JOURNAL, state)
        if CONFIG.read_bytes() != base64.b64decode(state['before']) or AGENT.exists():
            raise RuntimeError('Native files changed after preparation')
        release_guard.snapshot_database(pathlib.Path('/data/ai/watoom-code/application.sqlite'), out / 'application-before.private.sqlite')
        write(CONFIG, base64.b64decode(state['after']))
        write(AGENT, (HOME / 'staged-agent.md').read_bytes())
        deadline = time.monotonic() + 45
        while True:
            result = m.request('/api/agent?directory=/data/github/watoom-homelab-dev')
            rows = result.get('data', result) if isinstance(result, dict) else result
            if any(a.get('id', a.get('name')) == 'watoom-dev' for a in rows):
                break
            if time.monotonic() > deadline:
                raise RuntimeError('Native development agent was not discovered')
            time.sleep(1)
        runtime = json.loads((HOME / 'config.json').read_text())
        runtime['enabled'] = True
        atomic(HOME / 'config.json', runtime)
        # The synchronous finalizer rolls back unless this checkpoint is reached.
        release_guard.release(m.request, lambda p, b: m.request(p, b), owner)
        state.update(phase='COMPLETE', completed=time.time())
        atomic(JOURNAL, state)
        print(json.dumps({'status': 'PASS', 'native_agent': 'watoom-dev', 'evidence': str(out)}))
    except BaseException:
        recover()
        raise


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--prepare', action='store_true')
    p.add_argument('--run', action='store_true')
    p.add_argument('--recover', action='store_true')
    p.add_argument('--recover-if-idle', action='store_true')
    p.add_argument('--package-sha')
    p.add_argument('--host')
    p.add_argument('--evidence', type=pathlib.Path)
    p.add_argument('--i-approve', action='store_true')
    a = p.parse_args()
    if os.geteuid() != 0:
        raise PermissionError('Trusted administrator required')
    if a.recover or a.recover_if_idle:
        return recover(a.recover_if_idle)
    if a.run:
        return run()
    print('RISK: adds only the constrained development agent and native tool. Existing production sessions must be idle; independent rollback releases only this owned fence. No deployment or inference restart.', flush=True)
    if not a.prepare or not a.i_approve:
        raise PermissionError('--prepare --i-approve required')
    import re
    if not re.fullmatch('[a-f0-9]{64}', a.package_sha or '') or not re.fullmatch('[0-9.]+', a.host or ''):
        raise ValueError('Verified package digest and numeric host required')
    if JOURNAL.exists() and json.loads(JOURNAL.read_text())['phase'] not in {'COMPLETE', 'ROLLED_BACK'}:
        raise RuntimeError('Recover previous owned activation first')
    if AGENT.exists() or CONFIG.is_symlink():
        raise RuntimeError('Existing agent or indirect configuration requires inspection')
    before = CONFIG.read_bytes()
    config = json.loads(before)
    package = '/config/watoom-tools/dev-workspace-' + a.package_sha
    if any('dev-workspace-' in str(x) for x in config.get('plugins', [])):
        raise RuntimeError('An existing development plugin must be inspected')
    config.setdefault('plugins', []).append({'package': package, 'options': {
        'host': a.host, 'user': 'watoom-dev-run',
        'key': '/config/watoom-tools/dev-workspace-credentials/key',
        'knownHosts': '/config/watoom-tools/dev-workspace-credentials/known_hosts'}})
    a.evidence.mkdir(parents=True, exist_ok=False, mode=0o700)
    state = {'phase': 'PREPARED', 'launcher_pid': os.getpid(), 'launcher_birth': pathlib.Path('/proc/self/stat').read_text().split()[21], 'before': base64.b64encode(before).decode(),
             'after': base64.b64encode((json.dumps(config, indent=2) + '\n').encode()).decode(),
             'agent_sha': digest((HOME / 'staged-agent.md').read_bytes()), 'evidence': str(a.evidence)}
    atomic(JOURNAL, state)
    unit = 'watoom-dev-activate-' + secrets.token_hex(4)
    command = ['/usr/sbin/systemd-run', '--quiet', '--wait', '--collect', '--unit=' + unit,
               '--property=RuntimeMaxSec=120', '--property=TimeoutStopSec=10',
               '--property=ExecStopPost=/usr/bin/python3 -I ' + str(HOME / 'activation.py') + ' --recover',
               '--', '/usr/bin/python3', '-I', str(HOME / 'activation.py'), '--run']
    subprocess.run(command, check=True, timeout=160)
    if json.loads(JOURNAL.read_text())['phase'] != 'COMPLETE':
        raise RuntimeError('Activation did not complete; inspect retained journal')
    print('PASS independent development activation')


if __name__ == '__main__':
    main()
