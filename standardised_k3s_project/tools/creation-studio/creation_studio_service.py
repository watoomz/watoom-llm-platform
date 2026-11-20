#!/usr/bin/env python3
"""Creation Studio: a standalone web page for image and 3D-mesh generation.

Stdlib only. This service owns NO generation backend of its own: it is a thin,
read-mostly proxy in front of two existing services and a read-only status file.

  - SDXL pipeline: proxies to the existing Model Manager HTTP API
    (tools/model-manager/server.py), authenticating the same way an operator's
    browser does (password login -> session cookie -> CSRF token), then calling
    its existing /api/generate, /api/jobs, /api/result, /api/models endpoints.
    No GPU/broker logic is reimplemented here.
  - MOSS Image Studio pipeline: proxies to the existing MOSS Image Studio HTTP
    API (tools/moss-image/moss_image_service.py) over the internal k3s bridge,
    same-origin/no-auth, exactly as that service's own page does. No GPU
    session handling is reimplemented here; this only forwards the calls.
  - Mesh (LLaMA-Mesh) pipeline: proxies to the existing root-owned Unix bridge
    (ansible/roles/llm-model-lab/files/opencode_mesh_bridge.py) exactly as the
    OpenCode v2 canary's own watoom-llama-mesh.py MCP tool does -- one JSON
    request + newline over the bridge socket, no reimplementation of the GPU
    pipeline. The bridge authorizes callers by the connecting process's real
    UID (SO_PEERCRED) against an allow-list (ansible/roles/llm-model-lab
    defaults: llm_mesh_bridge_additional_uids); Creation Studio's systemd
    unit was deliberately added to that list (an operator-approved
    access-control change, not something this service grants itself) and runs
    as that dedicated UID so the connection is actually authorized. This
    service also reads the existing world-readable GPU controller
    observability snapshot (schema watoom.gpu-observation.v1) to show whether
    Mesh currently owns the GPU. If the bridge socket is not configured
    (--mesh-bridge-socket empty), Mesh generation reports a clear
    "not configured" error instead of silently no-opping.
  - GLB 3D Coder pipeline (2026-11-19): ccore/Qwen3.5-4B-GLB-3D-Coder through
    the existing LLM router (Model Manager model, --glb-model; the router asks the GPU
    controller for the switch, nothing GPU-side is reimplemented here). The
    model writes one standalone Three.js HTML page with an Export GLB button.
    A job streams the answer server-side (answers average ~20K tokens, so the
    browser only polls), with the model card's system prompt and sampling, and
    the result is served back under its own sandbox CSP for the preview.
"""
import argparse
import http.client
import json
import os
import pathlib
import re
import socket
import ssl
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = pathlib.Path(__file__).resolve().parent
MAX_BODY = 64 * 1024
JOB_ID = re.compile(r"^[0-9a-f]{32}$")
IMAGE_NAME = re.compile(r"^[0-9a-f]{32}\.png$")

MESH_BLOCKER = (
    "Mesh generation is not configured (no --mesh-bridge-socket). The real pipeline is reached "
    "only through a root-owned Unix bridge (opencode_mesh_bridge.py) that checks the caller's "
    "real UID against an allow-list (ansible/roles/llm-model-lab defaults: "
    "llm_mesh_bridge_additional_uids). See tools/creation-studio/README.md for the trace."
)


class ApiError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


# ---------------------------------------------------------------- Model Manager (SDXL) proxy
class ModelManagerError(ApiError):
    pass


class ModelManagerClient:
    """Authenticates like an operator's browser (password -> session cookie -> CSRF) and
    forwards calls to the existing Model Manager HTTP API. Never touches its GPU/broker logic."""

    def __init__(self, base_url, origin, password, timeout=30, ca_file=None):
        parsed = urllib.parse.urlsplit(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("model manager base url must be absolute http(s)")
        self.scheme, self.host = parsed.scheme, parsed.hostname
        self.port = parsed.port or (443 if parsed.scheme == "https" else 80)
        self.prefix = parsed.path.rstrip("/")
        self.origin, self.password, self.timeout = origin, password, timeout
        self._ssl_context = ssl.create_default_context(cafile=ca_file) if self.scheme == "https" else None
        self._lock = threading.Lock()
        self._cookie, self._csrf = None, None

    def _connection(self):
        if self.scheme == "https":
            return http.client.HTTPSConnection(self.host, self.port, timeout=self.timeout, context=self._ssl_context)
        return http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)

    def _login(self):
        conn = self._connection()
        try:
            body = urllib.parse.urlencode({"password": self.password}).encode()
            headers = {"Content-Type": "application/x-www-form-urlencoded", "Origin": self.origin,
                       "Content-Length": str(len(body))}
            conn.request("POST", self.prefix + "/login", body, headers)
            resp = conn.getresponse()
            resp.read()
            cookie = resp.getheader("Set-Cookie") or ""
            if resp.status != 303 or "mm_session=" not in cookie:
                raise ModelManagerError(502, "model_manager_login_failed", "Model Manager login failed (HTTP %d)" % resp.status)
            self._cookie = cookie.split(";", 1)[0]
        finally:
            conn.close()
        conn = self._connection()
        try:
            conn.request("GET", self.prefix + "/api/session", headers={"Cookie": self._cookie})
            resp = conn.getresponse()
            raw = resp.read()
            if resp.status != 200:
                raise ModelManagerError(502, "model_manager_session_failed", "Could not obtain a CSRF token from Model Manager")
            self._csrf = json.loads(raw).get("csrf", "")
        finally:
            conn.close()

    def _call(self, method, path, body=None, retry=True):
        with self._lock:
            if self._cookie is None:
                self._login()
            headers = {"Cookie": self._cookie}
            data = None
            if body is not None:
                data = json.dumps(body).encode()
                headers.update({"Content-Type": "application/json", "Origin": self.origin,
                                "X-CSRF-Token": self._csrf or "", "Content-Length": str(len(data))})
            conn = self._connection()
            try:
                conn.request(method, self.prefix + path, data, headers)
                resp = conn.getresponse()
                raw = resp.read()
                status = resp.status
            finally:
                conn.close()
        if status in (401, 403) and retry:
            with self._lock:
                self._cookie = None
            return self._call(method, path, body, retry=False)
        try:
            parsed = json.loads(raw) if raw else {}
        except ValueError:
            parsed = {"error": "Model Manager returned a non-JSON response"}
        if status >= 400:
            message = parsed.get("error") if isinstance(parsed, dict) else None
            raise ModelManagerError(status, "model_manager_error", message or ("Model Manager HTTP %d" % status))
        return parsed

    def models(self):
        return self._call("GET", "/api/models")

    def jobs(self):
        return self._call("GET", "/api/jobs")

    def result(self, job_id):
        return self._call("GET", "/api/result?id=" + urllib.parse.quote(job_id, safe=""))

    def generate(self, model_id, revision, prompt):
        return self._call("POST", "/api/generate", {"id": model_id, "revision": revision, "prompt": prompt})


