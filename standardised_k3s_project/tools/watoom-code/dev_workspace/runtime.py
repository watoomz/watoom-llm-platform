#!/usr/bin/python3 -I
"""Constrained development jobs; the SSH entry point accepts JSON, never a host shell."""
import argparse
import fcntl
import hashlib
import json
import os
import pathlib
import re
import selectors
import signal
import shutil
import subprocess
import sys
import time

CONFIG = pathlib.Path('/data/ai/helper-scripts/dev-workspace/config.json')
PROGRAM = pathlib.Path('/data/ai/helper-scripts/dev-workspace/runtime.py')
JOB = re.compile(r'[a-z0-9][a-z0-9_-]{2,63}')
MAX_LOG = 1024 * 1024


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + '.tmp')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def final_receipt(root, job):
    if os.geteuid() != 0 or not JOB.fullmatch(job):
        raise PermissionError('Trusted finalizer required')
    directory = pathlib.Path(root) / 'tasks' / job
    state = json.loads((directory / 'state.json').read_text())
    atomic(directory / 'exit-receipt.json', {
        'job': job, 'unit': state['unit'], 'time': time.time(),
        'result': os.environ.get('SERVICE_RESULT', 'unknown'),
        'exit_code': os.environ.get('EXIT_CODE', 'unknown'),
        'exit_status': os.environ.get('EXIT_STATUS', 'unknown'),
    })


