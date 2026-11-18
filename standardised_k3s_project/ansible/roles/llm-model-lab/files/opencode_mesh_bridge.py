#!/usr/bin/env python3
"""Narrow local bridge; all GPU work remains in the existing pipeline."""
import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import socket
import socketserver
import struct
import stat
import sqlite3
from contextlib import closing
import uuid
from pathlib import Path
from types import SimpleNamespace

def load(path):
    return json.loads(Path(path).read_text())

class Bridge:
    def __init__(self, config):
        self.config = config
        spec = importlib.util.spec_from_file_location('pipeline', config['pipeline'])
        self.pipeline = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.pipeline)
        self.c = self.pipeline.cfg()
        self.state = Path(config['state'])
        self.state.mkdir(mode=0o700, parents=True, exist_ok=True)

    def owned(self, jid):
        if not isinstance(jid, str) or not re.fullmatch(r'[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}', jid):
            raise ValueError('Invalid job ID')
        # Ownership derives from a root-owned allocation, never from client paths.
        job = self.pipeline.find_job(self.c, jid)
        request = load(job / 'request.json')
        output = Path(request['output_dir']).resolve()
        root = Path(self.c['asset_root']).resolve() / 'opencode-mesh'
        if output.parent != root or not (self.state / (output.name + '.json')).is_file():
            raise PermissionError('Job is not owned by this bridge')
        return job, output

    def checkpoint(self, request, peer_uid):
        database = getattr(self, 'config', {}).get('checkpoint_databases', {}).get(str(peer_uid))
        if database is None:
            return None
        request_id = request.get('request_id')
        if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', request_id):
            raise PermissionError('Native durable checkpoint requires request_id')
        arguments = {k: int(v) if type(v) is float and v.is_integer() else v for k, v in request.items() if k != 'operation'}
        digest = hashlib.sha256(json.dumps(arguments, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
        with closing(sqlite3.connect(Path(database).as_uri() + '?mode=ro', uri=True, timeout=2)) as db:
            rows = db.execute("SELECT body FROM _watoom_outbox WHERE body LIKE ? AND state IN ('pending','sending','uncertain','observed')", ('%' + request_id + '%',)).fetchall()
        for (body,) in rows:
            event = json.loads(body)
            try:
                content = json.loads(event['content'])
                scope = event['scope']
                valid = (event['version'] == 2 and event['seq'] == 1 and event['kind'] == 'checkpoint'
                         and event['job'].startswith('gpu:') and event['job'].endswith(':' + request_id)
                         and content.get('phase') == 'GPU_HANDOVER_PENDING'
                         and content.get('requestID') == request_id and content.get('inputDigest') == digest
                         and all(isinstance(scope[k], str) and scope[k] for k in ('project','repository','agent')))
                if valid:
                    return {'id': event['id'], 'scope': scope, 'input_digest': digest}
            except (KeyError, TypeError, ValueError):
                continue
        raise PermissionError('Matching native durable GPU checkpoint not found; no GPU work submitted')

    def execute(self, request, peer_uid=None):
        if not isinstance(request, dict):
            raise ValueError('Expected object')
        op = request.get('operation')
        if op == 'submit':
            if set(request) - {'operation', 'prompt', 'name', 'seed', 'temperature', 'max_tokens', 'request_id'}:
                raise ValueError('Unsupported submission option')
            prompt = request.get('prompt')
            name = request.get('name', 'mesh')
            if not isinstance(prompt, str) or not prompt.strip() or len(prompt.encode()) > 8192:
                raise ValueError('Prompt must be nonempty UTF-8, <=8192 bytes')
            if not isinstance(name, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,59}', name):
                raise ValueError('Invalid asset name')
            options = {'seed': 42, 'temperature': 1.0, 'max_tokens': 7000}
            options.update({k: request[k] for k in options if k in request})
            if type(options['seed']) is not int or not 0 <= options['seed'] <= 2147483647:
                raise ValueError('Invalid seed')
            if type(options['max_tokens']) is not int or not 1 <= options['max_tokens'] <= 7000:
                raise ValueError('Invalid token budget')
            if type(options['temperature']) not in (int, float) or not math.isfinite(options['temperature']) or not 0 <= options['temperature'] <= 2:
                raise ValueError('Invalid temperature')
            request_id=request.get('request_id')
            checkpoint=self.checkpoint(request, peer_uid)
            receipt=None
            digest=hashlib.sha256(json.dumps(request,sort_keys=True).encode()).hexdigest()
            if request_id is not None:
                if not isinstance(request_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',request_id):
                    raise ValueError('Invalid request_id')
                receipt=self.state/('request-'+hashlib.sha256(request_id.encode()).hexdigest()+'.json')
                if receipt.exists():
                    saved=load(receipt)
                    if saved['digest']!=digest:raise RuntimeError('request_id reused with different arguments')
                    for state in ('pending','running','complete','failed'):
                        for job in (Path(self.c['job_root'])/state).iterdir():
                            request_path=job/'request.json'
                            if request_path.is_file() and load(request_path).get('output_dir')==saved['output_dir']:
                                return {'job_id':job.name,'state':load(job/'status.json')['state'],'status_identifier':job.name,'idempotent':True}
                    raise RuntimeError('Submission receipt exists with unknown outcome; do not resubmit; operator reconciliation required')
            # Bound durable outstanding requests to avoid unattended GPU backlog.
            active = sum(1 for state in ('pending', 'running') for j in (Path(self.c['job_root']) / state).iterdir() if j.is_dir())
            if active >= 4:
                raise RuntimeError('Pipeline queue is full; check existing jobs')
            allocation = name + '-' + uuid.uuid4().hex
            output = Path(self.c['asset_root']) / 'opencode-mesh' / allocation
            record = self.state / (allocation + '.json')
            self.pipeline.write(record, {'name': name, 'created_at': self.pipeline.now(), 'native_checkpoint': checkpoint})
            if receipt is not None:self.pipeline.write(receipt,{'digest':digest,'output_dir':str(output),'request_id':request_id})
            prompt_path = self.state / (allocation + '.txt')
            prompt_path.write_text(prompt)
            # Directly reuse submit: durable atomic request, existing systemd worker.
            import contextlib
            import io
            capture = io.StringIO()
            with contextlib.redirect_stdout(capture):
                self.pipeline.submit(self.c, SimpleNamespace(command='submit', prompt_file=str(prompt_path), output_dir=str(output), name=name, dry_run=False, **options))
            jid = capture.getvalue().strip().removeprefix('JOB_ID=')
            job, _ = self.owned(jid)
            req = load(job / 'request.json')
            return {'job_id': jid, 'state': load(job / 'status.json')['state'], 'created_at': req['created_at'], 'status_identifier': jid}
        if op == 'list':
            if set(request) != {'operation'}:
                raise ValueError('List accepts no options')
            jobs = []
            for state in ('pending', 'running', 'complete', 'failed'):
                for job in (Path(self.c['job_root']) / state).iterdir():
                    try:
                        owned, _ = self.owned(job.name)
                        jobs.append(load(owned / 'status.json'))
                    except (ValueError, PermissionError, FileNotFoundError):
                        continue
            return {'jobs': sorted(jobs, key=lambda x: x['job_id'], reverse=True)[:100]}
        if op not in ('status', 'manifest', 'retrieve') or set(request) != {'operation', 'job_id'}:
            raise ValueError('Unsupported operation or fields')
        job, output = self.owned(request['job_id'])
        status = load(job / 'status.json')
        if op == 'status':
            return {**status, 'completion': status['state'] == 'complete', 'artifacts': self.artifacts(job, output, status)}
        manifest = load(job / 'result/manifest.json')
        if op == 'manifest':
            return manifest
        artifacts = self.artifacts(job, output, status)
        if not artifacts:
            raise RuntimeError('Validated outputs are not available')
        return {'job_id': request['job_id'], 'artifacts': artifacts, 'manifest': manifest}

    def artifacts(self, job, output, status):
        manifest_path = job / 'result/manifest.json'
        if status['state'] != 'complete' or not manifest_path.is_file() or load(manifest_path).get('result') != 'PASS':
            return {}
        result = {}
        for key, rel in {'obj': 'raw/mesh.obj', 'glb': 'game-ready/asset.glb', 'manifest': 'manifests/manifest.json'}.items():
            path = output / rel
            if path.is_file() and not path.is_symlink() and output in path.resolve().parents:
                result[key] = '/assets/' + str(path.relative_to(Path(self.c['asset_root']).parent))
        for path in sorted((output / 'renders').glob('*.png')):
            if path.is_file() and not path.is_symlink() and output in path.resolve().parents:
                result['render_' + path.stem] = '/assets/' + str(path.relative_to(Path(self.c['asset_root']).parent))
        return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    config = load(args.config)
    bridge = Bridge(config)
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            self.connection.settimeout(15)
            try:
                _, uid, _ = struct.unpack('3i', self.connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                if uid not in [config['uid'], *config.get('additional_uids', [])]:
                    raise PermissionError('Unauthorized peer UID')
                line = self.rfile.readline(16385)
                if len(line) > 16384 or not line.endswith(b'\n'):
                    raise ValueError('Request exceeds limit or is incomplete')
                result = {'ok': True, 'result': bridge.execute(json.loads(line), peer_uid=uid)}
            except Exception as error:
                result = {'ok': False, 'error': str(error)}
            self.wfile.write(json.dumps(result).encode() + b'\n')
    path = Path(config['socket'])
    # Hold the root-owned directory inode: a container user can rename its
    # writable ancestors, but must never redirect privileged socket operations.
    directory = os.open(path.parent, os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        metadata = os.fstat(directory)
        if metadata.st_uid != 0 or metadata.st_mode & 0o022:
            raise RuntimeError('Socket directory must be root-owned and non-writable')
        try:
            existing = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
            if not stat.S_ISSOCK(existing.st_mode):
                raise RuntimeError('Refuse to replace non-socket')
            os.unlink(path.name, dir_fd=directory)
        except FileNotFoundError:
            pass
        with socketserver.UnixStreamServer('/proc/self/fd/' + str(directory) + '/' + path.name, Handler) as server:
            os.chown(path.name, 0, config['gid'], dir_fd=directory, follow_symlinks=False)
            os.chmod(path.name, 0o660, dir_fd=directory)
            server.serve_forever()
    finally:
        os.close(directory)

if __name__ == '__main__':
    main()