# ---------------------------------------------------------------- MOSS Image Studio proxy
# Allow-listed paths only; this mirrors moss_image_service.py's own routing, never invents one.
MOSS_GET = (
    re.compile(r"^/api/presets$"),
    re.compile(r"^/api/status$"),
    re.compile(r"^/api/config$"),
    re.compile(r"^/api/gallery(\?.*)?$"),
    re.compile(r"^/api/jobs/[0-9a-f]{32}$"),
    re.compile(r"^/api/images/[0-9a-f]{32}\.png$"),
)
MOSS_POST = (
    re.compile(r"^/api/generate$"),
    re.compile(r"^/api/session/start$"),
    re.compile(r"^/api/session/end$"),
    re.compile(r"^/api/jobs/[0-9a-f]{32}/cancel$"),
)


class MossClient:
    """Same-origin, no-auth passthrough to the existing MOSS Image Studio API. Never reimplements
    its GPU session handling; only forwards the calls the Studio's own page already makes."""

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
            headers = {}
            data = None
            if body is not None:
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                headers["Content-Type"] = "application/json"
            conn.request(method, path, data, headers)
            resp = conn.getresponse()
            raw = resp.read()
            return resp.status, resp.getheader("Content-Type", "application/octet-stream"), raw
        except (OSError, http.client.HTTPException) as exc:
            raise ApiError(503, "moss_unreachable", "MOSS Image Studio is unreachable: %s" % exc)
        finally:
            conn.close()


# ---------------------------------------------------------------- Mesh (LLaMA-Mesh) bridge client
class MeshClient:
    """Speaks the opencode_mesh_bridge.py Unix-socket protocol directly (one JSON object + newline
    request, one JSON object + newline response: {"ok": true, "result": ...} or {"ok": false, "error": ...}).
    Authorization is by the connecting process's real UID (SO_PEERCRED) on the bridge's side, not by
    anything this client sends; Creation Studio's systemd unit must run as a UID on the bridge's
    allow-list (ansible/roles/llm-model-lab/defaults/main.yml: llm_mesh_bridge_additional_uids)
    for this to work. Never reimplements the pipeline; only forwards the bridge's own operations."""

    def __init__(self, socket_path, timeout=30):
        self.socket_path, self.timeout = socket_path, timeout

    def _call(self, request):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect(self.socket_path)
            sock.sendall(json.dumps(request).encode() + b"\n")
            chunks = []
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
                if chunk.endswith(b"\n"):
                    break
            reply = json.loads(b"".join(chunks).decode())
        except (OSError, ValueError) as exc:
            raise ApiError(503, "mesh_bridge_unreachable", "Mesh bridge is unreachable: %s" % exc)
        finally:
            sock.close()
        if not reply.get("ok"):
            raise ApiError(502, "mesh_rejected", str(reply.get("error", "rejected")))
        return reply["result"]

    def generate(self, prompt, name=None, seed=None, temperature=None, max_tokens=None, request_id=None):
        request = {"operation": "submit", "prompt": prompt}
        if name is not None:
            request["name"] = name
        if seed is not None:
            request["seed"] = seed
        if temperature is not None:
            request["temperature"] = temperature
        if max_tokens is not None:
            request["max_tokens"] = max_tokens
        if request_id is not None:
            request["request_id"] = request_id
        return self._call(request)

    def jobs(self):
        return self._call({"operation": "list"})

    def job_status(self, job_id):
        return self._call({"operation": "status", "job_id": job_id})

    def result(self, job_id):
        return self._call({"operation": "retrieve", "job_id": job_id})


# ---------------------------------------------------------------- Mesh: GPU observability snapshot
def mesh_status(observability_path, wired):
    path = pathlib.Path(observability_path)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"telemetry_available": False, "wired": wired, "blocker": None if wired else MESH_BLOCKER}
    if doc.get("schema") != "watoom.gpu-observation.v1":
        return {"telemetry_available": False, "wired": wired, "blocker": None if wired else MESH_BLOCKER}
    age_s = max(0.0, time.time() - doc.get("sampledAt", 0) / 1000.0)
    return {
        "telemetry_available": True, "wired": wired, "blocker": None if wired else MESH_BLOCKER,
        "phase": doc.get("phase"), "owner": doc.get("owner"), "uncertain": doc.get("uncertain"),
        "primary": doc.get("primary"), "active_requests": doc.get("activeRequests"),
        "sample_age_seconds": round(age_s, 1), "mesh_owns_gpu": doc.get("phase") == "mesh-ready",
    }