class Runtime:
    def __init__(self, configuration):
        self.config = configuration
        self.workspace = pathlib.Path(configuration['workspace'])
        self.root = pathlib.Path(configuration['state'])
        if self.workspace.is_symlink() or not self.workspace.is_dir():
            raise PermissionError('Existing real development workspace required')
        if not (self.workspace / '.git').is_dir() or (self.workspace / '.git').is_symlink():
            raise PermissionError('A separate clone with real Git metadata is required')
        if shutil.disk_usage(self.workspace).free < 5 * 1024 ** 3:
            raise RuntimeError('Development storage reserve is below 5 GiB')
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def sandbox(self, argv, metadata=False, network=False):
        workspace = str(self.workspace)
        command = [
            '/usr/sbin/bwrap', '--unshare-all', '--unshare-user', '--disable-userns',
            '--cap-drop', 'ALL', '--die-with-parent', '--new-session', '--clearenv',
            '--ro-bind', '/usr', '/usr', '--symlink', 'usr/bin', '/bin',
            '--symlink', 'usr/sbin', '/sbin', '--symlink', 'usr/lib', '/lib',
            '--symlink', 'usr/lib64', '/lib64', '--proc', '/proc', '--dev', '/dev',
            '--perms', '1777', '--size', '536870912', '--tmpfs', '/tmp',
            '--dir', '/etc', '--ro-bind', '/etc/passwd', '/etc/passwd',
            '--ro-bind', '/etc/group', '/etc/group',
            '--bind', workspace, workspace, '--chdir', workspace,
            '--setenv', 'PATH', '/usr/bin:/bin', '--setenv', 'HOME', '/tmp',
            '--setenv', 'GIT_CONFIG_NOSYSTEM', '1', '--setenv', 'GIT_CONFIG_GLOBAL', '/dev/null',
            '--setenv', 'GIT_TERMINAL_PROMPT', '0', '--setenv', 'GIT_OPTIONAL_LOCKS', '0',
            '--setenv', 'PYTHONDONTWRITEBYTECODE', '1',
        ]
        if not metadata:
            command += ['--ro-bind', workspace + '/.git', workspace + '/.git']
        if network:
            command += ['--share-net', '--dir', '/credentials',
                        '--ro-bind', self.config['git_key'], '/credentials/key',
                        '--ro-bind', self.config['known_hosts'], '/credentials/known_hosts']
        return command + ['--remount-ro', '/', '--', *argv]

    def execute(self, job, stage, argv, timeout=90, metadata=False, network=False):
        directory = self.root / 'tasks' / job
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        counter = len(list(directory.glob('*.log'))) + 1
        unit = 'watoom-dev-' + hashlib.sha256((str(self.root) + job).encode()).hexdigest()[:16] + '-' + str(counter)
        state_path = directory / 'state.json'
        state = json.loads(state_path.read_text()) if state_path.exists() else {'job': job, 'phase': 'PREPARED'}
        state.update(phase='RUNNING', stage=stage, unit=unit, owner_pid=os.getpid(),
                     owner_birth=pathlib.Path('/proc/self/stat').read_text().split()[21], started=time.time())
        receipt = directory / 'exit-receipt.json'
        if receipt.exists():
            receipt.rename(directory / ('exit-receipt-' + str(counter) + '.json'))
        atomic(state_path, state)
        script = self.config.get('program', str(PROGRAM))
        finalizer = '+/usr/bin/python3 -I ' + script + ' --finalize ' + str(self.root) + ' ' + job
        command = ['/usr/sbin/systemd-run', '--quiet', '--wait', '--pipe', '--collect', '--unit=' + unit,
                   '--uid=' + str(self.config['uid']), '--gid=' + str(self.config['gid']),
                   '--property=NoNewPrivileges=yes', '--property=CPUQuota=200%',
                   '--property=MemoryMax=' + self.config.get('memory', '2G'), '--property=TasksMax=64',
                   '--property=RuntimeMaxSec=' + str(timeout + 5), '--property=TimeoutStopSec=5',
                   '--property=KillMode=control-group', '--property=ExecStopPost=' + finalizer,
                   '--', *self.sandbox(argv, metadata, network)]
        log = directory / (str(counter) + '-' + stage + '.log')
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, close_fds=True, env={'PATH': '/usr/bin:/usr/sbin:/bin'})
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        size = 0
        stopped = False
        with log.open('wb') as stream:
            while selector.get_map():
                for key, _ in selector.select(0.5):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    available = max(0, MAX_LOG - size)
                    stream.write(chunk[:available])
                    stream.flush()
                    size += len(chunk)
                if not stopped and (size > MAX_LOG or time.time() > state['started'] + timeout + 12):
                    subprocess.run(['/usr/bin/systemctl', 'stop', '--no-block', unit], capture_output=True, timeout=10)
                    stopped = True
            code = process.wait(timeout=15)
        selector.close()
        process.stdout.close()
        state.update(phase='PASS' if code == 0 and not stopped else 'QUARANTINED',
                     exit_code=code, log=str(log), finished=time.time(), output_capped=size > MAX_LOG)
        atomic(state_path, state)
        text = log.read_text(errors='replace')
        if state['phase'] != 'PASS':
            raise RuntimeError(json.dumps({'status': 'FAIL', 'stage': stage, 'exit_code': code,
                                           'evidence': str(directory), 'output': text[-12000:]}))
        return text

    def git(self, job, *arguments, metadata=False, network=False):
        return self.execute(job, 'git', ['/usr/bin/git', '-c', 'core.hooksPath=/dev/null',
                            '-c', 'core.fsmonitor=false', '-c', 'diff.external=', *arguments],
                            timeout=45, metadata=metadata, network=network).strip()

    def identity(self, job):
        branch = self.git(job, 'branch', '--show-current')
        head = self.git(job, 'rev-parse', 'HEAD')
        if branch != 'dev':
            raise PermissionError('Canonical development branch must remain dev')
        return head

    def fingerprint(self, job):
        code = """import subprocess,pathlib,hashlib,os,json
names=set(subprocess.check_output(['git','ls-files','-co','--exclude-standard','-z']).decode().split(chr(0)))
items={}
for name in sorted(names-{''}):
 p=pathlib.Path(name)
 if p.is_symlink():items[name]='link:'+os.readlink(p)
 elif p.is_file():
  with p.open('rb') as stream:items[name]=hashlib.file_digest(stream,'sha256').hexdigest()
 else:items[name]='missing'
print(hashlib.sha256(json.dumps(items,sort_keys=True).encode()).hexdigest())
"""
        return self.execute(job, 'fingerprint', ['/usr/bin/python3', '-I', '-c', code], timeout=45).strip()

    def request(self, request):
        allowed = {'op', 'job', 'command', 'timeout', 'files', 'message', 'retry', 'session'}
        if not isinstance(request, dict) or set(request) - allowed:
            raise ValueError('Unsupported development request fields')
        job, operation = request.get('job'), request.get('op')
        if not isinstance(request.get('session'), str) or not re.fullmatch(r'[A-Za-z0-9_-]{3,128}', request['session']):
            raise ValueError('A stable native session identity is required')
        if not isinstance(job, str) or not JOB.fullmatch(job):
            raise ValueError('A stable development job ID is required')
        if operation not in {'status', 'run', 'validate', 'commit', 'push', 'report'}:
            raise PermissionError('Unsupported development operation')
        if not self.config.get('enabled'):
            raise PermissionError('Development runtime is disabled')
        lock = (self.root / 'serial.lock').open('a')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            directory = self.root / 'tasks' / job
            manifest = directory / 'task.json'
            self.recover_all()
            task = json.loads(manifest.read_text()) if manifest.exists() else None
            if task and task.get('session') != request.get('session'):
                raise PermissionError('This task belongs to another native session')
            for file in (self.root / 'tasks').glob('*/state.json'):
                state = json.loads(file.read_text())
                if state['phase'] == 'RUNNING' and self.unit_active(state['unit']):
                    if operation == 'status':
                        return {'status': 'RUNNING', 'job': state['job'], 'evidence': str(file.parent)}
                    raise RuntimeError('A development unit is still running; reconcile it before another submission')
            if operation == 'status' and task:
                return {'status': 'PASS', 'task': task, 'last_execution': json.loads((directory / 'state.json').read_text())}
            head = self.identity(job)
            if task is None:
                if self.git(job, 'status', '--porcelain'):
                    raise RuntimeError('Existing uncommitted work is preserved; resume its original task')
                task = {'job': job, 'session': request.get('session'), 'base': head, 'phase': 'PREPARED',
                        'created': time.time(), 'failures': 0, 'baseline': self.config['baseline']}
                atomic(manifest, task)
            if operation in {'run', 'validate'}:
                command = request.get('command')
                timeout = request.get('timeout', 90)
                if not isinstance(command, str) or not 1 <= len(command) <= 8000 or type(timeout) is not int or not 1 <= timeout <= 120:
                    raise ValueError('A bounded command and 1..120 second timeout are required')
                if task['failures'] and (request.get('retry') is not True or task['failures'] >= 2):
                    raise RuntimeError('Inspect the retained failure; one explicit retry is permitted')
                task.update(phase='RUNNING', pending_operation=operation,
                            pending_command_sha256=hashlib.sha256(command.encode()).hexdigest())
                atomic(manifest, task)
                try:
                    output = self.execute(job, operation, ['/bin/bash', '--noprofile', '--norc', '-c', command], timeout)
                except BaseException:
                    task.update(phase='QUARANTINED', failures=task['failures'] + 1)
                    atomic(manifest, task)
                    raise
                task.update(phase='EDITED' if operation == 'run' else 'VALIDATED')
                if operation == 'validate':
                    task.update(validated_command=command, validation_sha256=hashlib.sha256(command.encode()).hexdigest(),
                                validated_fingerprint=self.fingerprint(job), validated_head=self.identity(job))
                atomic(manifest, task)
                return {'status': 'PASS', 'phase': task['phase'], 'head': head, 'output': output[-12000:], 'evidence': str(directory)}
            if operation == 'commit':
                files, message = request.get('files'), request.get('message')
                if not isinstance(files, list) or not 1 <= len(files) <= 30 or not all(isinstance(x, str) and x and not x.startswith('/') and '..' not in x.split('/') and '.git' not in x.split('/') for x in files):
                    raise ValueError('Commit requires 1..30 explicit repository-relative files')
                if not isinstance(message, str) or not 1 <= len(message) <= 500:
                    raise ValueError('A concise commit message is required')
                if task['phase'] != 'VALIDATED' or task.get('validated_head') != head or task.get('validated_fingerprint') != self.fingerprint(job):
                    raise RuntimeError('Run meaningful validation after the last source change before committing')
                if self.git(job, 'diff', '--cached', '--name-only'):
                    raise RuntimeError('Existing staged work is preserved')
                task.update(phase='COMMITTING', files=files, commit_message=message)
                atomic(manifest, task)
                self.git(job, 'add', '--', *files, metadata=True)
                staged = set(self.git(job, 'diff', '--cached', '--name-only').splitlines())
                if not staged or not staged.issubset(set(files)):
                    raise RuntimeError('Staged changes differ from the explicit reviewed file list')
                self.git(job, '-c', 'user.name=WatooM Dev Agent', '-c', 'user.email=dev-agent@localhost', 'commit', '-m', message, metadata=True)
                task.update(phase='COMMITTED', commit=self.identity(job))
                atomic(manifest, task)
            if operation == 'push':
                if task['phase'] != 'COMMITTED' or task.get('commit') != head:
                    raise RuntimeError('Only this validated task commit can be pushed')
                if self.git(job, 'remote', 'get-url', 'origin') != self.config['dev_remote']:
                    raise PermissionError('Development destination changed; push refused')
                task.update(phase='PUSHING')
                atomic(manifest, task)
                ssh = '/usr/bin/ssh -F /dev/null -i /credentials/key -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/credentials/known_hosts'
                self.git(job, '-c', 'core.sshCommand=' + ssh, '-c', 'push.recurseSubmodules=no', 'push', 'origin', 'HEAD:refs/heads/dev', metadata=True, network=True)
                task.update(phase='PUSHED', pushed_commit=head)
                atomic(manifest, task)
            return {'status': 'PASS', 'task': task, 'evidence': str(directory)}
        finally:
            lock.close()

    @staticmethod
    def unit_active(unit):
        if not re.fullmatch(r'watoom-dev-[a-f0-9]{16}-[0-9]+', unit):
            raise PermissionError('Foreign unit identity refused')
        return subprocess.run(['/usr/bin/systemctl', 'is-active', '--quiet', unit], capture_output=True).returncode == 0

    def recover_all(self):
        for path in (self.root / 'tasks').glob('*/state.json'):
            state = json.loads(path.read_text())
            if state['phase'] != 'RUNNING' or self.unit_active(state['unit']):
                continue
            process = pathlib.Path('/proc') / str(state['owner_pid']) / 'stat'
            if process.exists() and process.read_text().split()[21] == state.get('owner_birth'):
                continue
            receipt = path.parent / 'exit-receipt.json'
            state.update(phase='INTERRUPTED', recovery='Retained working files and logs; review and resume the same task')
            if receipt.exists():
                state['exit_receipt'] = json.loads(receipt.read_text())
            atomic(path, state)
            manifest = path.parent / 'task.json'
            if manifest.exists():
                task = json.loads(manifest.read_text())
                if task['phase'] in {'RUNNING', 'COMMITTING', 'PUSHING'}:
                    task.update(phase='QUARANTINED', recovery='Review the retained log and actual HEAD before resuming; do not replay commit/push blindly')
                    atomic(manifest, task)


