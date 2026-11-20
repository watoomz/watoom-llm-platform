#!/usr/bin/env python3
"""Writing Studio: creative writing and graphic-novel art, one page for the 25 creative-writing skills (T-0099).

Stdlib only, same shape as tools/creation-studio: a host service bound to the k3s bridge, a Glance route, one
self-contained page and offline tests with fakes. It owns no generation backend:

  - Writing goes to the existing LLM router (OpenAI-compatible chat completions). The system prompt is the chosen
    skill's own SKILL.md (copied from the repository by the role), so the studio and WatooM Code share one source.
    Answers stream server-side in a background thread (one job at a time) so a long chapter survives page reloads;
    the browser polls /api/job. Form skills turn their fields into one request; chat skills keep a conversation.
  - Model switch and warm-up: the page lists the router's language models and what is loaded now
    (/v1/models, /models/status); "Warm up" asks the router to load the chosen model (POST /models/load), which in
    turn asks the GPU controller for the switch. Nothing GPU-side is reimplemented here.
  - Graphic-novel art is proxied to the existing MOSS Image Studio API (allow-listed paths only, exactly as
    Creation Studio does), with comic/graphic-novel style wrappers and high-quality defaults (50 steps). The MOSS
    GPU session (its own warm-up) is started and ended through the same proxy.
"""
import argparse
import http.client
import json
import pathlib
import re
import socket
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = pathlib.Path(__file__).resolve().parent
MAX_BODY = 256 * 1024
JOB_ID = re.compile(r"^[0-9a-f]{32}$")
SKILL_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
MODEL_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
FIELD_MAX = 60000
TURNS_MAX = 40
TAIL = 4000
SKILL_MAX = 40000
RUNNING = ("queued", "waiting", "thinking", "writing")
# Not writing models: 3D mesh and the GLB page coder live in Creation Studio.
EXCLUDED_MODEL = re.compile(r"mesh|glb-3d-coder|GLB-3D-Coder", re.I)

STUDIO_PREAMBLE = (
    "You are working inside the WatooM Writing Studio, a web page. You have no tools, files, scripts or project "
    "directory here: when the skill below describes files, registries or scripts, produce the content itself directly "
    "in your answer instead (as Markdown). Work only from what the writer gives you, ask briefly when something "
    "essential is missing, and never claim to have saved or run anything. Write in the writer's language.\n\n"
    "=== Skill: %s ===\n%s"
)

MOSS_GET = (
    re.compile(r"^/api/status$"),
    re.compile(r"^/api/config$"),
    re.compile(r"^/api/jobs/[0-9a-f]{32}$"),
    re.compile(r"^/api/images/[0-9a-f]{32}\.png$"),
)
MOSS_POST = (
    re.compile(r"^/api/generate$"),
    re.compile(r"^/api/session/start$"),
    re.compile(r"^/api/session/end$"),
    re.compile(r"^/api/jobs/[0-9a-f]{32}/cancel$"),
)


class ApiError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


