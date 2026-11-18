#!/usr/bin/env python3
"""MOSS-Image service: a small local web page and JSON API in front of the mossimage.cpp `moss-server` sidecar.

Stdlib only. Binds to 127.0.0.1 by default and has no authentication of its own: publish it only behind an
authenticated proxy. One generation runs at a time (the engine allows no more). The GPU gate refuses to start a
job unless enough VRAM is free, so this service never takes the GPU from the LLM; scheduling the GPU through the
GPU ownership controller is a separate, explicitly approved integration (see README.md).
"""
import argparse
import json
import os
import pathlib
import queue
import re
import shlex
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = pathlib.Path(__file__).resolve().parent
USUAL_NEGATIVE = "nsfw, worst quality, bad anatomy, watermark, jpeg artifact"
# Defaults are the settings the preset recipes were tested with (ComfyUI MOSS template: er_sde, 25 steps, CFG 2.5, 1216x832).
DEFAULTS = {"width": 1216, "height": 832, "steps": 25, "cfg": 2.5, "sampler": "er_sde", "seed": -1}
LIMITS = {"min_side": 256, "max_side": 2048, "max_pixels": 2_100_000, "min_steps": 1, "max_steps": 60,
          "max_cfg": 10.0, "max_text": 4000}
SAMPLERS = ("euler", "ab2", "euler_ancestral", "heun", "dpmpp_2m", "dpmpp_2m_sde", "er_sde", "res_multistep")
IMAGE_NAME = re.compile(r"^[0-9a-f]{32}\.png$")
JOB_ID = re.compile(r"^[0-9a-f]{32}$")
MAX_BODY = 64 * 1024
KEEP_JOBS = 200


_HIDE_LOCK = threading.Lock()


class ApiError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


# ---------------------------------------------------------------- presets and prompt composition
def load_presets(path):
    doc = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    presets, seen = doc["presets"], set()
    for p in presets:
        for key in ("id", "category", "name", "prompt_look", "negative_extra"):
            if not isinstance(p.get(key), str) or not p[key].strip():
                raise ValueError("preset %r has no %s" % (p.get("id"), key))
        if p["id"] in seen:
            raise ValueError("duplicate preset id " + p["id"])
        seen.add(p["id"])
    return doc


def compose(scene, preset, user_negative=""):
    """Recipe, then the scene, then the recipe again (the look is said twice); negative = usual + recipe + user."""
    scene = scene.strip()
    if preset is None:
        prompt, negative = scene, USUAL_NEGATIVE
    else:
        look = preset["prompt_look"].strip()
        prompt = "%s %s %s" % (look, scene, look)
        negative = "%s, %s" % (USUAL_NEGATIVE, preset["negative_extra"].strip())
    if user_negative.strip():
        negative += ", " + user_negative.strip()
    return prompt, negative


def _num(body, key, kind, lo, hi):
    value = body.get(key, DEFAULTS.get(key))
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ApiError(400, "invalid_params", "%s must be a number" % key)
    if kind is int and value != int(value):
        raise ApiError(400, "invalid_params", "%s must be a whole number" % key)
    value = kind(value)
    if not lo <= value <= hi:
        raise ApiError(400, "invalid_params", "%s must be between %s and %s" % (key, lo, hi))
    return value


