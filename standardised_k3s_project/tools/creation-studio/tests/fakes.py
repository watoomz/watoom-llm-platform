"""Offline fake HTTP backends standing in for Model Manager and MOSS Image Studio.

Neither fake does any real authentication/GPU work; they exist only so
creation_studio_service.py's proxying logic can be exercised without a live
Model Manager or MOSS Image Studio.
"""
import json
import os
import socketserver
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeModelManager:
    """Stands in for tools/model-manager/server.py's authenticated HTTP surface,
    under the same /model-manager-style prefix and cookie+CSRF login flow."""

    PREFIX = "/model-manager"

    def __init__(self, password="fixture-password-for-tests-only-long-enough", origin="https://glance.internal.homelab.example"):
        self.password, self.origin = password, origin
        self.csrf = "fixture-csrf-token"
        self.sessions = set()
        self.requests = []  # (method, path, headers-dict, body) for assertions
        self.models = [{"id": "m1", "revision": "r1", "repository": "stabilityai/stable-diffusion-xl-base-1.0",
                        "kind": "diffusion-pipeline", "registered": True}]
        self.jobs = []
        self.results = {}
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, status, obj, raw=None):
                body = raw if raw is not None else json.dumps(obj).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _path(self):
                return self.path.split("?", 1)[0][len(outer.PREFIX):] or "/"

            def do_GET(self):
                outer.requests.append(("GET", self._path(), dict(self.headers), None))
                path = self._path()
                cookie = self.headers.get("Cookie", "")
                if "mm_session=ok" not in cookie:
                    return self._send(401, {"error": "auth required"})
                if path == "/api/session":
                    return self._send(200, {"csrf": outer.csrf})
                if path == "/api/jobs":
                    return self._send(200, outer.jobs)
                if path == "/api/models":
                    return self._send(200, outer.models)
                if path.startswith("/api/result"):
                    job_id = self.path.split("id=", 1)[-1]
                    return self._send(200, outer.results.get(job_id, {"text": "no such result"}))
                self._send(404, {"error": "not found"})

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length)
                path = self._path()
                outer.requests.append(("POST", path, dict(self.headers), raw))
                if path == "/login":
                    from urllib.parse import parse_qs
                    form = parse_qs(raw.decode())
                    if self.headers.get("Origin") != outer.origin or form.get("password", [""])[0] != outer.password:
                        return self._send(401, {"error": "bad credentials"})
                    self.send_response(303)
                    self.send_header("Location", outer.PREFIX + "/")
                    self.send_header("Set-Cookie", "mm_session=ok; HttpOnly; Path=" + outer.PREFIX + "/")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                cookie = self.headers.get("Cookie", "")
                if "mm_session=ok" not in cookie:
                    return self._send(401, {"error": "auth required"})
                if self.headers.get("Origin") != outer.origin or self.headers.get("X-CSRF-Token") != outer.csrf:
                    return self._send(403, {"error": "csrf rejected"})
                if path == "/api/generate":
                    body = json.loads(raw)
                    job_id = "deadbeef" + body["id"]
                    outer.jobs.append({"id": job_id, "state": "GENERATION_VERIFIED", "selection": json.dumps(body)})
                    outer.results[job_id] = {"text": "generated: " + body["prompt"]}
                    return self._send(202, {"job": job_id})
                self._send(404, {"error": "not found"})

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        self.base_url = "http://127.0.0.1:%d%s" % (self.port, self.PREFIX)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class FakeMoss:
    """Stands in for tools/moss-image/moss_image_service.py's existing, unauthenticated HTTP API."""

    def __init__(self):
        self.requests = []
        self.presets = {"presets": [{"id": "kodak-portra-400", "category": "Film stocks", "name": "Kodak Portra 400",
                                     "prompt_look": "35mm color negative film photo.", "negative_extra": "digital"}]}
        self.status = {"engine_running": False, "session": {"state": "active"}}
        self.jobs = {}
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, status, obj):
                body = json.dumps(obj).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                path = self.path.split("?", 1)[0]
                outer.requests.append(("GET", path))
                if path == "/api/presets":
                    return self._send(200, outer.presets)
                if path == "/api/status":
                    return self._send(200, outer.status)
                if path.startswith("/api/jobs/"):
                    jid = path.rsplit("/", 1)[-1]
                    return self._send(200, outer.jobs.get(jid, {"status": "error", "error": {"message": "unknown"}}))
                if path == "/api/images/" + "f" * 32 + ".png":
                    body = b"\x89PNG\r\n\x1a\nFIXTURE"
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self._send(404, {"error": {"code": "not_found", "message": "not found"}})

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length)
                path = self.path.split("?", 1)[0]
                body = json.loads(raw) if raw else {}
                outer.requests.append(("POST", path, body))
                if path == "/api/generate":
                    jid = "f" * 32
                    outer.jobs[jid] = {"status": "done", "image": jid + ".png", "fraction": 1.0}
                    return self._send(202, {"id": jid, "status": "queued"})
                if path in ("/api/session/start", "/api/session/end"):
                    return self._send(202, {"state": "active" if path.endswith("start") else "ended"})
                self._send(404, {"error": {"code": "not_found", "message": "not found"}})

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        self.base_url = "http://127.0.0.1:%d" % self.port
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class FakeMeshBridge:
    """Stands in for opencode_mesh_bridge.py's Unix-socket wire protocol (one JSON object + newline
    in, one {"ok":..., "result"|"error":...} + newline out). Does not simulate the real UID check:
    MeshClient never sends any identity of its own, so there is nothing for this fake to check --
    that authorization happens on the real bridge's side via SO_PEERCRED, outside this process."""

    def __init__(self, socket_path):
        self.socket_path, self.requests, self.jobs = socket_path, [], {}
        outer = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                line = self.rfile.readline(16385)
                request = json.loads(line)
                outer.requests.append(request)
                try:
                    result = outer._execute(request)
                    reply = {"ok": True, "result": result}
                except Exception as exc:
                    reply = {"ok": False, "error": str(exc)}
                self.wfile.write(json.dumps(reply).encode() + b"\n")

        self.server = socketserver.ThreadingUnixStreamServer(socket_path, Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def _execute(self, request):
        op = request.get("operation")
        if op == "submit":
            job_id = "job-" + str(len(self.jobs))
            self.jobs[job_id] = {"job_id": job_id, "state": "complete", "prompt": request["prompt"]}
            return {"job_id": job_id, "state": "pending"}
        if op == "list":
            return {"jobs": list(self.jobs.values())}
        if op == "status":
            job = self.jobs.get(request.get("job_id"))
            if job is None:
                raise ValueError("unknown job")
            return {**job, "completion": True}
        if op == "retrieve":
            job = self.jobs.get(request.get("job_id"))
            if job is None:
                raise ValueError("unknown job")
            return {"job_id": job["job_id"], "artifacts": {"glb": "/assets/fixture.glb"}, "manifest": {"result": "PASS"}}
        raise ValueError("unsupported operation")

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass


class FakeRouter:
    """Stands in for the LLM router's /v1/chat/completions stream (llama-server SSE: reasoning_content deltas, then
    content deltas, a finish_reason, a usage chunk and [DONE]). mode: "ok", "error" (HTTP 503) or "slow" (keeps
    streaming reasoning until the client disconnects, for cancel tests)."""

    HTML = ("Here is the asset.\n```html\n<!DOCTYPE html>\n<html><head><script type=\"importmap\">{}</script></head>"
            "<body><button id=\"export\">Export GLB</button><script type=\"module\">1</script></body></html>\n```\n")

    def __init__(self, mode="ok"):
        self.mode = mode
        self.requests = []  # (path, headers-dict, json body)
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
                outer.requests.append((self.path, dict(self.headers), body))
                if outer.mode == "error":
                    raw = json.dumps({"error": {"message": "GPU owned or controller unavailable"}}).encode()
                    self.send_response(503)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Connection", "close")
                self.end_headers()

                def event(obj):
                    self.wfile.write(b"data: " + json.dumps(obj).encode() + b"\n\n")
                    self.wfile.flush()

                try:
                    if outer.mode == "slow":
                        for _ in range(2000):
                            event({"choices": [{"delta": {"reasoning_content": "thinking "}}]})
                            threading.Event().wait(0.01)
                        return
                    for word in ("I will build ", "a sword."):
                        event({"choices": [{"delta": {"reasoning_content": word}}]})
                    for i in range(0, len(outer.HTML), 40):
                        event({"choices": [{"delta": {"content": outer.HTML[i:i + 40]}}]})
                    event({"choices": [{"delta": {}, "finish_reason": "stop"}],
                           "timings": {"predicted_per_second": 101.5}})
                    event({"choices": [], "usage": {"completion_tokens": 321, "prompt_tokens": 99}})
                    self.wfile.write(b"data: [DONE]\n\n")
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base_url = "http://127.0.0.1:%d" % self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
