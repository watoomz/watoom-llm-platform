"""Rig-side poller for the Unreal lane. Outbound only: it pulls jobs from, and uploads results to, the homelab's transfer-only SFTP jail.
One job at a time; a job that was running when the worker died is NEVER replayed (it is reported as failed and left for the operator)."""
import hashlib, json, os, pathlib, re, subprocess, sys, time
import unreal_lane as lane

HERE = pathlib.Path(__file__).resolve().parent
GIB = 1024 ** 3
ACTIVE_PHASES = ('FETCHING', 'RUNNING', 'UPLOADING')
SKIP_UPLOAD = {'manifest.json', 'plan.json', 'result.json', 'progress.json'}


def atomic(path, value):
    tmp = pathlib.Path(str(path) + '.tmp')
    tmp.write_text(json.dumps(value, indent=2))
    os.replace(tmp, path)


class SftpTransport:
    """The jail's sftp.exe, key-only, host key checked - the same options as the Blender/Godot workers."""
    def __init__(self, cfg, scratch):
        self.cfg = cfg
        self.scratch = pathlib.Path(scratch)

    def _run(self, lines):
        import uuid
        batch = self.scratch / ('.sftp-' + uuid.uuid4().hex + '.batch')
        batch.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        c = self.cfg
        try:
            return subprocess.run([c.get('sftp', 'C:/Windows/System32/OpenSSH/sftp.exe'), '-b', str(batch), '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
                                   '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=15', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
                                   '-i', c['sftp_key'], c.get('sftp_user', 'watoom-render-transfer') + '@' + c['host']],
                                  capture_output=True, text=True, timeout=c.get('transfer_timeout', 3600), creationflags=0x08000000)
        finally:
            batch.unlink(missing_ok=True)

    @staticmethod
    def q(value):
        value = str(value).replace('\\', '/')
        if any(ch in value for ch in '\n\r\0"'):
            raise ValueError('control character or quote in transfer path')
        return '"' + value + '"'

    def list_jobs(self):
        r = self._run(['ls -1 /payloads/inputs/%s*.json' % lane.PREFIX])
        if r.returncode:
            return []   # nothing matches (or the link is down): the next poll tries again
        return sorted(set(re.findall(r'%s([a-z0-9][a-z0-9-]{7,47})\.json' % re.escape(lane.PREFIX), r.stdout)))

    def has_result(self, job):
        r = self._run(['ls -1 /payloads/uploads/%s/result.json' % lane.upload_dir(job)])
        return r.returncode == 0 and 'result.json' in r.stdout

    def get(self, name, local):
        r = self._run(['reget %s %s' % (self.q('/payloads/inputs/' + name), self.q(local))])
        if r.returncode:
            raise RuntimeError('download failed: ' + r.stderr[-200:])

    def put(self, job, files):
        lines = ['-mkdir ' + self.q('/payloads/uploads/' + lane.upload_dir(job))]
        lines += ['put %s %s' % (self.q(f), self.q('/payloads/uploads/%s/%s' % (lane.upload_dir(job), pathlib.Path(f).name))) for f in files]
        r = self._run(lines)
        if r.returncode:
            raise RuntimeError('upload failed: ' + r.stderr[-200:])


def run_runner(plan_path, timeout):
    flags = 0x08000000 if os.name == 'nt' else 0
    return subprocess.run([sys.executable, str(HERE / 'unreal_runner.py'), str(plan_path)], timeout=timeout, creationflags=flags).returncode