# ---------------------------------------------------------------- GLB 3D Coder (LLM router)
# From the model card (https://huggingface.co/ccore/Qwen3.5-4B-GLB-3D-Coder, rev 8f32a199): its system prompt, its
# sampling table (also its generation_config.json), thinking on with no budget and no output cap.
GLB_SYSTEM_PROMPT = (
    "Create game assets for the Godot editor, which uses GLB files. Create whatever the user requests as a "
    "good-quality low-poly asset using only Three.js in one complete standalone HTML file. The HTML must show the "
    "asset and include an Export GLB button that downloads a working GLB. If the requested asset needs animation, add "
    "it and include the animation in the exported GLB; otherwise make it static."
)
GLB_SAMPLING = {"temperature": 0.8, "top_k": 40, "top_p": 0.95, "min_p": 0.0, "repeat_penalty": 1.0}
# The card's "Domains and prompt ideas" table, all 25 rows, verbatim.
GLB_DOMAINS = [
    ("Characters and NPCs", "Create a village blacksmith wearing a blue apron."),
    ("Enemies", "Create a swamp goblin scout with a wooden shield."),
    ("Bosses", "Create a stone golem boss with glowing green crystals."),
    ("Companions and creatures", "Create a tiny fox companion wearing a red scarf."),
    ("Weapons and armor", "Create a short iron sword with a leather-wrapped grip."),
    ("Items, tools, and pickups", "Create a blue mana potion in a hexagonal glass bottle."),
    ("Props and furniture", "Create a weathered wooden workbench with a small lantern."),
    ("Nature and environment", "Create a pine tree growing on a rocky mound."),
    ("Modular architecture", "Create a stone dungeon doorway module with an iron frame."),
    ("Interactive objects", "Create a wooden gate with an opening animation."),
    ("Ground transport", "Create a compact courier motorcycle with cargo boxes."),
    ("Air and space transport", "Create a small cargo airship with twin propellers."),
    ("Watercraft", "Create a weathered fishing skiff with nets and wooden crates."),
    ("Industrial machinery", "Create a compact mining conveyor with metal support legs."),
    ("Laboratory and medical assets", "Create a portable botanical analysis station with sample jars."),
    ("Urban services", "Create a modern bus stop with a bench and route sign."),
    ("Sports and playgrounds", "Create a small playground climbing wall with colorful holds."),
    ("Farming and homestead", "Create an orchard harvest cart filled with wooden fruit crates."),
    ("Cuisine and markets", "Create a bakery display counter with bread baskets."),
    ("Museums and field research", "Create an ancient artifact display case on a stone pedestal."),
    ("Traps and hazards", "Create a hidden spiked floor trap with stone tiles."),
    ("Festivals and ceremonies", "Create a harvest festival booth with colorful banners."),
    ("Battlefield scenery", "Create a reinforced frontier command post with sandbag defenses."),
    ("Underwater structures", "Create a coral observation dome with a small docking platform."),
    ("Puzzles and gameplay markers", "Create a glowing rune sequence console with three stone buttons."),
]
# The card's gallery prompts (short and detailed briefs), verbatim.
GLB_GALLERY = [
    ("Coral-armored lighthouse keeper", "Create a coral-armored lighthouse keeper."),
    ("Frozen goblin watch camp", "Create a frozen goblin watch camp."),
    ("Magnetic-rail rescue engineer (detailed)",
     "Create a magnetic-rail rescue engineer character. Show an adult specialist in a grounded stance wearing a charcoal "
     "work suit, orange safety panels, insulated gloves, a compact helmet, and heavy boots with visible magnetic sole "
     "plates. Equip the character with a coil-testing wand, a folded emergency rail clamp, a shoulder radio, and a "
     "silver power pack connected to the tool belt by a thick blue cable. Make the proportions, cable route, pack "
     "mounting, tools, and protective equipment mechanically plausible. Use a plain presentation without extra "
     "scenery. Keep it static."),
    ("Bioluminescent cave tram station (detailed)",
     "Create a compact bioluminescent cave tram station scene. Include a short raised platform with safety rails, a "
     "small two-seat mine tram on narrow rails, a hand-operated cable winch, a ticket pedestal, a bench, and six blue "
     "glowing crystal lamps mounted in protective cages. Use dark stone, weathered timber, black iron rails, teal tram "
     "panels, and cyan crystals. Make the wheel flanges, rail spacing, cable route, platform supports, lamp cages, and "
     "passenger access mechanically coherent. Use a plain presentation without surrounding cave walls or extra "
     "scenery. Keep everything static."),
    ("Animated laboratory microscope", "Create a white laboratory microscope with a rotating objective turret."),
    ("Farmyard", "Create a small farmyard with a red barn, wooden fences, hay bales, a water trough, and a vegetable patch."),
]
# The generated page loads Three.js from a CDN (the training data uses cdn.jsdelivr.net import maps). It is served under
# a CSP sandbox WITHOUT allow-same-origin: an opaque origin that can run its scripts and download its GLB but cannot
# call this service's API or read its cookies.
GLB_PAGE_CDNS = "https://cdn.jsdelivr.net https://unpkg.com https://cdnjs.cloudflare.com https://esm.sh https://ga.jspm.io"
GLB_PAGE_CSP = (
    "sandbox allow-scripts allow-downloads allow-pointer-lock; default-src 'none'; "
    "script-src 'unsafe-inline' 'unsafe-eval' blob: " + GLB_PAGE_CDNS + "; "
    "style-src 'unsafe-inline' https://fonts.googleapis.com; font-src data: https://fonts.gstatic.com; "
    "img-src data: blob:; media-src data: blob:; worker-src blob:; "
    "connect-src data: blob: " + GLB_PAGE_CDNS
)
# Injected at the top of the PREVIEW only (never the download): a classic script runs before the page's module, so a
# module that fails to link (e.g. a named import the addon does not export) or throws is shown on the page and posted
# to the studio, instead of a blank preview (T-0103). textContent only; the message is the browser's own error text.
# Four seconds after load it also posts a health check (a drawn 3D canvas, an Export GLB button); a page that never
# posts it is frozen or still loading, which the studio reports itself.
GLB_ERROR_REPORTER = (
    b"<script>(function(){var shown=0;function report(m){if(shown>2)return;shown++;try{parent.postMessage("
    b"{type:'glb-page-error',message:String(m).slice(0,500)},'*')}catch(e){}function draw(){var d=document.createElement('div');"
    b"d.setAttribute('style','position:fixed;left:8px;right:8px;bottom:8px;z-index:2147483647;padding:8px 10px;"
    b"background:#7f1d1d;color:#fff;font:13px/1.4 system-ui,sans-serif;border-radius:6px;white-space:pre-wrap');"
    b"d.textContent='This generated page has an error, so it may show nothing: '+m;(document.body||document.documentElement)"
    b".appendChild(d)}if(document.body)draw();else addEventListener('DOMContentLoaded',draw)}"
    b"addEventListener('error',function(e){if(e.message)report(e.message+(e.lineno?' (line '+e.lineno+')':''))});"
    b"addEventListener('unhandledrejection',function(e){report('unhandled promise rejection: '+((e.reason&&e.reason.message)||e.reason))});"
    b"addEventListener('load',function(){setTimeout(function(){var c=document.querySelector('canvas'),b=[].slice.call("
    b"document.querySelectorAll('button,a,[role=button]')).some(function(x){return /export|glb|download/i.test(x.textContent||'')});"
    b"try{parent.postMessage({type:'glb-page-status',errors:shown,canvas:c?[c.width,c.height]:null,exportButton:b},'*')}catch(e){}},4000)})"
    b"})()</script>"
)