# ---------------------------------------------------------------- skills
def front_matter(text):
    """(fields, body) of a SKILL.md: the simple `key: value` lines of its front matter and the text after it."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fields = {}
    for line in text[3:end].splitlines():
        m = re.match(r"^([A-Za-z_-]+):\s*(.*)$", line)
        if m:
            fields[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return fields, text[end + 4:].lstrip("\n")


class Skills:
    """The panel definitions (skills.json) joined with each skill's SKILL.md from --skills-dir."""

    def __init__(self, skills_dir, catalog_path=HERE / "skills.json"):
        self.catalog = json.loads(pathlib.Path(catalog_path).read_text(encoding="utf-8"))
        self.dir = pathlib.Path(skills_dir)
        self.prompts, self.available = {}, {}
        for name in self.catalog["skills"]:
            path = self.dir / name / "SKILL.md"
            try:
                fields, body = front_matter(path.read_text(encoding="utf-8"))
            except OSError:
                self.available[name] = False
                continue
            self.available[name] = True
            self.prompts[name] = (fields.get("description", ""), body[:SKILL_MAX])

    def config(self):
        skills = []
        for name, spec in self.catalog["skills"].items():
            skills.append({"name": name, "group": spec["group"], "title": spec["title"], "mode": spec["mode"],
                           "intro": spec.get("intro", ""), "fields": spec.get("fields", []),
                           "starter": spec.get("starter", ""), "available": self.available.get(name, False),
                           "description": self.prompts.get(name, ("", ""))[0]})
        return {"groups": self.catalog["groups"], "skills": skills,
                "art": {"styles": self.catalog["art_styles"], "negative": self.catalog["art_negative"],
                        "sizes": self.catalog["art_sizes"], "defaults": self.catalog["art_defaults"]}}

    def system_prompt(self, name):
        spec = self.catalog["skills"].get(name)
        if spec is None or name not in self.prompts:
            raise ApiError(400, "invalid_params", "unknown or unavailable skill")
        return STUDIO_PREAMBLE % (spec["title"], self.prompts[name][1])

    def messages(self, name, body):
        """Chat messages for one request: the skill's system prompt plus the writer's form fields or conversation."""
        spec = self.catalog["skills"].get(name)
        if spec is None:
            raise ApiError(400, "invalid_params", "unknown skill")
        system = {"role": "system", "content": self.system_prompt(name)}
        if spec["mode"] == "chat" or body.get("messages"):
            turns = body.get("messages")
            if not isinstance(turns, list) or not turns or len(turns) > TURNS_MAX:
                raise ApiError(400, "invalid_params", "messages must be a non-empty list of at most %d turns" % TURNS_MAX)
            clean = []
            for turn in turns:
                if not isinstance(turn, dict) or turn.get("role") not in ("user", "assistant") \
                        or not isinstance(turn.get("content"), str) or len(turn["content"]) > FIELD_MAX:
                    raise ApiError(400, "invalid_params", "each turn needs role user|assistant and text content")
                clean.append({"role": turn["role"], "content": turn["content"]})
            if clean[-1]["role"] != "user":
                raise ApiError(400, "invalid_params", "the last turn must be the writer's")
            return [system] + clean
        values = body.get("fields")
        if not isinstance(values, dict):
            raise ApiError(400, "invalid_params", "fields are required")
        parts = ["Task: " + spec["title"]]
        for field in spec.get("fields", []):
            value = values.get(field["id"], "")
            if not isinstance(value, str) or len(value) > FIELD_MAX:
                raise ApiError(400, "invalid_params", "field %s must be text" % field["id"])
            if value.strip():
                parts.append("%s:\n%s" % (field["label"], value.strip()))
        extra = values.get("_extra", "")
        if isinstance(extra, str) and extra.strip():
            parts.append("Additional instructions:\n" + extra.strip()[:FIELD_MAX])
        if len(parts) == 1:
            raise ApiError(400, "invalid_params", "fill in at least one field")
        return [system, {"role": "user", "content": "\n\n".join(parts)}]