def validate_request(body, presets_by_id):
    if not isinstance(body, dict):
        raise ApiError(400, "invalid_params", "body must be a JSON object")
    scene = body.get("scene", "")
    if not isinstance(scene, str) or not scene.strip():
        raise ApiError(400, "invalid_params", "scene is required")
    user_negative = body.get("negative", "")
    if not isinstance(user_negative, str):
        raise ApiError(400, "invalid_params", "negative must be text")
    if len(scene) > LIMITS["max_text"] or len(user_negative) > LIMITS["max_text"]:
        raise ApiError(400, "invalid_params", "prompt text is too long")
    preset = None
    if body.get("preset_id"):
        preset = presets_by_id.get(body["preset_id"])
        if preset is None:
            raise ApiError(400, "invalid_params", "unknown preset_id")
    width = _num(body, "width", int, LIMITS["min_side"], LIMITS["max_side"])
    height = _num(body, "height", int, LIMITS["min_side"], LIMITS["max_side"])
    if width % 16 or height % 16:
        raise ApiError(400, "invalid_params", "width and height must be multiples of 16")
    if width * height > LIMITS["max_pixels"]:
        raise ApiError(400, "invalid_params", "image is larger than %.1f megapixels" % (LIMITS["max_pixels"] / 1e6))
    sampler = body.get("sampler", DEFAULTS["sampler"])
    if sampler not in SAMPLERS:
        raise ApiError(400, "invalid_params", "unknown sampler")
    seed = body.get("seed", DEFAULTS["seed"])
    if seed is None or seed == "":
        seed = -1
    if isinstance(seed, bool) or not isinstance(seed, int) or not -1 <= seed < 2**53:
        raise ApiError(400, "invalid_params", "seed must be -1 (random) or a whole number")
    prompt, negative = compose(scene, preset, user_negative)
    return {"prompt": prompt, "negative_prompt": negative, "width": width, "height": height,
            "steps": _num(body, "steps", int, LIMITS["min_steps"], LIMITS["max_steps"]),
            "cfg": _num(body, "cfg", float, 0.0, LIMITS["max_cfg"]), "sampler": sampler, "seed": seed,
            "scene": scene.strip(), "preset_id": preset["id"] if preset else None}


# ---------------------------------------------------------------- GPU gate
def gpu_free_mib(nvidia_smi="nvidia-smi"):
    """Read-only free VRAM of GPU 0 in MiB, or None if it cannot be read."""
    try:
        out = subprocess.run([nvidia_smi, "--query-gpu=memory.free", "--format=csv,noheader,nounits", "-i", "0"],
                             capture_output=True, text=True, timeout=10, check=True).stdout
        return int(out.strip().splitlines()[0])
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


# ---------------------------------------------------------------- sidecar
class SidecarDied(RuntimeError):
    pass


