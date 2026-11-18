"""G3F client contracts. No Kubernetes calls or fallback to kubectl."""
import socket
import json

class ControllerUnavailable(RuntimeError):
    pass

class ControllerRejected(RuntimeError):
    pass

class GPUClient:
    def __init__(self, socket_path, timeout=10):
        self.socket_path = str(socket_path)
        self.timeout = timeout

    def call(self, action, **fields):
        req = {'action': action, **fields}
        payload = json.dumps(req, separators=(',', ':')).encode() + b'\n'
        if len(payload) > 65536:
            raise ValueError('request too large')
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout)
                sock.connect(self.socket_path)
                sock.sendall(payload)
                stream = sock.makefile('rb')
                raw = stream.readline(65537)
                if not raw or len(raw) > 65536 or not raw.endswith(b'\n'):
                    raise ControllerUnavailable('missing or oversized response')
        except (OSError, TimeoutError) as exc:
            raise ControllerUnavailable('controller unreachable; do not switch models independently') from exc
        try:
            response = json.loads(raw)
        except ValueError as exc:
            raise ControllerUnavailable('invalid controller response') from exc
        if not isinstance(response, dict):
            raise ControllerUnavailable('unexpected controller response')
        if 'error' in response:
            raise ControllerRejected(str(response['error'])+': '+str(response.get('detail','controller rejected')))
        if 'result' not in response:
            raise ControllerUnavailable('controller response missing result')
        return response['result']

class RouterAdapter:
    """Router may check eligibility, but has NO direct scaling fallback."""
    def __init__(self, client):
        self.client = client

    def ensure_primary_available(self):
        result = self.client.call('can-use-qwen')
        if result.get('allowed') is not True:
            raise ControllerRejected('primary GPU not available')
        return True

    def ensure_specialist(self):
        raise ControllerRejected('specialist activation is worker-only; router must not scale')

class MeshWorkerAdapter:
    """Only bounded lifecycle calls; the host worker owns the job ID.

    No retry of activate/restore after uncertain transport outcome.
    """
    def __init__(self, client):
        self.client = client

    def begin(self, job_id):
        result = self.client.call('begin', job=job_id)
        if not isinstance(result.get('generation'), int):
            raise ControllerUnavailable('invalid generation acknowledgement')
        return result['generation']

    def activate(self, job_id, generation):
        return self.client.call('activate', job=job_id, generation=generation)

    def restore(self, job_id, generation):
        return self.client.call('restore', job=job_id, generation=generation)

    def status(self):
        return self.client.call('status')
