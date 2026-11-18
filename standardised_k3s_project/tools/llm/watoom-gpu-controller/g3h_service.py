"""Production host gateway; no credential discovery and no simulation fallback.

Two sockets: router has scoped model requests; workers use the private socket.
Missing/corrupt state fails closed. A verified live worker cannot be recovered.
"""
import argparse
import contextlib
import fcntl
import json
import hashlib
import os
from pathlib import Path
import re
import socket
import socketserver
import struct
import subprocess
import threading
import time
import urllib.request

from controller import Controller, State, Conflict, Unsafe
from gateway import ExclusiveStore
from kubernetes_actuator import KubernetesActuator, IntentJournal, MutationUnsafe
from kubernetes_api import DeploymentAPI


def atomic(path, doc):
    path = Path(path)
    temp = path.with_suffix('.new')
    with temp.open('w') as stream:
        json.dump(doc, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def process_identity(pid):
    try:
        # comm may contain spaces/parentheses. Field 22 follows final ')'.
        return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
    except FileNotFoundError:
        return None


# Registered host-process workers that may take the GPU by parking the primary model (no Mesh deployment starts).
# The worker must be the MainPID of the named systemd unit; the controller verifies that identity.
HOST_WORKER_UNITS = {
    'game-worker': 'watoom-game-worker.service',
    'moss-image': 'watoom-moss-image.service',
}


def unit_state(job):
    if job in HOST_WORKER_UNITS:
        unit = HOST_WORKER_UNITS[job]
    elif re.fullmatch(r'[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}', job):
        unit = 'llama-mesh-' + job
    else:
        raise Unsafe('invalid job identity')
    r = subprocess.run(['systemctl', 'show', unit,
                        '--property=ActiveState', '--property=MainPID'],
                       capture_output=True, text=True, timeout=10)
    if r.returncode:
        raise Unsafe('cannot verify worker unit')
    return dict(line.split('=', 1) for line in r.stdout.splitlines() if '=' in line)


class TokenAPI(DeploymentAPI):
    def __init__(self, config):
        self.token_file = Path(config['token_file'])
        super().__init__(base_url=config['api_url'], namespace=config['namespace'],
                         token=self.token_file.read_text().strip(), ca_file=config['ca_file'],
                         allowed=config.get('models',(config['primary'], config['mesh'])))

    def _call(self, *args, **kw):
        self.token = self.token_file.read_text().strip()
        return super()._call(*args, **kw)


class ProductionActuator(KubernetesActuator):
    def __init__(self, api, journal, config, probe, sleep=time.sleep):
        super().__init__(api, journal, allowed=config.get('models',(config['primary'], config['mesh'])))
        self.config, self.probe, self.sleep = config, probe, sleep
        self.lock_check = None
        self.event = lambda action: None

    def _patch(self, name, replicas):
        if self.lock_check is None:
            raise Unsafe('production mutation requires the gateway ownership lock')
        self.lock_check()
        return super()._patch(name, replicas)

    def _get(self, name):
        obj = super()._get(name)
        expected = self.config.get('deployment_identity', {}).get(name)
        if expected:
            spec = dict(obj['spec'])
            spec.pop('replicas', None)
            digest = hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            if obj['metadata']['uid'] != expected['uid'] or digest != expected['spec_sha256']:
                raise Unsafe('deployment identity or model configuration changed')
        return obj

    def scale(self, name, replicas, generation):
        from inference_leases import leases
        if replicas==0 and leases(Path(self.config["state_root"])):
            raise Unsafe("In-flight or uncertain inference requests block GPU stop")
        if replicas == 1 and self._get(name)['spec']['replicas'] != 1:
            # Pod termination alone does not establish that device memory was released.
            result = subprocess.run(['nvidia-smi', '--query-gpu=memory.used',
                                     '--format=csv,noheader,nounits'],
                                    capture_output=True, text=True, timeout=15)
            if result.returncode or float(result.stdout.strip()) > self.config['released_gpu_max_mib']:
                raise Unsafe('GPU memory has not been released; Mesh activation refused')
        return super().scale(name, replicas, generation)

    def stopped(self, name):
        deadline = time.monotonic() + self.config['stop_timeout']
        while time.monotonic() < deadline:
            obj = self._get(name)
            if obj['spec']['replicas'] == 0 and obj.get('status', {}).get('replicas', 0) == 0:
                # A deployment status can lag terminating pods; probe actual pods.
                if self.probe(name, 'stopped'):
                    self.event('QWEN_STOPPED' if name == self.config['primary'] else 'MESH_STOPPED' if name == self.config['mesh'] else 'MODEL_STOPPED:'+name)
                    return True
            self.sleep(2)
        return False

    def healthy(self, name):
        deadline = time.monotonic() + self.config['startup_timeout']
        while time.monotonic() < deadline:
            obj = self._get(name)
            if (obj['spec']['replicas'] == 1 and obj.get('status', {}).get('readyReplicas') == 1
                    and obj.get('status', {}).get('observedGeneration', 0) >= obj['metadata']['generation']):
                if self.probe(name, 'healthy'):
                    self.event('QWEN_READY' if name == self.config['primary'] else 'MESH_READY' if name == self.config['mesh'] else 'MODEL_READY:'+name)
                    return True
            self.sleep(2)
        return False


class ScopedController(Controller):
    """Restore the primary only after every registered competing GPU is stopped."""
    def _restore(self, job, generation):
        try:
            if not self.actuator.fence_and_reconcile(generation):
                raise Unsafe('outstanding mutation cannot be fenced')
            for name in sorted(self.actuator.allowed - {self.primary}):
                obj=self.actuator._get(name)
                if name==self.mesh or obj['spec']['replicas']!=0:
                    self.actuator.scale(name,0,generation)
                if not self.actuator.stopped(name):raise Unsafe('competing GPU pods remain: '+name)
            self.actuator.scale(self.primary,1,generation)
            if not self.actuator.healthy(self.primary):raise Unsafe('Qwen inference verification failed')
        except BaseException:
            self.store.save(State('recovery-required',job,generation,True))
            raise
        self.store.save(State('qwen-ready',None,generation))


class Runtime:
    def __init__(self, config, api=None, probe=None, units=unit_state, identity=process_identity):
        from model_lifecycle import read_ledger, overlay
        self.base_config = json.loads(json.dumps(config))
        managed = read_ledger(config["state_root"])
        config = overlay(config, managed)
        self.c = config
        self.root = Path(config['state_root'])
        if api is None and config.get('cutover_required') is not True:
            raise Unsafe('production gateway requires a verified cutover proof')
        if config.get('cutover_required'):
            proof=json.loads((self.root/'cutover-proof.json').read_text())
            if proof.get('status')!='complete' or not proof.get('models') or any(record.get('status')!='acknowledged' for record in proof['models'].values()):
                raise Unsafe('legacy storage barrier is incomplete')
            for name,deployment_identity in config['deployment_identity'].items():
                if name in managed:
                    continue  # Explicit never-started enrollment is not a legacy acknowledgment.
                if proof['models'].get(name,{}).get('uid')!=deployment_identity['uid']:
                    raise Unsafe('cutover identity proof does not match deployment')
        self.store = ExclusiveStore(self.root)
        self.journal = IntentJournal(self.root / 'intents')
        self.api = api or TokenAPI(config)
        self.actuator = ProductionActuator(self.api, self.journal, config, probe or self.probe)
        self.actuator.lock_check = self.store._check
        self.controller = ScopedController(self.store, self.actuator, config['primary'], config['mesh'])
        self.units, self.identity = units, identity
        self.owner_path = self.root / 'worker.json'
        self.actuator.event = lambda action: self.audit(action, self.store.load())

    def probe(self, name, kind):
        if kind == 'idle':
            from inference_leases import idle
            return idle(self,name)
        if kind == 'stopped':
            # Read-only kubeconfig belongs to the dedicated controller principal.
            r = subprocess.run(['kubectl', '--kubeconfig', self.c['kubeconfig'],
                                '--cache-dir',str(self.root/'kube-cache'), '-n',self.c['namespace'],
                                'get', 'pods', '-l', 'app=' + name, '-o', 'json'],
                               capture_output=True, timeout=15)
            if r.returncode:
                return False
            pods = json.loads(r.stdout)['items']
            return not any(p['metadata'].get('deletionTimestamp') or
                           p.get('status', {}).get('phase') not in ('Succeeded', 'Failed') for p in pods)
        try:
            base = self.c['urls'][name]
            headers={"Content-Type":"application/json"}
            if name.startswith("llama-cpp-mm-"):
                key_file=self.c.get("managed_auth_file")
                if key_file!="/data/ai/private/model-manager/backend-key":return False
                headers["Authorization"]="Bearer "+Path(key_file).read_text().strip()
            with urllib.request.urlopen(base + '/health', timeout=10) as response:
                if json.load(response).get('status') != 'ok':
                    return False
            alias = self.c['aliases'][name]
            if self.c.get("backend_types",{}).get(name)=="sdxl":
                req=urllib.request.Request(base+"/validate",b"{}",headers)
                with urllib.request.urlopen(req,timeout=180) as response:
                    result=json.load(response)
                if not (result.get("status")=="generated" and result.get("model")==alias and result.get("width")==512 and result.get("height")==512):return False
                artifact=result.get("artifact","")
                if not re.fullmatch(r"[a-f0-9]{32}\.png",artifact):return False
                with urllib.request.urlopen(urllib.request.Request(base+"/artifacts/"+artifact,headers=headers),timeout=30) as response:png=response.read(16*1024*1024+1)
                return (len(png)<=16*1024*1024 and png[:8]==bytes([137,80,78,71,13,10,26,10]) and hashlib.sha256(png).hexdigest()==result.get("sha256"))
            payload = {'model': alias, 'messages': [{'role': 'user', 'content': 'Reply OK.'}],
                       'max_tokens': 128, 'stream': False}
            req = urllib.request.Request(base + '/v1/chat/completions', json.dumps(payload).encode(),
                                         headers)
            with urllib.request.urlopen(req, timeout=120) as response:
                result = json.load(response)
            # Reasoning-enabled models can return reasoning_content with empty content.
            # Still require a successful completion and non-empty generated output.
            if result.get('model') != alias or not isinstance(result.get('choices'), list) or not result['choices']:
                return False
            choice = result['choices'][0]
            if choice.get('finish_reason') not in ('stop', 'length'):
                return False
            message = choice.get('message') or {}
            return bool((message.get('content') or '').strip() or
                        (message.get('reasoning_content') or '').strip() or
                        (message.get('reasoning') or '').strip())
        except (OSError, ValueError, KeyError, IndexError):
            return False

    def audit(self, action, state):
        with (self.root / 'audit.jsonl').open('a') as stream:
            stream.write(json.dumps({'time': time.time(), 'action': action, 'phase': state.phase,
                                     'owner': state.owner, 'generation': state.generation,
                                     'uncertain': state.uncertain}, sort_keys=True) + '\n')
            stream.flush()
            os.fsync(stream.fileno())

    def verify_owner(self, job, pid, recovering=False):
        if recovering:
            owner = json.loads(self.owner_path.read_text())
            if owner['job'] != job:
                raise Unsafe('worker identity mismatch')
            if owner.get('kind') in ('router','operator'):
                if self.identity(owner['pid'])==owner['start']:
                    raise Unsafe('verified live process owner cannot be reclaimed')
                return
            unit = self.units(job)
            if unit.get('ActiveState') in ('active', 'activating') or int(unit.get('MainPID', 0)) != 0:
                raise Unsafe('verified live worker cannot be reclaimed')
            if self.identity(owner['pid']) == owner['start']:
                raise Unsafe('worker process remains alive')
            return
        unit = self.units(job)
        allowed_states = ('active','activating','deactivating') if job == 'game-worker' else ('active','deactivating')
        if unit.get('ActiveState') not in allowed_states or int(unit.get('MainPID', 0)) != pid:
            raise Unsafe('request is not from the active worker MainPID')
        start = self.identity(pid)
        if start is None:
            raise Unsafe('worker disappeared')
        return {'job': job, 'pid': pid, 'start': start}

    def request_model(self, request, pid):
        from inference_leases import prune
        prune(self,atomic)
        name=request['deployment']
        if name not in self.actuator.allowed or name==self.c['mesh']:
            raise Unsafe('router may select only registered non-Mesh models')
        state=self.store.load()
        if state.owner:
            owner=json.loads(self.owner_path.read_text())
            if owner.get('kind')!='router' or owner['pid']!=pid or owner['start']!=self.identity(pid):
                raise Conflict('another owner holds the GPU')
            # A fresh request from the same authenticated owner may reconcile its
            # failed transition. Never replay the uncertain scale request.
            self.controller._restore(state.owner,state.generation)
            state=self.store.load()
        elif state.uncertain or self.actuator.unknown:
            raise Unsafe('unowned unknown mutation outcome')
        if state.phase=='qwen-ready':current=self.c['primary']
        elif state.phase=='model-ready':current=json.loads((self.root/'selected-model.json').read_text())['deployment']
        else:raise Unsafe('unowned invalid lifecycle state')
        if current==name:return {'allowed':True}
        from inference_leases import leases
        if leases(self.root):raise Conflict("In-flight inference blocks model switch")
        if not self.actuator.probe(current,"idle"):raise Conflict("Actual backend work or unavailable idle proof blocks model switch")
        if request.get('allow_switch') is not True:raise Conflict('explicit model switch required')
        start=self.identity(pid)
        if start is None:raise Unsafe('router process ended')
        job='router-'+str(pid)+'-'+str(start)
        generation=state.generation+1
        atomic(self.owner_path,{'kind':'router','job':job,'pid':pid,'start':start})
        self.store.save(State('switching-model',job,generation))
        self.actuator.generation=generation
        self.audit('OWNERSHIP_ACQUIRED',self.store.load())
        try:
            for competitor in sorted(self.actuator.allowed-{name}):
                obj=self.actuator._get(competitor)
                if obj['spec']['replicas']!=0:self.actuator.scale(competitor,0,generation)
                if not self.actuator.stopped(competitor):raise Unsafe('competing GPU remains')
            if self.actuator._get(name)['spec']['replicas']!=1:self.actuator.scale(name,1,generation)
            if not self.actuator.healthy(name):raise Unsafe('requested model inference verification failed')
            atomic(self.root/'selected-model.json',{'deployment':name})
            self.store.save(State('qwen-ready' if name==self.c['primary'] else 'model-ready',None,generation))
            self.audit('OWNERSHIP_RELEASED',self.store.load())
        except BaseException:
            self.store.save(State('recovery-required',job,generation,True))
            raise
        return {'allowed':True}

    def reconciliation_selftest(self,pid):
        """Actual API metadata-only lost-ACK/fence test; never changes replicas."""
        state=self.store.load()
        if state.phase!='qwen-ready' or state.owner or state.uncertain or self.journal.pending():
            raise Conflict('selftest requires idle known-good primary ownership state')
        name=self.c['primary']
        before=self.actuator._get(name)
        if not self.actuator.probe(name,'healthy'):raise Unsafe('primary inference gate failed')
        start=self.identity(pid)
        if start is None:raise Unsafe('operator process ended')
        job='operator-'+str(pid)+'-'+str(start)
        generation=state.generation+1
        atomic(self.owner_path,{'kind':'operator','job':job,'pid':pid,'start':start})
        self.store.save(State('acquiring',job,generation))
        self.actuator.generation=generation
        original=self.api.patch
        captured=[]
        def lose_ack(deployment,ops):
            captured.append((deployment,ops))
            original(deployment,ops)
            raise TimeoutError('injected lost acknowledgement after actual metadata commit')
        try:
            self.api.patch=lose_ack
            try:self.actuator._patch(name,None)
            except TimeoutError:self.store.save(State('recovery-required',job,generation,True))
            finally:self.api.patch=original
            if not self.journal.pending():raise Unsafe('lost acknowledgement did not remain pending')
            if not self.actuator.fence_and_reconcile(generation):raise Unsafe('actual API fence failed')
            # Explicit negative probe: the old conditional metadata request must
            # fail at the real Kubernetes boundary after the new revision barrier.
            try:original(*captured[0])
            except Exception as error:
                if getattr(error,'status',None) not in (409,422):
                    raise Unsafe('stale revision rejection not demonstrated') from error
            else:raise Unsafe('stale metadata mutation unexpectedly accepted')
            after=self.actuator._get(name)
            if before['spec']!=after['spec']:raise Unsafe('metadata test changed model spec')
            if not self.actuator.probe(name,'healthy'):raise Unsafe('post-test primary inference failed')
            self.store.save(State('qwen-ready',None,generation))
            self.audit('REAL_API_RECONCILIATION_SELFTEST_PASS',self.store.load())
            return {'result':'PASS','replicas_unchanged':True,'stale_patch_rejected':True,'generation':generation}
        except BaseException:
            self.api.patch=original
            self.store.save(State('recovery-required',job,generation,True))
            raise

    def handle(self, request, *, private, pid, uid):
        if uid != 0:
            raise Unsafe('unauthorized peer UID')
        action = request.get('action')
        if not private and action not in ('status', 'can-use-qwen','request-model','begin-inference','end-inference'):
            raise Unsafe('router endpoint is read-only')
        with self.store.exclusive():
            if not (self.root / 'state.json').is_file():
                raise Unsafe('missing durable state; explicit initialization required')
            state = self.store.load()
            self.actuator.generation = state.generation
            self.actuator.unknown = bool(self.journal.pending())
            if action == 'status':
                # Reconcile completed accounting under the existing owner lock.
                # Never change GPU deployments or erase uncertain owner evidence.
                if not state.owner and not state.uncertain and not self.actuator.unknown:
                    __import__('inference_leases').prune(self,atomic)
                return dict(managed_enrollment_version=1, inference_lease_version=1, phase=state.phase, owner=state.owner, generation=state.generation,
                            uncertain=state.uncertain or self.actuator.unknown,
                            active_requests=len(__import__('inference_leases').leases(self.root)),
                            primary=self.c['primary'],
                            owner_kind=json.loads(self.owner_path.read_text()).get('kind','worker') if state.owner else None)
            if action in ("begin-inference","end-inference"):
                from inference_leases import handle
                return handle(self,request,pid,atomic)
            if action in ("enroll-model","retire-model"):
                from model_lifecycle import Lifecycle
                return Lifecycle(self,atomic).change(request)
            if action=='request-model':
                return self.request_model(request,pid)
            if action=='selftest-reconciliation':
                return self.reconciliation_selftest(pid)
            if action == 'can-use-qwen':
                if self.actuator.unknown:
                    raise Unsafe('unreconciled mutation intent')
                return {'allowed': self.controller.request_qwen()}
            job = request['job']
            if action == 'begin':
                if self.actuator.unknown:
                    raise Unsafe('unreconciled mutation intent')
                if state.phase != 'qwen-ready' or state.owner or state.uncertain:
                    raise Conflict('GPU busy or outcome unknown')
                owner = self.verify_owner(job, pid)
                # Save identity before acquisition; crash before state write cannot grant ownership.
                atomic(self.owner_path, owner)
                generation = self.controller.begin_specialist(job)
                self.audit('OWNERSHIP_ACQUIRED', self.store.load())
                return {'generation': generation}
            generation = request['generation']
            if type(generation) is not int or generation < 1:
                raise Conflict('invalid epoch')
            if (state.owner, state.generation) != (job, generation):
                raise Conflict('stale owner or epoch')
            if action == 'recover':
                self.verify_owner(job, pid, recovering=True)
                if state.phase in ('mesh-active','switching-model','cpu-active'):
                    # Proven worker death permits recovery from the active generation state.
                    self.store.save(State('recovery-required', job, generation, True))
                self.controller.recover(job, generation, owner_confirmed_ended=True)
            else:
                owner = self.verify_owner(job, pid)
                saved = json.loads(self.owner_path.read_text())
                if saved != owner:
                    raise Unsafe('worker process identity changed')
                if action == 'park-cpu':
                    if job not in HOST_WORKER_UNITS or state.phase != 'acquiring' or state.uncertain:
                        raise Unsafe('CPU parking requires an admitted host worker acquisition')
                    from inference_leases import leases
                    if leases(self.root) or not self.actuator.probe(self.c['primary'], 'idle'):
                        raise Conflict('Active inference or unavailable idle proof blocks CPU parking')
                    self.store.save(State('stopping-qwen', job, generation))
                    try:
                        self.actuator.scale(self.c['primary'], 0, generation)
                        if not self.actuator.stopped(self.c['primary']):
                            raise Unsafe('Primary model remains active')
                        self.store.save(State('cpu-active', job, generation))
                    except BaseException:
                        self.store.save(State('recovery-required', job, generation, True))
                        raise
                elif action == 'activate':
                    self.controller.switch_to_mesh(job, generation)
                elif action == 'asset-saved':
                    if state.phase != 'mesh-active' or state.uncertain:
                        raise Unsafe('asset completion requires active Mesh ownership')
                    self.audit('ASSET_SAVED', state)
                elif action == 'restore':
                    # Cancellation/failed activation also needs ordered reconciliation.
                    if state.phase != 'mesh-active':
                        self.store.save(State('restoring', job, generation, True))
                        self.controller._restore(job, generation)
                    else:
                        self.controller.begin_restore(job, generation)
                else:
                    raise Unsafe('unsupported action')
            self.audit(action, self.store.load())
            if self.store.load().phase == 'qwen-ready':
                self.audit('OWNERSHIP_RELEASED', self.store.load())
            return {'ok': True}


def serve(config):
    root = Path(config['state_root'])
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Lifetime singleton prevents old/new daemons simultaneously serving sockets.
    with (root / 'daemon.lock').open('a') as singleton:
        fcntl.flock(singleton, fcntl.LOCK_EX | fcntl.LOCK_NB)
        runtime = Runtime(config)
        servers = []
        for key, private in [('router_socket', False), ('worker_socket', True)]:
            path = Path(config[key])
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700 if private else 0o755)
            if path.exists():
                if not path.is_socket():
                    raise Unsafe('refuse to replace non-socket')
                path.unlink()  # Lifetime lock proves no old daemon can own it.
            def handler_factory(is_private):
                class Handler(socketserver.StreamRequestHandler):
                    def handle(self):
                        self.connection.settimeout(15)
                        pid, uid, _ = struct.unpack('3i', self.connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                        try:
                            line = self.rfile.readline(65537)
                            if len(line) > 65536 or not line.endswith(b'\n'):
                                raise Unsafe('invalid request framing')
                            result = {'result': runtime.handle(json.loads(line), private=is_private, pid=pid, uid=uid)}
                        except Exception as exc:
                            result = {'error': type(exc).__name__, 'detail': str(exc)}
                        self.wfile.write(json.dumps(result).encode() + b'\n')
                return Handler
            class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
                daemon_threads = False
                block_on_close = True
            server = Server(str(path), handler_factory(private))
            os.chmod(path, 0o600)
            servers.append(server)
            threading.Thread(target=server.serve_forever, daemon=True).start()
        observation_stop=threading.Event()
        def observe():
            from observability import publish
            while not observation_stop.is_set():
                try:
                    publish(root,config['observability_path'],config['primary'])
                except Exception as exc:
                    # A failed read-only export must never change ownership/recovery.
                    print(json.dumps({'event':'GPU_OBSERVATION_FAILED','error':type(exc).__name__}),flush=True)
                observation_stop.wait(5)
        observer=None
        if config.get('observability_path'):
            observer=threading.Thread(target=observe,daemon=True);observer.start()
        try:
            threading.Event().wait()
        finally:
            observation_stop.set()
            if observer:observer.join(timeout=6)
            for server in servers:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    serve(json.loads(Path(args.config).read_text()))