class Sidecar:
    """One moss-server process, driven over JSON lines. Not thread-safe for concurrent generations (the queue serialises)."""

    def __init__(self, cmd, load_params, log_path):
        self.cmd, self.load_params, self.log_path = cmd, load_params, log_path
        self.proc = None
        self.pending = {}
        self.lock = threading.Lock()
        self.counter = 0
        self.loaded = False

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self):
        self.stop()
        log = open(self.log_path, "ab")
        self.proc = subprocess.Popen(self.cmd + ["--parent-pid", str(os.getpid())], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=log, text=True, bufsize=1)
        log.close()
        threading.Thread(target=self._reader, args=(self.proc,), daemon=True).start()
        hello = self.call("hello", {"client": "watoom-moss-image", "protocol_version": 2}, 30)
        if hello.get("protocol_version") != 2:
            raise ApiError(502, "engine", "moss-server speaks protocol %r, expected 2" % hello.get("protocol_version"))
        self.call("load", self.load_params, 120)
        self.loaded = True

    def _reader(self, proc):
        for line in proc.stdout:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            with self.lock:
                q = self.pending.get(msg.get("id"))
            if q is not None:
                q.put(msg)
        with self.lock:
            for q in self.pending.values():
                q.put({"event": "died"})

    def _send(self, obj):
        if not self.alive():
            raise SidecarDied("moss-server is not running")
        try:
            self.proc.stdin.write(json.dumps(obj) + "\n")
            self.proc.stdin.flush()
        except (OSError, ValueError) as exc:
            raise SidecarDied(str(exc))

    def _register(self):
        with self.lock:
            self.counter += 1
            rid = "r%d" % self.counter
            self.pending[rid] = queue.Queue()
            return rid, self.pending[rid]

    def _unregister(self, rid):
        with self.lock:
            self.pending.pop(rid, None)

    def call(self, method, params=None, timeout=60):
        rid, q = self._register()
        try:
            self._send({"id": rid, "method": method, **({"params": params} if params is not None else {})})
            while True:
                try:
                    msg = q.get(timeout=timeout)
                except queue.Empty:
                    raise ApiError(504, "engine", "moss-server did not answer %s in %ds" % (method, timeout))
                if msg.get("event") == "died":
                    raise SidecarDied("moss-server exited during " + method)
                if "event" in msg:
                    continue
                if "error" in msg:
                    err = msg["error"]
                    raise ApiError(502, err.get("code", "engine"), err.get("message", "engine error"))
                return msg.get("result") or {}
        finally:
            self._unregister(rid)

    def generate(self, params, on_event, cancelled):
        """Run one generation; returns the `done` event. on_event gets plan/progress events."""
        rid, q = self._register()
        sent_cancel = False
        try:
            self._send({"id": rid, "method": "generate", "params": params})
            while True:
                try:
                    msg = q.get(timeout=1.0)
                except queue.Empty:
                    if cancelled.is_set() and not sent_cancel:
                        sent_cancel = True
                        self.call("cancel", {"id": rid}, 10)
                    continue
                if msg.get("event") == "died":
                    raise SidecarDied("moss-server exited during generation")
                if "error" in msg:
                    err = msg["error"]
                    return {"status": "error", "error": {"code": err.get("code", "engine"), "message": err.get("message", "")}}
                if msg.get("event") == "done":
                    return msg
                if "event" in msg:
                    on_event(msg)
                if cancelled.is_set() and not sent_cancel:
                    sent_cancel = True
                    self.call("cancel", {"id": rid}, 10)
        finally:
            self._unregister(rid)

    def release(self):
        if self.alive() and self.loaded:
            self.call("release", {"keep_host_copy": False}, 60)

    def stop(self):
        if self.proc is not None and self.proc.poll() is None:
            try:
                self.call("shutdown", None, 5)
            except Exception:
                pass
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if self.proc is not None:
            for pipe in (self.proc.stdin, self.proc.stdout):
                try:
                    pipe.close()
                except (OSError, ValueError):
                    pass
        self.proc, self.loaded = None, False