def with_error_reporter(html):
    """The preview page with GLB_ERROR_REPORTER first in <head> (or first in the document when there is no <head>)."""
    m = re.search(rb"<head\b[^>]*>", html, re.I)
    at = m.end() if m else 0
    return html[:at] + GLB_ERROR_REPORTER + html[at:]


GLB_REPAIR_ERROR_MAX = 2000
GLB_REPAIR_NOTES_MAX = 2000
GLB_REPAIR_ERROR = (
    "The page you wrote fails in the browser with this JavaScript error:\n\n{error}\n\n"
    "Fix the cause. Also fix any other mistake of the same kind elsewhere in the file, such as another name declared "
    "twice in the same scope, a variable used outside the function that defines it, or an import that the module does "
    "not export."
)
GLB_REPAIR_NOTES = (
    "I looked at the rendered asset from several angles. Change these things:\n\n{notes}\n\n"
    "Build every part as closed, solid geometry that is visible from all sides, and keep each part attached to the "
    "part it belongs to."
)
GLB_REPAIR_CLOSE = (
    "Keep everything else about the asset, its look and the Export GLB button the same. "
    "Reply with the complete corrected HTML file."
)
# Runaway guards (T-0103). The card asks for unlimited thinking and output, and the server allows 256K tokens, but on
# 2026-11-20 a repair run looped one sentence for 21 minutes (612K characters of thinking) and would only have stopped
# at the context limit. A run stops with an error when its stream ends in the same block repeated GLB_LOOP_REPEATS
# times, or past GLB_MAX_TOKENS (the card: answers average ~20K tokens; its longest training example is 72K).
GLB_LOOP_REPEATS = 4                           # at least this many copies in a row...
GLB_LOOP_SPAN = 1500                           # ...covering at least this many characters (code can repeat a short line)
GLB_LOOP_MIN, GLB_LOOP_MAX = 30, 3000          # characters in the repeated block
GLB_LOOP_WINDOW = GLB_LOOP_REPEATS * GLB_LOOP_MAX
GLB_LOOP_CHECK_EVERY = 2000                    # characters between checks
GLB_MAX_TOKENS = 100000
GLB_CHARS_PER_TOKEN = 3.3                      # measured on two runs (51249 chars = 15221 tokens; 62645 = 18953)