# ---------------------------------------------------------------- router
class Router:
    """The existing LLM router: model list, current model, warm-up (load) and streamed chat completions."""

    def __init__(self, base_url, timeout=30):
        parsed = urllib.parse.urlsplit(base_url)
        if parsed.scheme != "http" or not parsed.hostname:
            raise ValueError("router base url must be absolute http://host:port")
        self.host, self.port, self.prefix, self.timeout = parsed.hostname, parsed.port or 80, parsed.path.rstrip("/"), timeout
        self._lock = threading.Lock()
        self.warmup = {"state": "idle", "model": None, "started": None, "finished": None, "error": None}

    def _json(self, method, path, body=None, timeout=None):
        conn = http.client.HTTPConnection(self.host, self.port, timeout=timeout or self.timeout)
        try:
            data = json.dumps(body).encode() if body is not None else None
            conn.request(method, self.prefix + path, data, {"Content-Type": "application/json"} if data else {})
            resp = conn.getresponse()
            raw = resp.read()
            try:
                value = json.loads(raw or b"{}")
            except ValueError:
                value = {"error": raw.decode("utf-8", "replace")[:300]}
            return resp.status, value
        except (OSError, http.client.HTTPException) as exc:
            raise ApiError(503, "router_unreachable", "LLM router is unreachable: %s" % exc)
        finally:
            conn.close()

    def models(self):
        status, value = self._json("GET", "/v1/models")
        if status != 200:
            raise ApiError(502, "router_error", "LLM router HTTP %d" % status)
        rows = [{"id": m["id"], "name": m.get("name") or m["id"], "context": m.get("application_context"),
                 "vision": m.get("vision")} for m in value.get("data", [])
                if MODEL_ID.match(m.get("id", "")) and m["id"] != "active-model"
                and not EXCLUDED_MODEL.search(m["id"] + " " + (m.get("name") or ""))]
        loaded = None
        try:
            status, current = self._json("GET", "/models/status")
            if status == 200:
                # the router reports its canonical id plus the public aliases; the page lists aliases
                ids = {row["id"] for row in rows}
                names = [current.get("active_model")] + list(current.get("active_aliases") or [])
                loaded = next((n for n in names if n in ids), current.get("active_model"))
        except ApiError:
            pass
        with self._lock:
            warm = dict(self.warmup)
        return {"models": rows, "loaded": loaded, "warmup": warm}

    def warm(self, model):
        if not isinstance(model, str) or not MODEL_ID.match(model):
            raise ApiError(400, "invalid_params", "a router model id is required")
        with self._lock:
            if self.warmup["state"] == "loading":
                raise ApiError(409, "busy", "already warming up %s" % self.warmup["model"])
            self.warmup = {"state": "loading", "model": model, "started": time.time(), "finished": None, "error": None}
        threading.Thread(target=self._warm, args=(model,), daemon=True).start()
        with self._lock:
            return dict(self.warmup)

    def _warm(self, model):
        try:
            # the router holds this until the GPU controller has switched (a 27B model loads in minutes from disk)
            status, value = self._json("POST", "/models/load", {"model": model}, timeout=1800)
            if status == 200 and value.get("status") == "loaded":
                result = {"state": "ready", "error": None}
            else:
                result = {"state": "failed", "error": (value.get("error") if isinstance(value, dict) else None) or "HTTP %d" % status}
        except ApiError as exc:
            result = {"state": "failed", "error": exc.message}
        with self._lock:
            self.warmup.update(result, finished=time.time())

    def stream(self, body, request_id):
        conn = http.client.HTTPConnection(self.host, self.port, timeout=1800)
        conn.request("POST", self.prefix + "/v1/chat/completions", json.dumps(body).encode(),
                     {"Content-Type": "application/json", "Accept": "text/event-stream", "X-Watoom-Request-Id": request_id})
        return conn


