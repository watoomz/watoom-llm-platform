"""Offline tests for Writing Studio: fake LLM router and fake MOSS over real HTTP, real skill files from the repo."""
import http.client
import json
import pathlib
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import writing_studio_service as ws  # noqa: E402

REPO_SKILLS = HERE.parents[2] / "ansible/roles/watoom-code/files/skills"


class FakeRouter:
    """/v1/models, /models/status, /models/load and an SSE /v1/chat/completions (mode ok|error|slow)."""

    def __init__(self, mode="ok"):
        self.mode, self.requests, self.loaded = mode, [], "swift-qwen38-coder"
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def _json(self, status, obj):
                raw = json.dumps(obj).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                if self.path == "/v1/models":
                    return self._json(200, {"data": [
                        {"id": "active-model", "name": "Active"},
                        {"id": "swift-qwen38-coder", "name": "Swift", "application_context": 100000},
                        {"id": "ornith-1.5-9b", "name": "Ornith", "application_context": 200000, "vision": True},
                        {"id": "llama-mesh", "name": "LLaMA-Mesh 8B"},
                        {"id": "mm-1664e7966537969a", "name": "ccore/Qwen3.5-4B-GLB-3D-Coder (x.gguf)"}]})
                if self.path == "/models/status":
                    return self._json(200, {"active_model": outer.loaded + "-q8" if outer.loaded == "ornith-1.5-9b" else outer.loaded,
                                            "active_aliases": [outer.loaded]})
                self._json(404, {})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
                outer.requests.append((self.path, body))
                if self.path == "/models/load":
                    time.sleep(0.05)
                    if body["model"] == "broken":
                        return self._json(503, {"error": "Unsafe: deployment identity changed"})
                    outer.loaded = body["model"]
                    return self._json(200, {"status": "loaded", "model": body["model"]})
                if outer.mode == "error":
                    return self._json(503, {"error": {"message": "GPU busy"}})
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
                            event({"choices": [{"delta": {"reasoning_content": "hmm "}}]})
                            threading.Event().wait(0.01)
                        return
                    event({"choices": [{"delta": {"reasoning_content": "Plan the chapter."}}]})
                    for word in ("The tide ", "went out ", "and the door ", "appeared."):
                        event({"choices": [{"delta": {"content": word}}]})
                    event({"choices": [{"delta": {}, "finish_reason": "stop"}], "timings": {"predicted_per_second": 42.0}})
                    self.wfile.write(b"data: [DONE]\n\n")
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base_url = "http://127.0.0.1:%d" % self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()


class FakeMoss:
    def __init__(self):
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _json(self, status, obj):
                raw = json.dumps(obj).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                outer.requests.append(("GET", self.path, None))
                if self.path == "/api/status":
                    return self._json(200, {"session": {"state": "idle"}})
                self._json(200, {"id": "a" * 32, "status": "done", "image": "b" * 32 + ".png"})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                outer.requests.append(("POST", self.path, body))
                self._json(202, {"id": "a" * 32, "status": "queued"})

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base_url = "http://127.0.0.1:%d" % self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()