def git_transport():
    import shlex
    settings = json.loads(pathlib.Path('/data/ai/helper-scripts/dev-workspace/transport.json').read_text())
    command = shlex.split(os.environ.get('SSH_ORIGINAL_COMMAND', ''))
    if len(command) != 2 or command[0] not in {'git-upload-pack', 'git-receive-pack'} or command[1] != settings['bare']:
        raise PermissionError('This key supports only the dedicated development Git repository')
    os.execv('/usr/bin/git', ['git','-c','safe.directory='+settings['bare'],command[0].removeprefix('git-'),settings['bare']])


def receive_policy():
    for line in sys.stdin:
        old, new, ref = line.split()
        if ref != 'refs/heads/dev' or not re.fullmatch('[a-f0-9]{40}', old + '') or not re.fullmatch('[a-f0-9]{40}', new) or new == '0' * 40:
            raise PermissionError('Only non-deleting dev updates are permitted')
        if old != '0' * 40 and subprocess.run(['/usr/bin/git', 'merge-base', '--is-ancestor', old, new], capture_output=True).returncode:
            raise PermissionError('Development history cannot be overwritten')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', action='store_true')
    parser.add_argument('--recover-all', action='store_true')
    parser.add_argument('--finalize', nargs=2)
    parser.add_argument('--git-transport', action='store_true')
    parser.add_argument('--receive-policy', action='store_true')
    arguments = parser.parse_args()
    if arguments.git_transport:
        return git_transport()
    if arguments.receive_policy:
        return receive_policy()
    if os.geteuid() != 0:
        raise PermissionError('The constrained administrative entry point is required')
    if arguments.finalize:
        return final_receipt(*arguments.finalize)
    runtime = Runtime(json.loads(CONFIG.read_text()))
    if arguments.recover_all:
        return runtime.recover_all()
    if not arguments.request:
        raise ValueError('An explicit operation is required')
    signal.alarm(10)
    raw = sys.stdin.buffer.read(65537)
    signal.alarm(0)
    if len(raw) > 65536:
        raise ValueError('Development request exceeds its limit')
    print(json.dumps(runtime.request(json.loads(raw))))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'status': 'FAIL', 'error': str(error)}))
        raise SystemExit(1)