# ---------------------------------------------------------------- writing jobs
class Writer:
    """One writing job at a time, streamed from the router in a background thread; the page polls status()."""

    def __init__(self, router, skills, default_model, output_dir=""):
        self.router, self.skills, self.default_model = router, skills, default_model
        self.output_dir = pathlib.Path(output_dir) if output_dir else None
        self._lock = threading.Lock()
        self._jobs = {}
        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            for meta in sorted(self.output_dir.glob("*.json")):
                try:
                    job = json.loads(meta.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if JOB_ID.match(job.get("id", "")):
                    if job.get("state") in RUNNING:
                        job["state"], job["error"] = "failed", "interrupted by a Writing Studio restart"
                    self._jobs[job["id"]] = job

    def submit(self, body):
        skill = body.get("skill")
        if not isinstance(skill, str) or not SKILL_NAME.match(skill):
            raise ApiError(400, "invalid_params", "skill is required")
        model = body.get("model") or self.default_model
        if not isinstance(model, str) or not MODEL_ID.match(model):
            raise ApiError(400, "invalid_params", "invalid model id")
        messages = self.skills.messages(skill, body)
        thinking = bool(body.get("thinking", False))
        with self._lock:
            busy = [j for j in self._jobs.values() if j["state"] in RUNNING]
            if busy:
                raise ApiError(409, "busy", "a writing job is already running (%s); wait for it or cancel it" % busy[0]["id"])
            job = {"id": uuid.uuid4().hex, "skill": skill, "model": model, "thinking": thinking, "state": "queued",
                   "created": time.time(), "first_token": None, "finished": None, "reasoning_chars": 0,
                   "content_chars": 0, "reasoning_tail": "", "content": "", "error": None, "finish_reason": None,
                   "usage": None, "timings": None, "request": messages[-1]["content"][:2000],
                   "_messages": messages, "_cancel": False, "_conn": None}
            self._jobs[job["id"]] = job
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return self.status(job["id"])

    def status(self, job_id):
        job = self._get(job_id)
        with self._lock:
            out = {k: v for k, v in job.items() if not k.startswith("_")}
        out["elapsed_seconds"] = round((out.get("finished") or time.time()) - out.get("created", time.time()), 1)
        out.setdefault("content", "")
        return out

    def jobs(self):
        with self._lock:
            ids = sorted(self._jobs, key=lambda i: self._jobs[i]["created"], reverse=True)[:40]
        result = []
        for i in ids:
            row = self.status(i)
            row["content"] = row["content"][:300]
            result.append(row)
        return result

    def cancel(self, job_id):
        job = self._get(job_id)
        with self._lock:
            if job["state"] not in RUNNING:
                raise ApiError(409, "not_running", "job is not running")
            job["_cancel"] = True
            conn = job["_conn"]
        if conn is not None:
            try:
                conn.sock and conn.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        return self.status(job_id)

    def _get(self, job_id):
        if not isinstance(job_id, str) or not JOB_ID.match(job_id):
            raise ApiError(400, "invalid_params", "a 32-hex job id is required")
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise ApiError(404, "not_found", "no such job")
        return job

    def _update(self, job, **changes):
        with self._lock:
            job.update(changes)

    def _run(self, job):
        body = {"model": job["model"], "stream": True, "stream_options": {"include_usage": True},
                "messages": job["_messages"], "chat_template_kwargs": {"enable_thinking": job["thinking"]}}
        content, tail = [], ""
        conn = None
        try:
            self._update(job, state="waiting")
            conn = self.router.stream(body, "writing-studio-" + job["id"])
            self._update(job, _conn=conn)
            resp = conn.getresponse()
            if resp.status != 200:
                raw = resp.read(4096)
                try:
                    message = json.loads(raw)["error"]
                    message = message.get("message") if isinstance(message, dict) else message
                except (ValueError, KeyError, TypeError):
                    message = raw.decode("utf-8", "replace")[:300]
                raise ApiError(502, "router_error", "LLM router HTTP %d: %s" % (resp.status, message or ""))
            for line in resp:
                if job["_cancel"]:
                    break
                line = line.strip()
                if not line.startswith(b"data:"):
                    continue
                raw = line[5:].strip()
                if raw == b"[DONE]":
                    break
                try:
                    event = json.loads(raw)
                except ValueError:
                    continue
                changes = {}
                if event.get("usage"):
                    changes["usage"] = event["usage"]
                if event.get("timings"):
                    changes["timings"] = event["timings"]
                for choice in event.get("choices") or []:
                    delta = choice.get("delta") or {}
                    thought, text = delta.get("reasoning_content") or "", delta.get("content") or ""
                    if (thought or text) and job["first_token"] is None:
                        changes["first_token"] = time.time()
                    if thought:
                        tail = (tail + thought)[-TAIL:]
                        changes.update(state="thinking", reasoning_tail=tail, reasoning_chars=job["reasoning_chars"] + len(thought))
                    if text:
                        content.append(text)
                        changes.update(state="writing", content="".join(content), content_chars=job["content_chars"] + len(text))
                    if choice.get("finish_reason"):
                        changes["finish_reason"] = choice["finish_reason"]
                if changes:
                    self._update(job, **changes)
            if job["_cancel"]:
                raise ApiError(499, "cancelled", "cancelled")
            if not content:
                raise ApiError(502, "empty", "the model returned no text (finish reason: %s)" % job["finish_reason"])
            self._update(job, state="done")
        except ApiError as exc:
            self._update(job, state="cancelled" if exc.code == "cancelled" else "failed",
                         error=None if exc.code == "cancelled" else exc.message)
        except (OSError, http.client.HTTPException) as exc:
            self._update(job, state="cancelled" if job["_cancel"] else "failed",
                         error=None if job["_cancel"] else "LLM router stream failed: %s" % exc)
        finally:
            if conn is not None:
                conn.close()
            self._update(job, _conn=None, finished=time.time())
            self._persist(job)

    def _persist(self, job):
        if not self.output_dir:
            return
        try:
            meta = {k: v for k, v in job.items() if not k.startswith("_")}
            (self.output_dir / (job["id"] + ".json")).write_text(json.dumps(meta, indent=1), encoding="utf-8")
            if job.get("content"):
                (self.output_dir / (job["id"] + ".md")).write_text(job["content"], encoding="utf-8")
        except OSError as exc:
            self._update(job, error=(job.get("error") or "") + " (could not save the result: %s)" % exc)


# ---------------------------------------------------------------- MOSS
class MossClient:
    """Allow-listed passthrough to the existing MOSS Image Studio API, as Creation Studio does it."""

    def __init__(self, base_url, timeout=30):
        parsed = urllib.parse.urlsplit(base_url)
        if parsed.scheme != "http" or not parsed.hostname:
            raise ValueError("moss base url must be absolute http://host:port")
        self.host, self.port, self.timeout = parsed.hostname, parsed.port or 80, timeout

    def request(self, method, path, body=None):
        allow = MOSS_GET if method == "GET" else MOSS_POST
        if not any(p.match(path) for p in allow):
            raise ApiError(404, "not_found", "not found")
        conn = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        try:
            headers, data = {}, None
            if body is not None:
                data = json.dumps(body).encode()
                headers["Content-Type"] = "application/json"
            conn.request(method, path, data, headers)
            resp = conn.getresponse()
            return resp.status, resp.getheader("Content-Type", "application/octet-stream"), resp.read()
        except (OSError, http.client.HTTPException) as exc:
            raise ApiError(503, "moss_unreachable", "MOSS Image Studio is unreachable: %s" % exc)
        finally:
            conn.close()


def art_request(catalog, body):
    """A MOSS generate body: the scene wrapped in the chosen graphic-novel style, high-quality defaults."""
    scene = body.get("scene")
    if not isinstance(scene, str) or not scene.strip():
        raise ApiError(400, "invalid_params", "scene is required")
    style = next((s for s in catalog["art_styles"] if s["id"] == body.get("style", "none")), None)
    if style is None:
        raise ApiError(400, "invalid_params", "unknown style")
    size = next((s for s in catalog["art_sizes"] if s["id"] == body.get("size", "page")), None)
    if size is None:
        raise ApiError(400, "invalid_params", "unknown size")
    defaults = catalog["art_defaults"]
    text = " ".join(x for x in (style["prefix"], scene.strip(), style["suffix"]) if x)
    out = {"scene": text, "negative": body.get("negative", catalog["art_negative"]), "width": size["width"],
           "height": size["height"], "steps": defaults["steps"], "cfg": defaults["cfg"], "sampler": defaults["sampler"]}
    for key, kind in (("steps", int), ("cfg", float), ("seed", int)):
        if key in body and body[key] not in (None, ""):
            try:
                out[key] = kind(body[key])
            except (TypeError, ValueError):
                raise ApiError(400, "invalid_params", "%s must be a number" % key)
    if not isinstance(out["negative"], str):
        raise ApiError(400, "invalid_params", "negative must be text")
    return out


# ---------------------------------------------------------------- HTTP
def make_handler(skills, router, writer, moss):
    page = (HERE / "web" / "index.html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        server_version = "writing-studio"

        def log_message(self, *args):
            pass

        def _send(self, status, body, ctype="application/json", extra=None):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status, obj):
            self._send(status, json.dumps(obj).encode())

        def _body(self):
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                raise ApiError(415, "unsupported", "Content-Type must be application/json")
            origin = self.headers.get("Origin")
            host = self.headers.get("X-Forwarded-Host") or self.headers.get("Host") or ""
            if origin and urllib.parse.urlsplit(origin).netloc != host:
                raise ApiError(403, "cross_origin", "cross-origin request refused")
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                raise ApiError(413, "too_large", "request body too large")
            try:
                value = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                raise ApiError(400, "invalid_params", "body is not valid JSON")
            if not isinstance(value, dict):
                raise ApiError(400, "invalid_params", "body must be a JSON object")
            return value

        def _route(self, method):
            path = self.path.split("?", 1)[0]
            query = urllib.parse.parse_qs(self.path[len(path):].lstrip("?"))
            job_id = query.get("id", [""])[0]
            if method == "GET" and path in ("/", "/index.html"):
                return self._send(200, page, "text/html; charset=utf-8")
            if method == "GET" and path == "/api/config":
                config = skills.config()
                config["default_model"] = writer.default_model
                return self._json(200, config)
            if method == "GET" and path == "/api/models":
                return self._json(200, router.models())
            if method == "POST" and path == "/api/warmup":
                return self._json(202, router.warm(self._body().get("model")))
            if method == "GET" and path == "/api/jobs":
                return self._json(200, writer.jobs())
            if method == "GET" and path == "/api/job":
                return self._json(200, writer.status(job_id))
            if method == "GET" and path == "/api/job.md":
                job = writer.status(job_id)
                return self._send(200, job["content"].encode("utf-8"), "text/markdown; charset=utf-8",
                                  {"Content-Disposition": 'attachment; filename="%s-%s.md"' % (job["skill"], job_id[:8])})
            if method == "POST" and path == "/api/write":
                return self._json(202, writer.submit(self._body()))
            if method == "POST" and path == "/api/cancel":
                return self._json(200, writer.cancel(job_id))
            if method == "POST" and path == "/api/art/generate":
                status, ctype, raw = moss.request("POST", "/api/generate", art_request(skills.catalog, self._body()))
                return self._send(status, raw, ctype)
            if path.startswith("/api/moss/"):
                sub = "/api/" + path[len("/api/moss/"):]
                body = self._body() if method == "POST" else None
                status, ctype, raw = moss.request(method, sub, body)
                return self._send(status, raw, ctype)
            raise ApiError(404, "not_found", "not found")

        def _handle(self, method):
            try:
                self._route(method)
            except ApiError as exc:
                self._json(exc.status, {"error": {"code": exc.code, "message": exc.message}})
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as exc:
                self._json(500, {"error": {"code": "internal", "message": type(exc).__name__}})

        def do_GET(self):
            self._handle("GET")

        def do_POST(self):
            self._handle("POST")

    return Handler


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8793)
    ap.add_argument("--router-base", default="http://10.243.133.2:8000", help="LLM router base URL (its ClusterIP)")
    ap.add_argument("--default-model", default="swift-qwen38-coder", help="router model id preselected on the page")
    ap.add_argument("--skills-dir", default=str(HERE / "skills"), help="directory with <skill>/SKILL.md for the 25 skills")
    ap.add_argument("--moss-base", default="http://10.242.0.1:8791", help="MOSS Image Studio base URL")
    ap.add_argument("--output-dir", default="", help="where finished writing jobs are kept (empty = memory only)")
    args = ap.parse_args(argv)
    skills = Skills(args.skills_dir)
    router = Router(args.router_base)
    writer = Writer(router, skills, args.default_model, args.output_dir)
    httpd = ThreadingHTTPServer((args.host, args.port), make_handler(skills, router, writer, MossClient(args.moss_base)))
    print("writing-studio listening on http://%s:%d" % (args.host, httpd.server_address[1]), flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
