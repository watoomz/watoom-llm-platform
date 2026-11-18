"""Offline GPU ownership gateway. No Kubernetes client or production deployment path.
Unix peer authentication, cross-process exclusive file locking and persistent state.
For simulation and client-contract tests only.
"""
import contextlib
import fcntl
import json
import os
from pathlib import Path
import socket
import socketserver
import struct
import threading
from controller import Controller, Conflict, Unsafe
from durable_store import DurableStore

class ExclusiveStore:
    """Ensures only a lock holder reads/writes state and all RPCs serialize."""
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock_path = self.root / 'owner.lock'
        self.store = DurableStore(self.root / 'state.json')
        self.local = threading.local()

    @contextlib.contextmanager
    def exclusive(self):
        # Flock is per-open-file-description; use fresh FD for each request.
        with open(self.lock_path, 'a+b') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            self.local.held = True
            try:
                yield
            finally:
                self.local.held = False
                fcntl.flock(stream, fcntl.LOCK_UN)

    def _check(self):
        if not getattr(self.local, 'held', False):
            raise Unsafe('durable state access requires ownership lock')

    def load(self):
        self._check()
        return self.store.load()

    def save(self, state):
        self._check()
        return self.store.save(state)

class SimulatedActuator:
    """Explicitly offline. Rejects production deployment names."""
    def __init__(self):
        self.replicas = {'qwen':1, 'mesh':0}
        self.pending = False
        self.operations = []
    def scale(self, name, replicas, generation):
        if name not in self.replicas or replicas not in (0,1):
            raise Unsafe('simulation only')
        if self.pending:
            raise Unsafe('unknown in-flight write')
        self.operations.append((generation,name,replicas))
        self.replicas[name] = replicas
    def stopped(self, name):
        return self.replicas[name] == 0
    def healthy(self, name):
        return self.replicas[name] == 1
    def fence_and_reconcile(self, generation):
        return not self.pending

class Gateway:
    def __init__(self, root, actuator=None):
        self.store = ExclusiveStore(root)
        self.actuator = actuator if actuator is not None else SimulatedActuator()
        self.controller = Controller(self.store, self.actuator, 'qwen', 'mesh')

    def handle(self, request):
        if not isinstance(request, dict) or not isinstance(request.get('action'),str):
            raise ValueError('invalid request')
        action = request['action']
        with self.store.exclusive():
            if action == 'status':
                s = self.store.load()
                return {'phase':s.phase,'owner':s.owner,'generation':s.generation,'uncertain':s.uncertain}
            if action == 'begin':
                return {'generation':self.controller.begin_specialist(request['job'])}
            if action == 'activate':
                self.controller.switch_to_mesh(request['job'],request['generation'])
                return {'ok':True}
            if action == 'restore':
                self.controller.begin_restore(request['job'],request['generation'])
                return {'ok':True}
            if action == 'can-use-qwen':
                return {'allowed':self.controller.request_qwen()}
            # Recovery is intentionally NOT exposed through RPC: confirmation
            # of worker death is not an assertion an untrusted client can make.
            raise ValueError('unsupported action')

class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        uid = struct.unpack('3i',self.request.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))[1]
        if uid not in self.server.allowed_uids:
            self.wfile.write(b'{"error":"permission denied"}\n')
            return
        line = self.rfile.readline(65537)
        if len(line)>65536:
            return
        try:
            request=json.loads(line)
            answer={'result':self.server.gateway.handle(request)}
        except (ValueError,KeyError,Conflict,Unsafe,TypeError) as exc:
            answer={'error':type(exc).__name__,'detail':str(exc)}
        self.wfile.write(json.dumps(answer,sort_keys=True).encode()+b'\n')

class Server(socketserver.ThreadingMixIn,socketserver.UnixStreamServer):
    daemon_threads=True
    def __init__(self, socket_path, gateway, allowed_uids):
        self.gateway=gateway
        self.allowed_uids=frozenset(allowed_uids)
        self.socket_path=Path(socket_path)
        if self.socket_path.exists():
            raise FileExistsError('refuse unlink of existing socket')
        super().__init__(str(self.socket_path),Handler)
        os.chmod(self.socket_path,0o600)
    def server_close(self):
        # Socket pathname is deliberately retained; caller handles cleanup
        # after verifying process termination. No unsafe unlink on restart.
        super().server_close()

def request(socket_path, message):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
        s.connect(str(socket_path))
        s.sendall(json.dumps(message).encode()+b'\n')
        data=b''
        while not data.endswith(b'\n'):
            part=s.recv(4096)
            if not part:break
            data+=part
            if len(data)>65536:raise ValueError('oversized response')
        return json.loads(data)