class Studio(unittest.TestCase):
    def setUp(self, mode="ok"):
        self.router_fake, self.moss_fake = FakeRouter(mode), FakeMoss()
        self.tmp = tempfile.TemporaryDirectory()
        self.skills = ws.Skills(REPO_SKILLS)
        self.router = ws.Router(self.router_fake.base_url)
        self.writer = ws.Writer(self.router, self.skills, "swift-qwen38-coder", self.tmp.name)
        handler = ws.make_handler(self.skills, self.router, self.writer, ws.MossClient(self.moss_fake.base_url))
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.tmp.cleanup()

    def call(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Content-Type": "application/json"} if body is not None else {}
        h.update(headers or {})
        conn.request(method, path, json.dumps(body).encode() if body is not None else None, h)
        resp = conn.getresponse()
        raw = resp.read()
        conn.close()
        try:
            return resp.status, json.loads(raw)
        except ValueError:
            return resp.status, raw

    def wait(self, job_id):
        for _ in range(300):
            status, job = self.call("GET", "/api/job?id=" + job_id)
            if job["state"] not in ws.RUNNING:
                return job
            time.sleep(0.02)
        self.fail("job did not finish")

    def test_all_25_skills_load_from_the_repo(self):
        status, config = self.call("GET", "/api/config")
        self.assertEqual(status, 200)
        self.assertEqual(len(config["skills"]), 25)
        self.assertTrue(all(s["available"] for s in config["skills"]), [s["name"] for s in config["skills"] if not s["available"]])
        self.assertEqual({s["group"] for s in config["skills"]}, set(config["groups"]))
        self.assertEqual(config["art"]["defaults"]["steps"], 50)

    def test_form_skill_streams_and_saves(self):
        status, job = self.call("POST", "/api/write", {"skill": "chapter-writing", "fields": {"context": "A keeper.", "beats": "The door appears.", "length": "Outline only"}})
        self.assertEqual(status, 202)
        job = self.wait(job["id"])
        self.assertEqual((job["state"], job["content"]), ("done", "The tide went out and the door appeared."))
        path, body = self.router_fake.requests[-1]
        self.assertEqual((path, body["model"], body["stream"]), ("/v1/chat/completions", "swift-qwen38-coder", True))
        self.assertIn("=== Skill: Write a chapter ===", body["messages"][0]["content"])
        self.assertIn("Story so far:\nA keeper.", body["messages"][1]["content"])
        self.assertEqual(body["chat_template_kwargs"], {"enable_thinking": False})
        self.assertTrue((pathlib.Path(self.tmp.name) / (job["id"] + ".md")).is_file())
        status, raw = self.call("GET", "/api/job.md?id=" + job["id"])
        self.assertEqual(raw, b"The tide went out and the door appeared.")

    def test_chat_skill_sends_the_conversation(self):
        turns = [{"role": "user", "content": "An idea?"}, {"role": "assistant", "content": "A door."}, {"role": "user", "content": "Go on."}]
        status, job = self.call("POST", "/api/write", {"skill": "premise-workshop", "messages": turns, "model": "ornith-1.5-9b", "thinking": True})
        self.wait(job["id"])
        body = self.router_fake.requests[-1][1]
        self.assertEqual([m["role"] for m in body["messages"]], ["system", "user", "assistant", "user"])
        self.assertEqual((body["model"], body["chat_template_kwargs"]["enable_thinking"]), ("ornith-1.5-9b", True))

    def test_invalid_requests(self):
        for body in ({"skill": "nope", "fields": {"a": "b"}}, {"skill": "chapter-writing", "fields": {}},
                     {"skill": "premise-workshop", "messages": [{"role": "assistant", "content": "x"}]},
                     {"skill": "premise-workshop", "messages": [{"role": "system", "content": "x"}]},
                     {"skill": "chapter-writing", "fields": {"beats": "x"}, "model": "bad model!"}):
            status, err = self.call("POST", "/api/write", body)
            self.assertEqual(status, 400, body)
        status, _ = self.call("POST", "/api/write", {"skill": "chapter-writing", "fields": {"beats": "x"}},
                              {"Origin": "https://evil.example"})
        self.assertEqual(status, 403)

    def test_one_job_at_a_time_and_cancel(self):
        self.tearDown()
        self.setUp("slow")
        status, job = self.call("POST", "/api/write", {"skill": "premise-workshop", "messages": [{"role": "user", "content": "Hi"}]})
        status, err = self.call("POST", "/api/write", {"skill": "premise-workshop", "messages": [{"role": "user", "content": "Again"}]})
        self.assertEqual(status, 409)
        time.sleep(0.2)
        self.call("POST", "/api/cancel?id=" + job["id"], {})
        self.assertEqual(self.wait(job["id"])["state"], "cancelled")

    def test_router_error_is_reported(self):
        self.tearDown()
        self.setUp("error")
        status, job = self.call("POST", "/api/write", {"skill": "premise-workshop", "messages": [{"role": "user", "content": "Hi"}]})
        job = self.wait(job["id"])
        self.assertEqual(job["state"], "failed")
        self.assertIn("GPU busy", job["error"])

    def test_models_and_warmup(self):
        status, models = self.call("GET", "/api/models")
        self.assertEqual([m["id"] for m in models["models"]], ["swift-qwen38-coder", "ornith-1.5-9b"])  # no alias, mesh or GLB
        self.assertEqual(models["loaded"], "swift-qwen38-coder")
        status, warm = self.call("POST", "/api/warmup", {"model": "ornith-1.5-9b"})
        self.assertEqual((status, warm["state"]), (202, "loading"))
        for _ in range(100):
            models = self.call("GET", "/api/models")[1]
            if models["warmup"]["state"] != "loading":
                break
            time.sleep(0.02)
        self.assertEqual((models["warmup"]["state"], models["loaded"]), ("ready", "ornith-1.5-9b"))
        self.call("POST", "/api/warmup", {"model": "broken"})
        for _ in range(100):
            models = self.call("GET", "/api/models")[1]
            if models["warmup"]["state"] != "loading":
                break
            time.sleep(0.02)
        self.assertEqual(models["warmup"]["state"], "failed")
        self.assertIn("identity", models["warmup"]["error"])

    def test_art_wraps_style_and_uses_high_quality_defaults(self):
        status, _ = self.call("POST", "/api/art/generate", {"scene": "a keeper at the sea door", "style": "ink-noir", "size": "page"})
        self.assertEqual(status, 202)
        method, path, body = self.moss_fake.requests[-1]
        self.assertEqual((path, body["steps"], body["width"], body["height"]), ("/api/generate", 50, 832, 1216))
        self.assertTrue(body["scene"].startswith("high-contrast black and white") and "a keeper at the sea door" in body["scene"])
        self.call("POST", "/api/art/generate", {"scene": "x", "style": "none", "size": "square", "steps": "30", "seed": "7"})
        body = self.moss_fake.requests[-1][2]
        self.assertEqual((body["scene"], body["steps"], body["seed"]), ("x", 30, 7))
        self.assertEqual(self.call("POST", "/api/art/generate", {"scene": "x", "style": "nope"})[0], 400)

    def test_moss_proxy_is_allow_listed(self):
        self.assertEqual(self.call("GET", "/api/moss/status")[0], 200)
        self.assertEqual(self.call("POST", "/api/moss/session/start", {})[0], 202)
        self.assertEqual(self.call("GET", "/api/moss/gallery")[0], 404)
        self.assertEqual(self.call("POST", "/api/moss/gallery/" + "a" * 32 + "/hide", {})[0], 404)

    def test_restart_marks_running_jobs_interrupted(self):
        (pathlib.Path(self.tmp.name) / ("c" * 32 + ".json")).write_text(json.dumps({"id": "c" * 32, "state": "writing", "skill": "x", "created": 1}))
        writer = ws.Writer(self.router, self.skills, "m", self.tmp.name)
        self.assertEqual(writer.status("c" * 32)["state"], "failed")

    def test_page_is_served(self):
        status, raw = self.call("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"Warm up", raw)


if __name__ == "__main__":
    unittest.main()