class Lane:
    def __init__(self, cfg, transport, runner=run_runner, paused=lambda: False, now=time.time):
        self.cfg, self.t, self.runner, self.paused, self.now = cfg, transport, runner, paused, now
        self.root = pathlib.Path(cfg['root'])
        for sub in ('jobs', 'done'):
            (self.root / sub).mkdir(parents=True, exist_ok=True)
        self.journal = self.root / 'active.json'

    # -- state -------------------------------------------------------------------------------------------------------
    def done(self, job): return (self.root / 'done' / (job + '.json')).exists()
    def mark_done(self, job, status, reason=None): atomic(self.root / 'done' / (job + '.json'), {'job': job, 'status': status, 'reason': reason, 'at': self.now()})

    def progress(self, job, phase, op=None):
        """Best-effort phase signal; failure to publish progress never changes execution or result handling."""
        path = self.root / 'jobs' / job / 'progress.json'
        try:
            atomic(path, {'job': job, 'phase': phase, 'timestamp': self.now(), 'op': op})
            self.t.put(job, [path])
        except Exception:
            pass

    def busy(self):
        """Another RIG consumer (Blender/Godot) holds the GPU/RAM: defer. Journals listed in cfg['busy_journals']."""
        for p in self.cfg.get('busy_journals', []):
            try:
                if json.loads(pathlib.Path(p).read_text(encoding='utf-8-sig')).get('phase') in ACTIVE_PHASES:
                    return True
            except (OSError, ValueError):
                continue
        return False

    def fail(self, job, op, reason, workdir, stage='request', code='unknown'):
        """Upload a FAIL result for a job we cannot or must not run; the homelab sees why."""
        result = {'schema': 1, 'job': job, 'op': op or 'unknown', 'status': 'FAIL', 'reason': reason[:400],
                  'failure_stage': stage, 'failure_code': code, 'files': {}, 'finished': self.now()}
        workdir.mkdir(parents=True, exist_ok=True)
        atomic(workdir / 'result.json', result)
        self.t.put(job, [workdir / 'result.json'])
        self.mark_done(job, 'FAIL', reason[:200])

    # -- one poll ----------------------------------------------------------------------------------------------------
    def once(self):
        if self.paused() or self.busy():
            return None
        if self.journal.exists():
            old = json.loads(self.journal.read_text())
            if old.get('phase') in ACTIVE_PHASES:
                # the worker died mid-job: never replay
                job = old['job']
                try:
                    self.fail(job, old.get('op'), 'Worker restarted during %s; the job was not replayed' % old['phase'], self.root / 'jobs' / (job + '.recovery'), 'run', 'worker_error')
                except Exception:
                    self.mark_done(job, 'RECONCILIATION_REQUIRED', 'restart during ' + old['phase'])
                self.journal.unlink()
                return job
        for job in self.t.list_jobs():
            if self.done(job):
                continue
            if self.t.has_result(job):
                self.mark_done(job, 'ALREADY_HAS_RESULT')
                continue
            return self.process(job)
        return None

    def process(self, job):
        work = self.root / 'jobs' / job
        if work.exists():
            work.rename(work.with_name('%s.old-%d' % (job, time.time_ns())))
        work.mkdir(parents=True)
        atomic(self.journal, {'job': job, 'phase': 'FETCHING', 'op': None})
        self.progress(job, 'FETCHING')
        try:
            self.t.get(lane.manifest_name(job), work / 'manifest.json')
            if (work / 'manifest.json').stat().st_size > 16384:
                raise ValueError('manifest too large')
            manifest = lane.validate_manifest(json.loads((work / 'manifest.json').read_text(encoding='utf-8-sig')), expected_job=job)
        except ValueError as e:                       # a bad manifest is the homelab's mistake: report it, do not run it
            self.fail(job, None, 'Rejected manifest: %s' % e, work, 'request', 'unknown')
            self.journal.unlink()
            return job
        except Exception:                             # transport trouble before anything ran: retry on the next poll
            self.journal.unlink(missing_ok=True)
            return None
        op = lane.OPS[manifest['op']]
        atomic(self.journal, {'job': job, 'phase': 'FETCHING', 'op': manifest['op']})
        try:
            if op['package']:
                pkg = work / 'package.zip'
                self.t.get(lane.package_name(job), pkg)
                if pkg.stat().st_size != manifest['package']['bytes'] or lane.sha256_file(pkg) != manifest['package']['sha256']:
                    raise ValueError('package hash mismatch')
        except ValueError as e:
            self.fail(job, manifest['op'], str(e), work, 'stage', 'not_staged')
            self.journal.unlink()
            return job
        except Exception:
            self.journal.unlink(missing_ok=True)
            return None
        plan = {'job': job, 'op': manifest['op'], 'script': op['script'], 'timeout': op['timeout'], 'memory_bytes': int(self.cfg['memory_gib']) * GIB,
                'plugins': self.cfg.get('plugins', []), 'null_rhi': op.get('null_rhi', True), 'full_editor': bool(op.get('full_editor')),
                'package': bool(op['package'])}
        if op.get('request_op'):                       # keys are fixed here; only validated values come from the manifest
            plan['request'] = {'op': op['request_op'], 'asset': manifest['params']['asset'], 'name': manifest['params']['name'],
                               'bake_makeup': bool(manifest['params'].get('bake_makeup', False))}
        atomic(work / 'plan.json', plan)
        atomic(self.journal, {'job': job, 'phase': 'RUNNING', 'op': manifest['op']})
        self.progress(job, 'RUNNING', manifest['op'])
        timed_out = False
        try:
            code = self.runner(work / 'plan.json', op['timeout'] + 120)
        except Exception as e:
            code = -1
            timed_out = isinstance(e, TimeoutError) or isinstance(e, subprocess.TimeoutExpired)
            (work / 'runner-error.log').write_text(repr(e))
        files = {}
        for f in sorted(work.iterdir()):
            if f.is_file() and f.name not in SKIP_UPLOAD and f.suffix in lane.UPLOAD_SUFFIXES and f.name != 'package.zip':
                files[f.name] = {'sha256': lane.sha256_file(f), 'bytes': f.stat().st_size}
        result = {'schema': 1, 'job': job, 'op': manifest['op'], 'status': 'PASS' if code == 0 else 'FAIL', 'exit_code': code, 'files': files, 'finished': self.now()}
        if code != 0:
            result.update(failure_stage='run', failure_code='timeout' if timed_out else 'oom' if code == 137 else 'worker_error')
        atomic(work / 'result.json', result)
        atomic(self.journal, {'job': job, 'phase': 'UPLOADING', 'op': manifest['op']})
        self.progress(job, 'UPLOADING', manifest['op'])
        self.t.put(job, [work / n for n in files])        # artifacts first ...
        self.t.put(job, [work / 'result.json'])           # ... result.json last: its presence means "complete"
        (work / 'package.zip').unlink(missing_ok=True)
        self.mark_done(job, result['status'])
        self.journal.unlink()
        return job