# ---------------------------------------------------------------- job manager
class Manager:
    def __init__(self, cfg, presets_doc, sidecar, session=None):
        self.cfg, self.presets_doc, self.sidecar, self.session = cfg, presets_doc, sidecar, session
        self.presets_by_id = {p["id"]: p for p in presets_doc["presets"]}
        self.jobs, self.order = {}, []
        self.q = queue.Queue()
        self.mu = threading.Lock()
        self.last_used = time.monotonic()
        self.running = None
        self.stopping = threading.Event()
        # In-memory Prometheus counters (reset when the service restarts).
        self.stats = {"jobs": {}, "errors": {}, "gen_seconds": 0.0, "gen_count": 0, "steps": 0, "pixels": 0, "last_seconds": 0.0}
        cfg["out_dir"].mkdir(parents=True, exist_ok=True)
        threading.Thread(target=self._worker, daemon=True).start()
        threading.Thread(target=self._idle_release, daemon=True).start()

    # -- API-facing
    def submit(self, body):
        params = validate_request(body, self.presets_by_id)
        if self.session is not None and not self.session.active():
            raise ApiError(409, "gpu_session_required", "Start a GPU session first (this pauses the LLM while you generate).")
        jid = uuid.uuid4().hex
        job = {"id": jid, "status": "queued", "created": time.time(), "request": params, "phase": None, "fraction": 0.0,
               "eta_seconds": None, "image": None, "error": None, "warnings": [], "cancel": threading.Event()}
        with self.mu:
            if sum(1 for j in self.jobs.values() if j["status"] in ("queued", "running")) >= 8:
                raise ApiError(429, "busy", "too many queued jobs")
            self.jobs[jid] = job
            self.order.append(jid)
            while len(self.order) > KEEP_JOBS:
                self.jobs.pop(self.order.pop(0), None)
        self.q.put(jid)
        return self.public(job)

    def get(self, jid):
        with self.mu:
            job = self.jobs.get(jid)
        if job is None:
            raise ApiError(404, "not_found", "no such job")
        return self.public(job)

    def cancel(self, jid):
        with self.mu:
            job = self.jobs.get(jid)
        if job is None:
            raise ApiError(404, "not_found", "no such job")
        job["cancel"].set()
        if job["status"] == "queued":
            job["status"] = "cancelled"
        return self.public(job)

    @staticmethod
    def public(job):
        r = job["request"]
        return {"id": job["id"], "status": job["status"], "phase": job["phase"], "fraction": job["fraction"],
                "eta_seconds": job["eta_seconds"], "image": job["image"], "error": job["error"], "warnings": job["warnings"],
                "request": {k: r[k] for k in ("scene", "preset_id", "prompt", "negative_prompt", "width", "height", "steps",
                                              "cfg", "sampler", "seed")}}

    def gallery(self, limit=40, hidden=False):
        """Recent images, newest first. With hidden=True, only the images moved to the blurred Hidden panel (their prompt text is not returned)."""
        items = []
        for meta in sorted(self.cfg["out_dir"].glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            if len(items) >= limit:
                break
            try:
                doc = json.loads(meta.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if (doc.get("hidden") is True) != hidden:
                continue
            if JOB_ID.match(meta.stem) and (self.cfg["out_dir"] / (meta.stem + ".png")).exists():
                keys = ("width", "height", "created") if hidden else ("scene", "preset_id", "width", "height", "created")
                items.append({"id": meta.stem, "image": meta.stem + ".png", **{k: doc.get(k) for k in keys}})
        return items

    def hide(self, image_id, hidden=True):
        """Move an image to the blurred Hidden panel (and out of the Command Center) without deleting any file; reversible."""
        if not JOB_ID.fullmatch(image_id):
            raise ApiError(400, "invalid_params", "invalid image id")
        meta = self.cfg["out_dir"] / (image_id + ".json")
        with _HIDE_LOCK:
            try:
                doc = json.loads(meta.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raise ApiError(404, "not_found", "not found")
            if not isinstance(doc, dict):
                raise ApiError(404, "not_found", "not found")
            if hidden:
                doc["hidden"] = True
            else:
                doc.pop("hidden", None)
            tmp = meta.with_name("." + meta.name + ".tmp")
            tmp.write_text(json.dumps(doc), encoding="utf-8")
            os.replace(tmp, meta)
        return {"id": image_id, "hidden": hidden}

    def status(self):
        free = gpu_free_mib(self.cfg["nvidia_smi"]) if self.cfg["gpu_gate"] == "vram" else None
        return {"engine_running": self.sidecar.alive(), "loaded": self.sidecar.loaded, "running_job": self.running,
                "queued": self.q.qsize(), "gpu_gate": self.cfg["gpu_gate"], "gpu_free_mib": free,
                "min_free_vram_mib": self.cfg["min_free_vram_mib"],
                "session": self.session.snapshot() if self.session else None}

    # -- worker
    def _gate(self):
        # Only called before a fresh engine is started; a running engine already owns its VRAM.
        if self.session is not None:
            if not self.session.active():
                raise ApiError(409, "gpu_session_required", "No active GPU session")
            return  # the controller already paused the LLM; VRAM was verified when the session started
        if self.cfg["gpu_gate"] != "vram":
            return
        free = gpu_free_mib(self.cfg["nvidia_smi"])
        need = self.cfg["min_free_vram_mib"]
        if free is None:
            raise ApiError(503, "gpu_unknown", "GPU memory could not be read; refusing to start")
        if free < need:
            raise ApiError(503, "gpu_busy", "The GPU is in use by another workload (%d MiB free, %d MiB needed). "
                           "This service never takes the GPU from the LLM; schedule it through the GPU controller." % (free, need))

    def _worker(self):
        while not self.stopping.is_set():
            try:
                jid = self.q.get(timeout=0.5)
            except queue.Empty:
                continue
            with self.mu:
                job = self.jobs.get(jid)
            if job is None or job["status"] != "queued":
                if job is not None and job["status"] == "cancelled":
                    self._count(job, 0.0)
                continue
            job["status"] = "running"
            self.running = jid
            started = time.monotonic()
            try:
                self._run(job)
            except ApiError as exc:
                job["status"], job["error"] = "error", {"code": exc.code, "message": exc.message}
            except SidecarDied as exc:
                self.sidecar.stop()
                job["status"], job["error"] = "error", {"code": "engine_died", "message": str(exc)}
            except Exception as exc:  # keep the worker alive whatever happens
                job["status"], job["error"] = "error", {"code": "internal", "message": "%s: %s" % (type(exc).__name__, exc)}
            finally:
                self._count(job, time.monotonic() - started)
                self.running = None
                self.last_used = time.monotonic()

    def _count(self, job, seconds):
        st = self.stats
        st["jobs"][job["status"]] = st["jobs"].get(job["status"], 0) + 1
        if job["status"] == "error":
            code = (job.get("error") or {}).get("code", "unknown")
            st["errors"][code] = st["errors"].get(code, 0) + 1
        if job["status"] == "done":
            r = job["request"]
            st["gen_seconds"] += seconds; st["gen_count"] += 1; st["last_seconds"] = seconds
            st["steps"] += int(r["steps"]); st["pixels"] += int(r["width"]) * int(r["height"])

    def metrics(self):
        """Prometheus text exposition for the dashboard (no secrets, no prompts)."""
        st, out = self.stats, []
        def g(name, help_, kind, samples):
            out.append("# HELP %s %s\n# TYPE %s %s" % (name, help_, name, kind))
            out.extend("%s%s %s" % (name, lab, val) for lab, val in samples)
        sess = None
        try:
            sess = self.session.snapshot() if self.session else None
        except Exception:
            pass
        g("watoom_moss_up", "MOSS image service is serving.", "gauge", [("", 1)])
        g("watoom_moss_engine_running", "1 when the moss-server engine process is alive.", "gauge", [("", int(bool(self.sidecar.alive())))])
        g("watoom_moss_engine_loaded", "1 when an image model is loaded in the engine.", "gauge", [("", int(bool(self.sidecar.loaded)))])
        g("watoom_moss_job_running", "1 while a generation is running.", "gauge", [("", int(self.running is not None))])
        g("watoom_moss_queue_depth", "Queued generation jobs.", "gauge", [("", self.q.qsize())])
        g("watoom_moss_session_active", "1 while a GPU session is active.", "gauge", [("", int(bool(sess and sess.get("state") == "active")))])
        g("watoom_moss_session_idle_seconds_left", "Seconds until the idle timeout ends the GPU session.", "gauge",
          [("", sess.get("idle_seconds_left") or 0)] if sess else [])
        g("watoom_moss_jobs_total", "Finished generation jobs by status.", "counter",
          [('{status="%s"}' % k, v) for k, v in sorted(st["jobs"].items())])
        g("watoom_moss_job_errors_total", "Failed generation jobs by error code.", "counter",
          [('{code="%s"}' % k, v) for k, v in sorted(st["errors"].items())])
        g("watoom_moss_generation_seconds_sum", "Total wall seconds spent generating completed images.", "counter", [("", round(st["gen_seconds"], 3))])
        g("watoom_moss_generation_seconds_count", "Completed images (denominator for average seconds per image).", "counter", [("", st["gen_count"])])
        g("watoom_moss_steps_total", "Sampling steps across completed images.", "counter", [("", st["steps"])])
        g("watoom_moss_pixels_total", "Pixels across completed images.", "counter", [("", st["pixels"])])
        g("watoom_moss_last_generation_seconds", "Wall seconds of the most recent completed image.", "gauge", [("", round(st["last_seconds"], 3))])
        return "\n".join(out) + "\n"

    def _run(self, job):
        if job["cancel"].is_set():
            job["status"] = "cancelled"
            return
        if not (self.sidecar.alive() and self.sidecar.loaded):
            self._gate()
            self.sidecar.start()
        r = job["request"]
        out = self.cfg["out_dir"] / (job["id"] + ".png")
        params = {"prompt": r["prompt"], "negative_prompt": r["negative_prompt"], "width": r["width"], "height": r["height"],
                  "steps": r["steps"], "cfg": r["cfg"], "sampler": r["sampler"], "seed": r["seed"], "output": str(out)}

        def on_event(msg):
            if msg.get("event") == "progress":
                job["phase"] = msg.get("phase")
                if isinstance(msg.get("fraction"), (int, float)):
                    job["fraction"] = max(job["fraction"], float(msg["fraction"]))
                job["eta_seconds"] = msg.get("eta_seconds")

        done = self.sidecar.generate(params, on_event, job["cancel"])
        job["warnings"] = [str(w)[:300] for w in done.get("warnings", [])][:20]
        if done.get("status") == "ok" and out.exists():
            job["status"], job["image"], job["fraction"] = "done", out.name, 1.0
            meta = {"scene": r["scene"], "preset_id": r["preset_id"], "prompt": r["prompt"], "negative_prompt": r["negative_prompt"],
                    "width": r["width"], "height": r["height"], "steps": r["steps"], "cfg": r["cfg"], "sampler": r["sampler"],
                    "seed": r["seed"], "created": job["created"]}
            (self.cfg["out_dir"] / (job["id"] + ".json")).write_text(json.dumps(meta), encoding="utf-8")
        elif done.get("status") == "cancelled":
            job["status"] = "cancelled"
        else:
            err = done.get("error") or {"code": "engine", "message": "generation failed"}
            job["status"], job["error"] = "error", {"code": err.get("code", "engine"), "message": err.get("message", "")}

    def _idle_release(self):
        while not self.stopping.wait(5):
            idle = self.cfg["idle_release_s"]
            if self.session is None and idle and self.running is None and self.q.empty() and self.sidecar.loaded and time.monotonic() - self.last_used > idle:
                try:
                    self.sidecar.release()
                    self.sidecar.stop()  # frees the CUDA context too; the next job starts a fresh server
                except Exception:
                    self.sidecar.stop()

    def busy(self):
        return self.running is not None or not self.q.empty()

    def stop_engine(self):
        self.sidecar.stop()

    def shutdown(self):
        self.stopping.set()
        if self.session is not None:
            self.session.shutdown()
        self.sidecar.stop()


# ---------------------------------------------------------------- HTTP
def make_handler(manager):
    page = (HERE / "web" / "index.html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        server_version = "moss-image"

        def log_message(self, *args):
            pass

        def _send(self, status, body, ctype="application/json", extra=None):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status, obj):
            self._send(status, json.dumps(obj).encode())

        def _guard_post(self):
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                raise ApiError(415, "unsupported", "Content-Type must be application/json")
            origin = self.headers.get("Origin")
            if origin and origin.split("://", 1)[-1] != self.headers.get("Host", ""):
                raise ApiError(403, "forbidden", "cross-origin request refused")
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                raise ApiError(413, "too_large", "request body too large")
            try:
                return json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                raise ApiError(400, "invalid_params", "body is not valid JSON")

        def _route(self, method):
            path = self.path.split("?", 1)[0]
            if method == "GET":
                if path in ("/", "/index.html"):
                    return self._send(200, page, "text/html; charset=utf-8")
                if path == "/api/presets":
                    return self._json(200, {k: manager.presets_doc.get(k) for k in ("title", "source", "author", "usage", "licence_note", "presets")})
                if path == "/api/config":
                    return self._json(200, {"defaults": DEFAULTS, "limits": LIMITS, "samplers": SAMPLERS, "out_dir": str(manager.cfg["out_dir"])})
                if path == "/api/status":
                    return self._json(200, manager.status())
                if path == "/metrics":
                    return self._send(200, manager.metrics().encode(), "text/plain; version=0.0.4; charset=utf-8")
                if path == "/api/gallery":
                    m = re.search(r"[?&]limit=(\d{1,2})(?:&|$)", self.path)
                    return self._json(200, {"items": manager.gallery(max(1, min(int(m.group(1)), 40)) if m else 40, hidden=bool(re.search(r"[?&]hidden=1(?:&|$)", self.path)))})
                m = re.fullmatch(r"/api/jobs/([0-9a-f]{32})", path)
                if m:
                    return self._json(200, manager.get(m.group(1)))
                m = re.fullmatch(r"/api/images/([0-9a-f]{32}\.png)", path)
                if m and IMAGE_NAME.match(m.group(1)):
                    f = manager.cfg["out_dir"] / m.group(1)
                    if f.is_file():
                        return self._send(200, f.read_bytes(), "image/png")
                raise ApiError(404, "not_found", "not found")
            if path == "/api/session/start" and manager.session is not None:
                self._guard_post()
                return self._json(202, manager.session.start())
            if path == "/api/session/end" and manager.session is not None:
                self._guard_post()
                return self._json(202, manager.session.end())
            if path == "/api/generate":
                return self._json(202, manager.submit(self._guard_post()))
            m = re.fullmatch(r"/api/gallery/([0-9a-f]{32})/(hide|unhide)", path)
            if m:
                self._guard_post()
                return self._json(200, manager.hide(m.group(1), m.group(2) == "hide"))
            m = re.fullmatch(r"/api/jobs/([0-9a-f]{32})/cancel", path)
            if m:
                self._guard_post()
                return self._json(200, manager.cancel(m.group(1)))
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


def build(args):
    engine = pathlib.Path(args.engine_dir)
    model = pathlib.Path(args.model_folder)
    out_dir = pathlib.Path(args.out_dir)
    load = {"model": str(model), "tier": args.tier, "mode": args.mode, "cache_dir": str(out_dir / ".cache")}
    for key, val in (("dit_file", args.dit), ("text_encoder_file", args.text_encoder), ("vae_file", args.vae)):
        if val:
            load[key] = str(val)
    if args.sidecar_cmd:
        cmd = shlex.split(args.sidecar_cmd)
    else:  # the release tarball unpacks into engine/mossinfer-<version>-<flavour>/
        found = sorted(engine.glob("*/bin/moss-server")) or sorted(engine.glob("bin/moss-server"))
        if not found:
            raise SystemExit("moss-server not found under %s" % engine)
        cmd = [str(found[-1])]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / ".cache").mkdir(exist_ok=True)
    cfg = {"out_dir": out_dir, "gpu_gate": args.gpu_gate, "min_free_vram_mib": args.min_free_vram_mib,
           "idle_release_s": args.idle_release, "nvidia_smi": os.environ.get("MOSS_NVIDIA_SMI", "nvidia-smi")}
    sidecar = Sidecar(cmd, load, str(out_dir / "moss-server.log"))
    mgr = Manager(cfg, load_presets(args.presets), sidecar)
    if args.gpu_gate == "controller":
        mgr.session = make_session(args, cfg, mgr)
    return mgr


def make_session(args, cfg, mgr):
    """Real controller wiring. Imports the controller client and the native-activity probe lazily."""
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    import gpu_session
    tools = pathlib.Path(args.tools_dir)
    sys.path[:0] = [str(tools / "llm" / "watoom-gpu-controller"), str(tools / "watoom-code")]
    from client import GPUClient
    probe_state = {}

    def native_active():
        from maintenance_guard import Maintenance  # needs kubectl + the OPENCODE secret; fails closed if unavailable
        if "m" not in probe_state:
            probe_state["m"] = Maintenance("watoom-code", "watoom-code", pathlib.Path(cfg["out_dir"]) / ".guard", True, True)
        return bool(probe_state["m"].request("/api/session/active").get("data", {}))

    quiet = gpu_session.QuietTracker(native_active)
    threading.Thread(target=lambda: [quiet.sample() or time.sleep(quiet.interval) for _ in iter(int, 1)], daemon=True).start()
    free = lambda: gpu_free_mib(cfg["nvidia_smi"])
    return gpu_session.GpuSession(GPUClient(args.controller_socket, timeout=1500), quiet, mgr.stop_engine, free,
                                  min_free_mib=cfg["min_free_vram_mib"], quiet_required=args.quiet_seconds,
                                  idle_timeout=args.session_idle, max_session=args.session_max,
                                  busy=mgr.busy, last_used=lambda: mgr.last_used,
                                  demand=gpu_session.DemandWatcher(args.llm_demand_url).poll if args.llm_demand_url else (lambda: False))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    root = pathlib.Path(os.environ.get("MOSS_IMAGE_ROOT", "/data/ai/projects/images/moss-image"))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8791)
    ap.add_argument("--engine-dir", default=str(root / "engine"))
    ap.add_argument("--model-folder", default=str(root / "models" / "MOSS-Image-SFT"))
    ap.add_argument("--dit", default=str(root / "models/components/dit/moss_image_sft_int8_convrot.safetensors"))
    ap.add_argument("--text-encoder", default=str(root / "models/components/text_encoder/qwen3.5_9b_w4a8_gptq.safetensors"))
    ap.add_argument("--vae", default=str(root / "models/components/vae/flux2-vae.safetensors"))
    ap.add_argument("--tier", default="high", choices=("reference", "high", "turbo"))
    ap.add_argument("--mode", default="min_memory", choices=("min_memory", "balanced", "max_speed"))
    ap.add_argument("--out-dir", default=str(root / "output"))
    ap.add_argument("--presets", default=str(HERE / "presets" / "film-camera-looks.json"))
    ap.add_argument("--gpu-gate", default="vram", choices=("vram", "none", "controller"))
    ap.add_argument("--controller-socket", default="/data/ai/helper-scripts/state/gpu-controller-private/worker.sock")
    ap.add_argument("--tools-dir", default=str(HERE.parent))
    ap.add_argument("--quiet-seconds", type=int, default=0, help="WatooM Code must have been inactive this long before a session may start (0: one idle check, then start)")
    ap.add_argument("--session-idle", type=int, default=600, help="seconds with no job before the session ends and the LLM is restored")
    ap.add_argument("--session-max", type=int, default=7200, help="hard maximum session length in seconds")
    ap.add_argument("--llm-demand-url", default="", help="router /performance URL; when LLM requests are refused while MOSS is idle, the session ends and Qwen is restored (empty: off)")
    ap.add_argument("--min-free-vram-mib", type=int, default=6144)
    ap.add_argument("--idle-release", type=int, default=300, help="seconds idle before the engine is stopped and the GPU freed; 0 = never")
    ap.add_argument("--sidecar-cmd", default="", help="override the moss-server command (tests)")
    args = ap.parse_args(argv)
    manager = build(args)
    httpd = ThreadingHTTPServer((args.host, args.port), make_handler(manager))
    print("moss-image listening on http://%s:%d" % (args.host, httpd.server_address[1]), flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        manager.shutdown()


if __name__ == "__main__":
    main()