def repeating_block(text, repeats=GLB_LOOP_REPEATS, shortest=GLB_LOOP_MIN, longest=GLB_LOOP_MAX, span=GLB_LOOP_SPAN):
    """Length of a block that ends `text` at least `repeats` times in a row, covering at least `span` characters, or
    0. Candidate lengths come from where the last `shortest` characters occurred before, so a check costs a few
    searches, not every possible length."""
    if len(text) < repeats * shortest:
        return 0
    probe, end = text[-shortest:], len(text) - shortest
    seen = set()
    for _ in range(12):
        at = text.rfind(probe, max(0, end - longest), end)
        if at < 0:
            return 0
        period = len(text) - shortest - at
        end = at
        if period in seen or period < shortest:
            continue
        seen.add(period)
        need = max(repeats, -(-span // period))
        if period * need <= len(text):
            block = text[-period:]
            if all(text[len(text) - k * period:len(text) - (k - 1) * period] == block for k in range(2, need + 1)):
                return period
    return 0


GLB_TAIL = 1500
GLB_PROMPT_MAX = 8192


def extract_html(text):
    """The complete HTML document in a model answer (fenced or bare), or None."""
    lower = text.lower()
    start = lower.find("<!doctype html")
    if start < 0:
        start = lower.find("<html")
    end = lower.rfind("</html>")
    if start >= 0 and end > start:
        return text[start:end + len("</html>")]
    fence = re.search(r"```(?:html)?[ \t]*\n(.*?)```", text, re.S | re.I)
    if fence and "<script" in fence.group(1).lower():
        return fence.group(1)
    return None


class GlbCoder:
    """One generation at a time (the model's llama-server has a single slot), streamed from the LLM router in a
    background thread so a 20K-token answer survives page reloads; the browser polls status()."""

    def __init__(self, router_base, model="glb-3d-coder", output_dir="", read_timeout=1800):
        parsed = urllib.parse.urlsplit(router_base)
        if parsed.scheme != "http" or not parsed.hostname:
            raise ValueError("router base url must be absolute http://host:port")
        self.host, self.port = parsed.hostname, parsed.port or 80
        self.prefix = parsed.path.rstrip("/")
        self.model, self.read_timeout = model, read_timeout
        self.output_dir = pathlib.Path(output_dir) if output_dir else None
        self._lock = threading.Lock()
        self._jobs = {}
        self._warm = {"state": "idle", "started": None, "finished": None, "error": None}
        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            for meta in sorted(self.output_dir.glob("*.json")):
                try:
                    job = json.loads(meta.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if JOB_ID.match(job.get("id", "")):
                    if job.get("state") in ("queued", "waiting", "thinking", "writing"):
                        job["state"], job["error"] = "failed", "interrupted by a Creation Studio restart"
                    self._jobs[job["id"]] = job

    # ------------------------------------------------------------ public
    def config(self):
        return {"model": self.model, "model_name": self.model_names().get(self.model, self.model),
                "system_prompt": GLB_SYSTEM_PROMPT, "sampling": GLB_SAMPLING,
                "thinking": True, "max_tokens": "unlimited",
                "domains": [{"domain": d, "prompt": p} for d, p in GLB_DOMAINS],
                "gallery": [{"title": t, "prompt": p} for t, p in GLB_GALLERY]}

    def submit(self, prompt):
        prompt = prompt.strip()
        if not prompt:
            raise ApiError(400, "invalid_params", "prompt is required")
        if len(prompt) > GLB_PROMPT_MAX:
            raise ApiError(400, "invalid_params", "prompt is longer than %d characters" % GLB_PROMPT_MAX)
        return self._start(prompt, None, {})

    def repair(self, job_id, error=None, notes=None):
        """A new run that sends the model its own page back (T-0103): the same system prompt, the original request, the
        page as the model's previous answer, then what is wrong and a request for the whole corrected file. "What is
        wrong" is the browser's error (the 4B coder often writes pages that never run: a name declared twice, a variable
        out of scope, an import an addon does not export) and/or the owner's notes on what the render shows (a wall or
        side never modelled, parts floating), which no error check can see. The card itself expects retries and small
        corrections, and its showcase assets went through a validation harness."""
        error = error.strip()[:GLB_REPAIR_ERROR_MAX] if isinstance(error, str) else ""
        notes = notes.strip()[:GLB_REPAIR_NOTES_MAX] if isinstance(notes, str) else ""
        if not error and not notes:
            raise ApiError(400, "invalid_params", "give the page check's error, notes on what to change, or both")
        source = self._get(job_id)
        page = self.html(job_id).decode("utf-8", "replace")
        parts = []
        if error:
            parts.append(GLB_REPAIR_ERROR.format(error=error))
        if notes:
            parts.append(GLB_REPAIR_NOTES.format(notes=notes))
        parts.append(GLB_REPAIR_CLOSE)
        messages = [{"role": "system", "content": GLB_SYSTEM_PROMPT}, {"role": "user", "content": source["prompt"]},
                    {"role": "assistant", "content": page}, {"role": "user", "content": "\n\n".join(parts)}]
        extra = {"repair_of": source["id"], "repair_error": error or None, "repair_notes": notes or None}
        return self._start(source["prompt"], messages, extra)

    def _start(self, prompt, messages, extra):
        with self._lock:
            busy = [j for j in self._jobs.values() if j["state"] in ("queued", "waiting", "thinking", "writing")]
            if busy:
                raise ApiError(409, "busy", "a GLB generation is already running (%s); wait for it or cancel it" % busy[0]["id"])
            job = {"id": uuid.uuid4().hex, "prompt": prompt, "state": "queued", "created": time.time(),
                   "first_token": None, "finished": None, "reasoning_chars": 0, "content_chars": 0,
                   "reasoning_tail": "", "content_tail": "", "has_html": False, "error": None,
                   "finish_reason": None, "usage": None, "timings": None, "_cancel": False, "_conn": None,
                   "_content": [], "_messages": messages}
            job.update(extra)
            self._jobs[job["id"]] = job
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return self.status(job["id"])

    def _router_json(self, method, path, body=None, timeout=20):
        conn = http.client.HTTPConnection(self.host, self.port, timeout=timeout)
        try:
            data = json.dumps(body).encode() if body is not None else None
            conn.request(method, self.prefix + path, data, {"Content-Type": "application/json"} if data else {})
            resp = conn.getresponse()
            raw = resp.read()
            try:
                return resp.status, json.loads(raw or b"{}")
            except ValueError:
                return resp.status, {"error": raw.decode("utf-8", "replace")[:300]}
        finally:
            conn.close()

    def gpu(self):
        """Whether the GLB coder is the loaded model now, and the state of a warm-up started from this page."""
        loaded = None
        try:
            status, current = self._router_json("GET", "/models/status")
            if status == 200:
                names = [current.get("active_model")] + list(current.get("active_aliases") or [])
                loaded = next((n for n in names if n == self.model), current.get("active_model"))
        except (OSError, http.client.HTTPException):
            loaded = None
        with self._lock:
            warm = dict(self._warm)
        names = self.model_names()
        return {"model": self.model, "model_name": names.get(self.model, self.model), "loaded": loaded,
                "loaded_name": names.get(loaded, loaded), "ready": loaded == self.model, "warmup": warm}

    def model_names(self):
        """Router model id -> its display name (the HF repo and file); {} when the router does not answer."""
        try:
            status, listing = self._router_json("GET", "/v1/models")
        except (OSError, http.client.HTTPException):
            return {}
        if status != 200 or not isinstance(listing, dict):
            return {}
        return {m["id"]: m.get("name") or m["id"] for m in listing.get("data") or [] if isinstance(m, dict) and m.get("id")}

    def warmup(self):
        """Ask the router to load the GLB coder now (POST /models/load; the router asks the GPU controller), so the
        first generation starts at once. Runs in the background; gpu() reports progress."""
        with self._lock:
            if self._warm["state"] == "loading":
                raise ApiError(409, "busy", "already warming up")
            self._warm = {"state": "loading", "started": time.time(), "finished": None, "error": None}

        def run():
            try:
                status, value = self._router_json("POST", "/models/load", {"model": self.model}, timeout=1800)
                ok = status == 200 and value.get("status") == "loaded"
                result = {"state": "ready" if ok else "failed", "error": None if ok else (value.get("error") or "HTTP %d" % status)}
            except (OSError, http.client.HTTPException) as exc:
                result = {"state": "failed", "error": "LLM router unreachable: %s" % exc}
            with self._lock:
                self._warm.update(result, finished=time.time())
        threading.Thread(target=run, daemon=True).start()
        return self.gpu()

    def status(self, job_id):
        job = self._get(job_id)
        with self._lock:
            out = {k: v for k, v in job.items() if not k.startswith("_")}
        now = out["finished"] or time.time()
        out["elapsed_seconds"] = round(now - out["created"], 1)
        return out

    def jobs(self):
        with self._lock:
            ids = sorted(self._jobs, key=lambda i: self._jobs[i]["created"], reverse=True)[:30]
        return [self.status(i) for i in ids]

    def cancel(self, job_id):
        job = self._get(job_id)
        with self._lock:
            if job["state"] not in ("queued", "waiting", "thinking", "writing"):
                raise ApiError(409, "not_running", "job is not running")
            job["_cancel"] = True
            conn = job["_conn"]
        if conn is not None:
            try:
                conn.sock and conn.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        return self.status(job_id)

    def html(self, job_id):
        job = self._get(job_id)
        if self.output_dir:
            path = self.output_dir / (job_id + ".html")
            if path.is_file():
                return path.read_bytes()
        html = job.get("_html")
        if html is None:
            raise ApiError(404, "no_html", "this job has no HTML page (yet)")
        return html.encode("utf-8")

    # ------------------------------------------------------------ internals
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
        body = {"model": self.model, "stream": True, "stream_options": {"include_usage": True},
                "messages": job.get("_messages") or [{"role": "system", "content": GLB_SYSTEM_PROMPT},
                                                     {"role": "user", "content": job["prompt"]}],
                "chat_template_kwargs": {"enable_thinking": True}}
        body.update(GLB_SAMPLING)
        data = json.dumps(body).encode()
        reasoning_tail, content_tail = "", ""
        conn = http.client.HTTPConnection(self.host, self.port, timeout=self.read_timeout)
        self._update(job, _conn=conn, state="waiting")
        try:
            # the router holds this request while the GPU controller switches to the model (minutes from cold)
            conn.request("POST", self.prefix + "/v1/chat/completions", data,
                         {"Content-Type": "application/json", "Accept": "text/event-stream",
                          "X-Watoom-Request-Id": "creation-studio-glb-" + job["id"]})
            resp = conn.getresponse()
            if resp.status != 200:
                raw = resp.read(4096)
                try:
                    message = json.loads(raw)["error"]["message"]
                except (ValueError, KeyError, TypeError):
                    message = raw.decode("utf-8", "replace")[:300] or ("HTTP %d" % resp.status)
                raise ApiError(502, "router_error", "LLM router HTTP %d: %s" % (resp.status, message))
            windows, unchecked = {"thinking": "", "page": ""}, 0
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
                        reasoning_tail = (reasoning_tail + thought)[-GLB_TAIL:]
                        changes.update(state="thinking", reasoning_tail=reasoning_tail,
                                       reasoning_chars=job["reasoning_chars"] + len(thought))
                    if text:
                        job["_content"].append(text)
                        content_tail = (content_tail + text)[-GLB_TAIL:]
                        changes.update(state="writing", content_tail=content_tail,
                                       content_chars=job["content_chars"] + len(text))
                    if choice.get("finish_reason"):
                        changes["finish_reason"] = choice["finish_reason"]
                    for name, piece in (("thinking", thought), ("page", text)):
                        if piece:
                            windows[name] = (windows[name] + piece)[-GLB_LOOP_WINDOW:]
                            unchecked += len(piece)
                if changes:
                    self._update(job, **changes)
                if unchecked >= GLB_LOOP_CHECK_EVERY:
                    unchecked = 0
                    for name, window in windows.items():
                        period = repeating_block(window)
                        if period:
                            raise ApiError(502, "loop", "stopped: the model was repeating itself while %s (the same %d-character "
                                           "block over and over). Generate again or revise; each run differs."
                                           % ("thinking" if name == "thinking" else "writing the page", period))
                    if (job["reasoning_chars"] + job["content_chars"]) / GLB_CHARS_PER_TOKEN > GLB_MAX_TOKENS:
                        raise ApiError(502, "too_long", "stopped: past ~%dK tokens without finishing (answers average ~20K; "
                                       "the card's longest training example is 72K)" % (GLB_MAX_TOKENS // 1000))
            if job["_cancel"]:
                raise ApiError(499, "cancelled", "cancelled")
            content = "".join(job["_content"])
            html = extract_html(content)
            if html is None:
                raise ApiError(502, "no_html", "the answer has no complete HTML page (finish reason: %s)" % job["finish_reason"])
            self._update(job, _html=html, has_html=True, state="done")
        except ApiError as exc:
            self._update(job, state="cancelled" if exc.code == "cancelled" else "failed",
                         error=None if exc.code == "cancelled" else exc.message)
        except (OSError, http.client.HTTPException) as exc:
            self._update(job, state="cancelled" if job["_cancel"] else "failed",
                         error=None if job["_cancel"] else "LLM router stream failed: %s" % exc)
        finally:
            conn.close()
            self._update(job, _conn=None, finished=time.time())
            self._persist(job)

    def _persist(self, job):
        if not self.output_dir:
            return
        try:
            if job.get("_html"):
                (self.output_dir / (job["id"] + ".html")).write_text(job["_html"], encoding="utf-8")
            content = "".join(job["_content"])
            if content and not job.get("_html"):
                (self.output_dir / (job["id"] + ".answer.txt")).write_text(content, encoding="utf-8")
            meta = {k: v for k, v in job.items() if not k.startswith("_")}
            (self.output_dir / (job["id"] + ".json")).write_text(json.dumps(meta, indent=1), encoding="utf-8")
        except OSError as exc:
            self._update(job, error=(job.get("error") or "") + " (could not save the result: %s)" % exc)


# ---------------------------------------------------------------- HTTP
def make_handler(mm_client, moss_client, mesh_client, cfg, glb_coder=None):
    page = (HERE / "web" / "index.html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        server_version = "creation-studio"

        def log_message(self, *args):
            pass

        def _send(self, status, body, ctype="application/json", extra=None, csp=None):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", csp or
                              "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status, obj):
            self._send(status, json.dumps(obj).encode())

        def _read_json_body(self):
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                raise ApiError(415, "unsupported", "Content-Type must be application/json")
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                raise ApiError(413, "too_large", "request body too large")
            try:
                return json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                raise ApiError(400, "invalid_params", "body is not valid JSON")

        def _proxy_mm(self, fn):
            try:
                return fn()
            except ModelManagerError:
                raise
            except ApiError:
                raise
            except (OSError, http.client.HTTPException) as exc:
                raise ApiError(503, "model_manager_unreachable", "Model Manager is unreachable: %s" % exc)

        def _route(self, method):
            path = self.path.split("?", 1)[0]
            query = self.path[len(path):]

            if method == "GET" and path in ("/", "/index.html"):
                return self._send(200, page, "text/html; charset=utf-8")
            if method == "GET" and path == "/api/config":
                return self._json(200, {"model_manager_origin": cfg["mm_origin"], "moss_origin": cfg["moss_label"]})
            if method == "GET" and path == "/api/mesh/status":
                return self._json(200, mesh_status(cfg["mesh_observability_path"], wired=bool(mesh_client)))
            if path in ("/api/mesh/generate", "/api/mesh/jobs", "/api/mesh/job", "/api/mesh/result"):
                if not mesh_client:
                    raise ApiError(503, "mesh_not_configured", MESH_BLOCKER)
                if method == "POST" and path == "/api/mesh/generate":
                    body = self._read_json_body()
                    prompt = body.get("prompt")
                    if not isinstance(prompt, str) or not prompt.strip():
                        raise ApiError(400, "invalid_params", "prompt is required")
                    kwargs = {k: body[k] for k in ("name", "seed", "temperature", "max_tokens", "request_id") if k in body}
                    return self._json(202, mesh_client.generate(prompt, **kwargs))
                if method == "GET" and path == "/api/mesh/jobs":
                    return self._json(200, mesh_client.jobs())
                if method == "GET" and path == "/api/mesh/job":
                    job_id = urllib.parse.parse_qs(query.lstrip("?")).get("id", [""])[0]
                    return self._json(200, mesh_client.job_status(job_id))
                if method == "GET" and path == "/api/mesh/result":
                    job_id = urllib.parse.parse_qs(query.lstrip("?")).get("id", [""])[0]
                    return self._json(200, mesh_client.result(job_id))
                raise ApiError(404, "not_found", "not found")

            if path.startswith("/api/glb/"):
                sub = path[len("/api/glb/"):]
                if not glb_coder:
                    raise ApiError(503, "glb_not_configured", "GLB 3D Coder is not configured (no --glb-router-base)")
                job_id = urllib.parse.parse_qs(query.lstrip("?")).get("id", [""])[0]
                if method == "GET" and sub == "config":
                    return self._json(200, glb_coder.config())
                if method == "GET" and sub == "gpu":
                    return self._json(200, glb_coder.gpu())
                if method == "POST" and sub == "warmup":
                    self._read_json_body()
                    return self._json(202, glb_coder.warmup())
                if method == "GET" and sub == "jobs":
                    return self._json(200, glb_coder.jobs())
                if method == "GET" and sub == "job":
                    return self._json(200, glb_coder.status(job_id))
                if method == "POST" and sub == "generate":
                    prompt = self._read_json_body().get("prompt")
                    if not isinstance(prompt, str):
                        raise ApiError(400, "invalid_params", "prompt is required")
                    return self._json(202, glb_coder.submit(prompt))
                if method == "POST" and sub == "repair":
                    body = self._read_json_body()
                    if not isinstance(body.get("id"), str):
                        raise ApiError(400, "invalid_params", "id is required")
                    return self._json(202, glb_coder.repair(body["id"], body.get("error"), body.get("notes")))
                if method == "POST" and sub == "cancel":
                    return self._json(200, glb_coder.cancel(job_id))
                if method == "GET" and sub == "page":
                    html = glb_coder.html(job_id)
                    if "download=1" in query:
                        return self._send(200, html, "text/html; charset=utf-8",
                                          {"Content-Disposition": 'attachment; filename="glb-3d-coder-%s.html"' % job_id[:8]})
                    return self._send(200, with_error_reporter(html), "text/html; charset=utf-8", csp=GLB_PAGE_CSP)
                raise ApiError(404, "not_found", "not found")

            if path.startswith("/api/sdxl/"):
                sub = path[len("/api/sdxl/"):]
                if not mm_client:
                    raise ApiError(503, "model_manager_disabled", "Model Manager integration is not configured")
                if method == "GET" and sub == "models":
                    return self._json(200, self._proxy_mm(mm_client.models))
                if method == "GET" and sub == "jobs":
                    return self._json(200, self._proxy_mm(mm_client.jobs))
                if method == "GET" and sub == "result":
                    job_id = urllib.parse.parse_qs(query.lstrip("?")).get("id", [""])[0]
                    return self._json(200, self._proxy_mm(lambda: mm_client.result(job_id)))
                if method == "POST" and sub == "generate":
                    body = self._read_json_body()
                    model_id, revision, prompt = body.get("id"), body.get("revision"), body.get("prompt")
                    if not all(isinstance(x, str) and x for x in (model_id, revision, prompt)):
                        raise ApiError(400, "invalid_params", "id, revision and prompt are required")
                    return self._json(202, self._proxy_mm(lambda: mm_client.generate(model_id, revision, prompt)))
                raise ApiError(404, "not_found", "not found")

            if path.startswith("/api/moss/"):
                sub = "/api/" + path[len("/api/moss/"):]
                body = self._read_json_body() if method == "POST" else None
                status, ctype, raw = moss_client.request(method, sub + query, body)
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


def build(args):
    mm_client = None
    if args.model_manager_base:
        password = pathlib.Path(args.model_manager_password_file).read_text().strip()
        mm_client = ModelManagerClient(args.model_manager_base, args.model_manager_origin, password,
                                        ca_file=args.model_manager_ca_file or None)
    moss_client = MossClient(args.moss_base)
    mesh_client = MeshClient(args.mesh_bridge_socket) if args.mesh_bridge_socket else None
    cfg = {"mm_origin": args.model_manager_base or "", "moss_label": args.moss_base,
           "mesh_observability_path": args.mesh_observability_path}
    glb_coder = GlbCoder(args.glb_router_base, args.glb_model, args.glb_output_dir) if args.glb_router_base else None
    return mm_client, moss_client, mesh_client, cfg, glb_coder


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8792)
    ap.add_argument("--model-manager-base", default="https://glance.internal.homelab.example/model-manager",
                     help="Model Manager base URL (empty disables the SDXL pipeline)")
    ap.add_argument("--model-manager-origin", default="https://glance.internal.homelab.example",
                     help="Origin header Model Manager expects (its --origin argument)")
    ap.add_argument("--model-manager-password-file", default="/data/ai/private/model-manager/password")
    ap.add_argument("--model-manager-ca-file", default="",
                     help="PEM CA bundle to trust for --model-manager-base when it is https (the internal watoom-tls CA; empty uses the system trust store)")
    ap.add_argument("--moss-base", default="http://10.242.0.1:8791", help="MOSS Image Studio base URL")
    ap.add_argument("--mesh-observability-path", default="/data/ai/helper-scripts/state/gpu-controller-observability/status.json")
    ap.add_argument("--mesh-bridge-socket", default="",
                     help="opencode_mesh_bridge.py Unix socket path (empty disables Mesh generation; "
                          "this process's real UID must be on the bridge's allow-list)")
    ap.add_argument("--glb-router-base", default="",
                     help="LLM router base URL for the GLB 3D Coder section (empty disables it), e.g. http://10.243.133.2:8000")
    ap.add_argument("--glb-model", default="glb-3d-coder", help="router model id of ccore/Qwen3.5-4B-GLB-3D-Coder")
    ap.add_argument("--glb-output-dir", default="", help="where finished pages and job records are kept (empty = memory only)")
    args = ap.parse_args(argv)
    mm_client, moss_client, mesh_client, cfg, glb_coder = build(args)
    httpd = ThreadingHTTPServer((args.host, args.port), make_handler(mm_client, moss_client, mesh_client, cfg, glb_coder))
    print("creation-studio listening on http://%s:%d" % (args.host, httpd.server_address[1]), flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