def main():
    import argparse, msvcrt
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', required=True)
    ap.add_argument('--once', action='store_true')
    a = ap.parse_args()
    cfg = json.loads(pathlib.Path(a.config).read_text(encoding='utf-8-sig'))
    root = pathlib.Path(cfg['root'])
    root.mkdir(parents=True, exist_ok=True)
    # worker sources and the pinned Unreal executables must be exactly what was installed
    for name, digest in json.loads((HERE / 'unreal-lane-provenance.json').read_text())['files'].items():
        if lane.sha256_file(HERE / name) != digest:
            raise RuntimeError('worker file changed since install: ' + name)
    prov = json.loads((HERE / 'unreal-runtime-provenance.json').read_text())
    for name, digest in prov['files'].items():
        if lane.sha256_file(pathlib.Path(prov['executable_dir']) / name) != digest:
            raise RuntimeError('Unreal executable changed since pinning: ' + name)
    lock = (root / 'worker.lock').open('a+b')
    lock.write(b'0'); lock.flush(); lock.seek(0)
    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    try:
        from pause_control import control
        paused = lambda: bool(control(cfg))
    except Exception:
        paused = lambda: False
    worker = Lane(cfg, SftpTransport(cfg, root), paused=paused)
    while True:
        try:
            worker.once()
            atomic(root / 'health.json', {'status': 'paused' if paused() else 'online', 'seenAt': time.time(), 'engine': prov['version']})
        except Exception as e:
            atomic(root / 'health.json', {'status': 'error', 'error': str(e)[:500], 'seenAt': time.time()})
            if a.once:
                raise
        if a.once:
            break
        time.sleep(cfg.get('poll_seconds', 15))


if __name__ == '__main__':
    main()
