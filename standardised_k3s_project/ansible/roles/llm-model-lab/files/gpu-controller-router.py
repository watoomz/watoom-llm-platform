import json
from client import GPUClient
def gpu_controller_check(model_id="swift-qwen38-coder",allow_switch=False):
    canonical=MODEL_ALIASES.get(model_id,model_id)
    target=MODELS[canonical]
    result=GPUClient('/gpu-controller/router.sock',timeout=1500 if allow_switch else 10).call('request-model',deployment=target['deployment'],allow_switch=allow_switch)
    if result.get('allowed') is not True:raise RuntimeError('GPU owned or controller unavailable')
import os
import ssl
from collections import deque
import time
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

NAMESPACE = os.environ.get("POD_NAMESPACE", "llama-cpp")
TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
API = "https://kubernetes.default.svc"
MODELS = {
    "swift-qwen38-coder": {
        "deployment": "llama-cpp-swift-qwen38-coder",
        "url": "http://llama-cpp-swift-qwen38-coder.llama-cpp.svc.cluster.local:8000",
        "name": "Swift Qwen3.8 27B Coder 32K Stable",
    },
    "qwen38-27b-ad-iq4-xs": {
        "deployment": "llama-cpp-qwen38-atomic",
        "url": "http://llama-cpp-qwen38-atomic.llama-cpp.svc.cluster.local:8000",
        "name": "Qwen3.8 General Atomic AD-IQ4_XS",
    },
    "qwen38-uncensored-mtp-iq4-xs": {
        "deployment": "llama-cpp-qwen38-uncensored-mtp",
        "url": "http://llama-cpp-qwen38-uncensored-mtp.llama-cpp.svc.cluster.local:8000",
        "name": "Qwen3.8 Uncensored MTP IQ4_XS",
    },
    "ornith-1.5-9b-q8": {
        "deployment": "llama-cpp-ornith-15-9b",
        "url": "http://llama-cpp-ornith-15-9b.llama-cpp.svc.cluster.local:8000",
        "name": "Ornith 1.5 9B Uncensored",
    },
    "qwen35-defiant-fable-9b-q8": {
        "deployment": "llama-cpp-qwen35-defiant-fable-9b",
        "url": "http://llama-cpp-qwen35-defiant-fable-9b.llama-cpp.svc.cluster.local:8000",
        "name": "Qwen3.5 9B Defiant Fable plusIQ-TOOLS",
    },
    "gemma-4-e4b-q8-k-p": {
        "deployment": "llama-cpp-gemma-4-e4b",
        "url": "http://llama-cpp-gemma-4-e4b.llama-cpp.svc.cluster.local:8000",
        "name": "Gemma 4 E4B Uncensored HauhauCS Aggressive",
    },
    "tiel-coder-35b-a3b-mtp": {
        "deployment": "llama-cpp-tiel-coder-35b-a3b-mtp",
        "url": "http://llama-cpp-tiel-coder-35b-a3b-mtp.llama-cpp.svc.cluster.local:8000",
        "name": "CyberTiel Coder 35B-A3B MTP IQ4_XS",
    },
}
DEFAULT_MODEL = "active-model"
ACTIVE_MODEL_ALIAS = "active-model"

MODEL_ALIASES = {
    "qwen38-general": "qwen38-27b-ad-iq4-xs",
    "qwen38-uncensored-mtp": "qwen38-uncensored-mtp-iq4-xs",
    "ornith-1.5-9b": "ornith-1.5-9b-q8",
    "qwen35-defiant-fable-9b": "qwen35-defiant-fable-9b-q8",
    "gemma-4-e4b": "gemma-4-e4b-q8-k-p",
}
VISIBLE_MODELS = {
    ACTIVE_MODEL_ALIAS: "Active Homelab Model / Loaded Backend",
    "swift-qwen38-coder": "Swift Qwen3.8 27B Coder / 32K Stable",
    "qwen38-general": "Qwen3.8 General Atomic AD-IQ4_XS",
    "qwen38-uncensored-mtp": "Qwen3.8 Uncensored MTP IQ4_XS",
    "ornith-1.5-9b": "Ornith 1.5 9B Uncensored",
    "qwen35-defiant-fable-9b": "Qwen3.5 9B Defiant Fable plusIQ-TOOLS",
    "gemma-4-e4b": "Gemma 4 E4B Uncensored HauhauCS Aggressive",
    "tiel-coder-35b-a3b-mtp": "CyberTiel Coder 35B-A3B MTP IQ4_XS",
}
START_TIMEOUT = int(os.environ.get("START_TIMEOUT_SECONDS", "240"))
STOP_TIMEOUT = int(os.environ.get("STOP_TIMEOUT_SECONDS", "120"))
SWITCH_LOCK_TIMEOUT = int(os.environ.get("SWITCH_LOCK_TIMEOUT_SECONDS", "300"))
# 2026-11-19: while the controller switches models (5-7 min for a 27B gguf read fresh from disk) it handles one request
# at a time, so every other request's begin-inference timed out after 10 s and the router answered 503: watoom-code saw a
# burst of 503s and gave up. A request now WAITS while a switch this router started is in flight, up to this many seconds.
SWITCH_WAIT_SECONDS = int(os.environ.get("SWITCH_WAIT_SECONDS", "900"))
SWITCHES_IN_FLIGHT = [0]
SWITCHES_IN_FLIGHT_LOCK = threading.Lock()


def switch_in_progress():
    with SWITCHES_IN_FLIGHT_LOCK:
        return SWITCHES_IN_FLIGHT[0] > 0 or MODEL_SWITCH_LOCK.locked()


def begin_inference(client, deployment, allow_switch):
    """begin-inference lease; a request that may switch counts as an in-flight switch; any other request that fails
    while a switch is in flight retries every 5 s until it ends or SWITCH_WAIT_SECONDS pass (then the error stands)."""
    deadline = time.monotonic() + SWITCH_WAIT_SECONDS
    waited = False
    while True:
        if allow_switch:
            with SWITCHES_IN_FLIGHT_LOCK:
                SWITCHES_IN_FLIGHT[0] += 1
        try:
            lease = client.call('begin-inference', deployment=deployment, allow_switch=allow_switch)['lease']
            if waited:
                print("[MODEL-SWITCH] action=waited-for-switch deployment=" + deployment, flush=True)
            return lease
        except Exception:
            if allow_switch or time.monotonic() >= deadline or not switch_in_progress():
                raise
            if not waited:
                print("[MODEL-SWITCH] action=wait-for-switch deployment=" + deployment, flush=True)
            waited = True
            time.sleep(5)
        finally:
            if allow_switch:
                with SWITCHES_IN_FLIGHT_LOCK:
                    SWITCHES_IN_FLIGHT[0] -= 1

# ThreadingHTTPServer processes requests concurrently. GPU model lifecycle
# changes must therefore be serialized independently of inference traffic.
MODEL_SWITCH_LOCK = threading.Lock()
MODEL_SWITCH_STATE_LOCK = threading.Lock()
MODEL_SWITCH_STATE = {
    "switching": False,
    "requested_model": None,
    "target_deployment": None,
    "started_at": None,
    "last_error": None,
}

MODEL_CALL_LIMIT = int(os.environ.get("WATOOM_MODEL_MAX_CALLS", "3"))
MODEL_CALL_TTL_SECONDS = int(os.environ.get("WATOOM_MODEL_CALL_TTL_SECONDS", "900"))
MODEL_CALL_COUNTS = {}
MODEL_CALL_LOCK = threading.Lock()

def register_model_call(request_id):
    """Count one HTTP model call for a Pi correlation id.

    Requests without the WatooM correlation header are not rate-limited here;
    normal Open WebUI/direct router traffic remains unaffected.  The counter is
    intentionally independent of the client-supplied model-call number.
    """
    if not request_id or request_id == "-":
        return None
    now = time.time()
    with MODEL_CALL_LOCK:
        stale = [key for key, item in MODEL_CALL_COUNTS.items()
                 if now - item["last_seen"] > MODEL_CALL_TTL_SECONDS]
        for key in stale:
            MODEL_CALL_COUNTS.pop(key, None)
        item = MODEL_CALL_COUNTS.setdefault(request_id, {"count": 0, "last_seen": now})
        item["count"] += 1
        item["last_seen"] = now
        return item["count"]
def token():
    with open(TOKEN_PATH, "r", encoding="utf-8") as handle:
        return handle.read().strip()

def k8s(path, method="GET", body=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(API + path, data=data, method=method)
    req.add_header("Authorization", "Bearer " + token())
    req.add_header("Accept", "application/json")
    if body is not None:
        req.add_header("Content-Type", "application/merge-patch+json")
    ctx = ssl.create_default_context(cafile=CA_PATH)
    with urllib.request.urlopen(req, timeout=20, context=ctx) as response:
        return json.loads(response.read().decode("utf-8"))

def deploy(name):
    return k8s(f"/apis/apps/v1/namespaces/{NAMESPACE}/deployments/{name}")

def scale(name, replicas):
    raise RuntimeError('Direct scaling retired; GPU controller is the sole writer')


def is_available(name):
    d = deploy(name)
    status = d.get("status", {})
    return status.get("readyReplicas", 0) >= 1 and status.get("availableReplicas", 0) >= 1

def active_deployment():
    for model in MODELS.values():
        try:
            if is_available(model["deployment"]):
                return model["deployment"]
        except Exception:
            pass
    return None

def active_model():
    """Return (canonical_model_id, model_spec) for the already-active backend.

    This helper is intentionally read-only. It never scales deployments.
    """
    deployment = active_deployment()
    if not deployment:
        return None, None

    for canonical_model_id, model_spec in MODELS.items():
        if model_spec["deployment"] == deployment:
            return canonical_model_id, model_spec

    return None, None


def desired_replicas(name):
    d = deploy(name)
    return int(
        (d.get("spec") or {}).get("replicas") or 0
    )

def deployment_pods(name):
    """Return pods selected by a model Deployment."""
    d = deploy(name)

    selector = (
        (d.get("spec") or {})
        .get("selector", {})
        .get("matchLabels", {})
    )

    if not selector:
        return []

    label_selector=",".join(
        f"{key}={value}"
        for key,value in sorted(selector.items())
    )

    path=(
        f"/api/v1/namespaces/{NAMESPACE}/pods"
        "?labelSelector="
        + urllib.parse.quote(label_selector)
    )

    result=k8s(path)

    return result.get("items") or []

def deployment_has_live_pods(name):
    """True until all pods for the deployment have fully terminated."""
    for pod in deployment_pods(name):
        metadata=pod.get("metadata") or {}
        status=pod.get("status") or {}

        # A deleting pod can still own the GPU until its containers exit.
        if metadata.get("deletionTimestamp"):
            return True

        phase=status.get("phase")

        if phase not in ("Succeeded","Failed"):
            return True

    return False

def wait_stopped(name, timeout):
    """Wait for replicas=0 AND disappearance of live deployment pods."""
    deadline=time.time()+timeout
    last=None

    while time.time() < deadline:
        try:
            replicas=desired_replicas(name)
            live=deployment_has_live_pods(name)

            last={
                "replicas": replicas,
                "live_pods": live,
            }

            if replicas == 0 and not live:
                return True

        except Exception as exc:
            last={"error":str(exc)}

        time.sleep(2)

    raise TimeoutError(
        f"deployment {name} did not fully stop "
        f"within {timeout}s; last={last}"
    )

def wait_available(name, timeout):
    deadline=time.time()+timeout
    last_error=None

    while time.time() < deadline:
        try:
            if is_available(name):
                return True
        except Exception as exc:
            last_error=exc

        time.sleep(3)

    raise TimeoutError(
        f"deployment {name} was not ready "
        f"within {timeout}s; "
        f"last_error={last_error}"
    )

def wait_health(base_url, timeout):
    deadline=time.time()+timeout
    last_error=None

    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                base_url+"/health",
                timeout=10,
            ) as response:
                if response.status == 200:
                    return True

        except Exception as exc:
            last_error=exc

        time.sleep(3)

    raise TimeoutError(
        f"service {base_url} was not healthy "
        f"within {timeout}s; "
        f"last_error={last_error}"
    )

def set_switch_state(**updates):
    with MODEL_SWITCH_STATE_LOCK:
        MODEL_SWITCH_STATE.update(updates)

def switch_state():
    with MODEL_SWITCH_STATE_LOCK:
        return dict(MODEL_SWITCH_STATE)

def ensure_model(model_id, allow_switch=False):
    model_id=MODEL_ALIASES.get(model_id,model_id)
    if model_id not in MODELS:raise ValueError('unknown model: '+model_id)
    target=MODELS[model_id]
    target_deploy=target['deployment']
    if not MODEL_SWITCH_LOCK.acquire(timeout=SWITCH_LOCK_TIMEOUT):
        raise TimeoutError('Router lifecycle lock timeout')
    # WATOOM_MESH_EXTERNAL_GUARD_V1: protect host-owned Mesh jobs against router-triggered switches.
    # No new RBAC: the existing router role already has deployments GET.
    # Checked after acquiring the router lock; host worker may own Mesh independently.
    try:
        mesh_external_active = (
            target_deploy != "llama-cpp-llama-mesh"
            and desired_replicas("llama-cpp-llama-mesh") > 0
        )
    except Exception:
        MODEL_SWITCH_LOCK.release()
        raise
    if mesh_external_active:
        MODEL_SWITCH_LOCK.release()
        print("[MODEL-SWITCH] action=blocked-external-mesh requested=" + model_id, flush=True)
        raise RuntimeError("model switch temporarily blocked: LLaMA-Mesh owns GPU")

    try:
        gpu_controller_check(model_id,allow_switch)
        wait_available(target_deploy,START_TIMEOUT)
        wait_health(target['url'],30)
        return target
    finally:
        MODEL_SWITCH_LOCK.release()




# 2026-11-19 (owner): WatooM Code's per-model context budget scales with the model's real llama-server context: a 128K
# server (the ~17 GB 27B models) gets 100K in WatooM Code, a smaller model with a bigger server context proportionally
# more (256K -> 200K). The Deployment's --ctx-size / LLAMA_ARG_CTX_SIZE is the source (cached; RBAC: get deployments).
DEFAULT_APPLICATION_CONTEXT = int(os.environ.get("DEFAULT_APPLICATION_CONTEXT", "100000"))
APPLICATION_CONTEXT_RATIO = 100000 / 131072


def application_budget(served):
    # never below the previous fixed budget (min(served, 100000)), so no model loses context
    return max(min(served, 100000), int(served * APPLICATION_CONTEXT_RATIO) // 1000 * 1000) if served else None
DEPLOYMENT_CONTEXT_TTL = 300
DEPLOYMENT_CONTEXT = {}
DEPLOYMENT_CONTEXT_LOCK = threading.Lock()


def server_context(container):
    args = container.get("args") or []
    for index, arg in enumerate(args):
        if arg in ("--ctx-size", "-c") and index + 1 < len(args):
            return int(args[index + 1])
    for env in container.get("env") or []:
        if env.get("name") == "LLAMA_ARG_CTX_SIZE" and env.get("value"):
            return int(env["value"])
    return None


def server_vision(container):
    """True when llama-server loads a vision projector (--mmproj / LLAMA_ARG_MMPROJ) (T-0095)."""
    if "--mmproj" in (container.get("args") or []):
        return True
    return any(env.get("name") == "LLAMA_ARG_MMPROJ" and env.get("value") for env in container.get("env") or [])


def deployment_facts(name):
    """{"context": served --ctx-size, "vision": bool} from the Deployment; cached, last value kept on errors."""
    now = time.time()
    with DEPLOYMENT_CONTEXT_LOCK:
        cached = DEPLOYMENT_CONTEXT.get(name)
    if cached and now - cached[0] < DEPLOYMENT_CONTEXT_TTL:
        return cached[1]
    try:
        container = deploy(name)["spec"]["template"]["spec"]["containers"][0]
        value = {"context": server_context(container), "vision": server_vision(container)}
    except Exception:
        value = cached[1] if cached else {"context": None, "vision": None}
    with DEPLOYMENT_CONTEXT_LOCK:
        DEPLOYMENT_CONTEXT[name] = (now, value)
    return value


def model_list():
    data = []
    for model_id, name in VISIBLE_MODELS.items():
        spec = MODELS.get(MODEL_ALIASES.get(model_id, model_id), {})
        facts = deployment_facts(spec["deployment"]) if spec.get("deployment") else {"context": None, "vision": None}
        served = facts["context"]
        data.append({
            "id": model_id,
            "object": "model",
            "created": 0,
            "owned_by": "llm-router",
            "name": name,
            "context_limit": spec.get("context_limit"),
            "application_context": application_budget(served) or spec.get("application_context") or DEFAULT_APPLICATION_CONTEXT,
            "vision": facts["vision"],
        })
    return {"object": "list", "data": data}

def lifecycle_catalog():
    models = []

    for model_id, spec in MODELS.items():
        aliases = sorted(
            alias
            for alias, canonical in MODEL_ALIASES.items()
            if canonical == model_id
        )
        models.append({
            "id": model_id,
            "aliases": aliases,
            "deployment": spec["deployment"],
            "llama_cpp_alias": model_id,
        })

    return {
        "models": models,
        "available_model_ids": sorted(
            set(MODELS) | set(MODEL_ALIASES)
        ),
    }

def lifecycle_status():
    model_id, spec = active_model()

    if not model_id or not spec:
        return {
            "active_model": None,
            "active_aliases": [],
            "active_deployment": None,
        }

    aliases = sorted(
        alias
        for alias, canonical in MODEL_ALIASES.items()
        if canonical == model_id
    )

    return {
        "active_model": model_id,
        "active_aliases": aliases,
        "active_deployment": spec["deployment"],
        "llama_cpp_alias": model_id,
    }

MODELS["llama-mesh-q8"] = {"deployment": "llama-cpp-llama-mesh", "url": "http://llama-cpp-llama-mesh.llama-cpp.svc.cluster.local:8000", "name": "LLaMA-Mesh 8B Q8_0"}
MODEL_ALIASES["llama-mesh"] = "llama-mesh-q8"
VISIBLE_MODELS["llama-mesh"] = "LLaMA-Mesh 8B Q8_0 / Text-to-3D"

_MANAGED_IDS=set()
def refresh_managed_catalog():
    """Read only the root broker's derived view; never accepts a URL from clients."""
    global _MANAGED_IDS, MODELS, VISIBLE_MODELS
    path=os.environ.get("WATOOM_MANAGED_CATALOG")
    if not path:return
    from pathlib import Path
    try:
        doc=json.loads(Path(path).read_text())
        if doc.get("version")!=1:raise ValueError("Invalid managed view")
        current=doc["models"]
        import re
        for alias,entry in current.items():
            if not re.fullmatch(r"mm-[a-f0-9]{16}",alias) or entry["deployment"]!="llama-cpp-"+alias:
                raise ValueError("Invalid managed route identity")
            expected="http://"+entry["deployment"]+"."+NAMESPACE+".svc.cluster.local:8080"
            if entry["url"]!=expected:raise ValueError("Invalid managed backend URL")
        models={key:value for key,value in MODELS.items() if key not in _MANAGED_IDS}
        visible={key:value for key,value in VISIBLE_MODELS.items() if key not in _MANAGED_IDS}
        for alias,entry in current.items():
            models[alias]=entry
            if entry["backend"]=="gguf":visible[alias]=entry["name"]
        MODELS,VISIBLE_MODELS=models,visible
        _MANAGED_IDS=set(current)
    except FileNotFoundError:
        if _MANAGED_IDS:raise RuntimeError("Managed catalog disappeared")

PERF_WINDOW_SECONDS = 86400
PERF_EVENTS = deque(maxlen=10000)
PERF_LOCK = threading.Lock()

def sse_has_generated_output(line):
    if not line.startswith(b"data:"):
        return False
    raw = line.partition(b":")[2].strip()
    if not raw or raw == b"[DONE]":
        return False
    try:
        event = json.loads(raw)
        for choice in event.get("choices", []):
            delta = choice.get("delta") or {}
            if any(delta.get(key) for key in ("content", "reasoning_content", "tool_calls", "function_call")) or choice.get("text"):
                return True
    except (ValueError, AttributeError, TypeError):
        return False
    return False


def record_perf(effort, status, latency_ms, ttft_ms):
    row = {"at": time.time(), "effort": effort, "status": int(status),
           "latency_ms": round(latency_ms, 1), "ttft_ms": round(ttft_ms, 1) if ttft_ms is not None else None}
    with PERF_LOCK:
        PERF_EVENTS.append(row)

def performance_summary(now=None):
    now = time.time() if now is None else now
    with PERF_LOCK:
        rows = [r.copy() for r in PERF_EVENTS if now - r["at"] <= PERF_WINDOW_SECONDS]
    result = {}
    for effort in ("low", "medium", "high", "xhigh", "unset", "other"):
        group = [r for r in rows if (r["effort"] if r["effort"] in ("low", "medium", "high", "xhigh", "unset") else "other") == effort]
        if not group:
            result[effort] = {"requests": 0, "latency_p50_ms": None, "latency_p95_ms": None, "ttft_p50_ms": None,
                              "errors": 0, "http_503": 0, "generation_tokens_per_second": None,
                              "prompt_tokens_per_second": None}
            continue
        latencies = sorted(r["latency_ms"] for r in group)
        ttfts = sorted(r["ttft_ms"] for r in group if r["ttft_ms"] is not None)
        percentile = lambda values, q: values[max(0, min(len(values)-1, int(q*len(values)+.999999)-1))] if values else None
        result[effort] = {"requests": len(group), "latency_p50_ms": round(percentile(latencies, .50), 1),
                          "latency_p95_ms": round(percentile(latencies, .95), 1),
                          "ttft_p50_ms": round(percentile(ttfts, .50), 1) if ttfts else None,
                          "errors": sum(r["status"] >= 400 for r in group),
                          "http_503": sum(r["status"] == 503 for r in group),
                          "generation_tokens_per_second": None, "prompt_tokens_per_second": None}
    return {"window_seconds": PERF_WINDOW_SECONDS, "generated": now, "levels": result}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} {self.command} {self.path} " + (fmt % args), flush=True)

    def send_json(self, status, payload):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        refresh_managed_catalog()
        if self.path == "/performance":
            self.send_json(200, performance_summary())
            return
        if self.path == "/healthz":
            self.send_json(200, {"status": "ok"})
            return
        if self.path in ("/health", "/"):
            self.send_json(200, {"status": "ok", "active_deployment": active_deployment()})
            return
        if self.path == "/v1/models":
            self.send_json(200, model_list())
            return
        if self.path == "/models":
            self.send_json(200, lifecycle_catalog())
            return
        if self.path == "/models/status":
            self.send_json(200, lifecycle_status())
            return
        self.proxy("GET")

    def do_POST(self):
        refresh_managed_catalog()
        if self.path == "/models/load":
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length else b"{}"

            try:
                payload = json.loads(body.decode("utf-8"))
                requested_model = str(payload.get("model") or "").strip()
                resolved_model = MODEL_ALIASES.get(
                    requested_model,
                    requested_model,
                )

                if resolved_model not in MODELS:
                    self.send_json(
                        404,
                        {
                            "error": "unknown model",
                            "requested_model": requested_model,
                            "mapped_router_model": resolved_model,
                            "available_model_ids": lifecycle_catalog()["available_model_ids"],
                        },
                    )
                    return

                target = ensure_model(requested_model, allow_switch=True)
                self.send_json(
                    200,
                    {
                        "status": "loaded",
                        "requested_model": requested_model,
                        "model": resolved_model,
                        "deployment": target["deployment"],
                    },
                )
            except Exception as exc:
                self.send_json(
                    503,
                    {
                        "error": str(exc),
                        "requested_model": locals().get("requested_model"),
                    },
                )
            return
        self.proxy("POST")

    def proxy(self, method):
        performance_started = time.monotonic()
        performance_effort = "unset"
        performance_enabled = False
        performance_status = 503
        performance_ttft = None
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b""
        model_id = DEFAULT_MODEL
        stream_requested = False
        # Defaults keep non-JSON/GET proxy paths safe and make the guard state
        # explicit outside the metadata try/except.
        tools = []
        payload = {}
        request_id = "-"
        model_call = "-"
        router_call = None
        active_only_target = None
        allow_request_switch = False
        if body:
            try:
                payload = json.loads(body.decode("utf-8"))
                model_id = payload.get("model") or DEFAULT_MODEL
                # OpenCode dropdown selection is carried in the inference model ID.
                allow_request_switch = (
                    method == "POST"
                    and self.path in ("/v1/chat/completions", "/v1/completions")
                    and bool(payload.get("model"))
                    and model_id != ACTIVE_MODEL_ALIAS
                )
                stream_requested = payload.get("stream") is True
                performance_enabled = method == "POST" and self.path in ("/v1/chat/completions", "/v1/completions")
                raw_effort = payload.get("reasoning_effort")
                performance_effort = str(raw_effort).lower() if raw_effort is not None else "unset"


                if model_id == ACTIVE_MODEL_ALIAS:
                    active_model_id, active_only_target = active_model()
                    if not active_model_id or not active_only_target:
                        self.send_json(
                            503,
                            {
                                "error": {
                                    "message": "No LLM backend is currently active",
                                    "type": "model_not_available",
                                    "code": "no_active_model",
                                }
                            },
                        )
                        if performance_enabled:
                            record_perf(performance_effort, 503, (time.monotonic() - performance_started) * 1000, None)
                        return
                    model_id = active_model_id

                # The public router aliases are not necessarily the aliases
                # exposed by the individual llama-server process. Select the
                # backend using MODEL_ALIASES and forward that same canonical
                # model id in the OpenAI request body.
                backend_model_id = MODEL_ALIASES.get(model_id, model_id)
                payload["model"] = backend_model_id
                body = json.dumps(payload).encode("utf-8")

                # Preserve every tool supplied by the calling client.
                #
                # The router does not maintain its own tool allowlist,
                # silently remove tools, impose a tool-count restriction,
                # or downgrade tool_choice.
                #
                # A generated tool call must still be validated against
                # this request's supplied tool definitions before it is
                # normalized/exposed to the client.
                # Fix captured instrumentation defect: `messages` was iterated below
                # without first being assigned, and the broad exception swallowed the
                # resulting NameError. Keep metadata content-free.
                messages = payload.get("messages") or []
                request_id = self.headers.get("X-Watoom-Request-Id") or "-"
                model_call = self.headers.get("X-Watoom-Model-Call") or "-"
                router_call = register_model_call(request_id)
                tools = payload.get("tools") or []

                tool_names = []
                for tool in tools:
                    try:
                        if tool.get("type") == "function":
                            tool_names.append(
                                (tool.get("function") or {}).get("name", "<unnamed>")
                            )
                        else:
                            tool_names.append(tool.get("type", "<unknown>"))
                    except Exception:
                        tool_names.append("<parse-error>")

                message_chars = 0
                for message in messages:
                    content = message.get("content", "")
                    if isinstance(content, str):
                        message_chars += len(content)
                    else:
                        message_chars += len(str(content))

                print(
                    "[REQMETA]"
                    f" request_id={request_id}"
                    f" model_call={model_call}"
                    f" router_call={router_call if router_call is not None else '-'}"
                    f" path={self.path}"
                    f" model={model_id}"
                    f" backend_model={backend_model_id}"
                    f" messages={len(messages)}"
                    f" message_chars={message_chars}"
                    f" tools={len(tools)}"
                    f" tool_names={tool_names}"
                    f" tool_choice={payload.get('tool_choice')}"
                    f" stream={payload.get('stream')}"
                    f" max_tokens={payload.get('max_tokens')}"
                    f" response_format={payload.get('response_format')}"
                    f" reasoning_effort={payload.get('reasoning_effort')}"
                    f" thinking_budget_tokens={payload.get('thinking_budget_tokens')}",
                    flush=True,
                )
            except Exception:
                pass
        if router_call is not None and router_call > MODEL_CALL_LIMIT:
            print(
                "[WATOOM_MODEL_GUARD]"
                f" request_id={request_id}"
                f" client_model_call={model_call}"
                f" router_call={router_call}"
                f" max_calls={MODEL_CALL_LIMIT}"
                " action=reject",
                flush=True,
            )
            self.send_json(
                429,
                {
                    "error": {
                        "type": "watoom_model_call_limit",
                        "message": f"model-call limit exceeded: {router_call} > {MODEL_CALL_LIMIT}",
                        "request_id": request_id,
                        "router_call": router_call,
                        "max_calls": MODEL_CALL_LIMIT,
                    }
                },
            )
            if performance_enabled:
                record_perf(performance_effort, 429, (time.monotonic() - performance_started) * 1000, None)
            return

        lease=None
        try:
            canonical=MODEL_ALIASES.get(model_id,model_id)
            request_account=GPUClient('/gpu-controller/router.sock',timeout=1500 if allow_request_switch else 10)
            lease=begin_inference(request_account,MODELS[canonical]['deployment'],allow_request_switch)
            gpu_controller_check(model_id,allow_request_switch)
            target = active_only_target or ensure_model(
                model_id, allow_switch=allow_request_switch
            )
            if target.get("backend")=="sdxl":
                raise RuntimeError("Use the model manager image-generation workflow for SDXL; chat is not supported")
            url = target["url"] + self.path
            req = urllib.request.Request(url, data=body if method != "GET" else None, method=method)
            for key, value in self.headers.items():
                if key.lower() not in ("host", "content-length", "connection"):
                    req.add_header(key, value)
            if target.get("backend"):
                from pathlib import Path
                key_file=os.environ.get("WATOOM_MANAGED_KEY")
                if not key_file:raise RuntimeError("Managed backend credentials unavailable")
                req.remove_header("Authorization")
                req.add_header("Authorization","Bearer "+Path(key_file).read_text().strip())
            with urllib.request.urlopen(req, timeout=600) as response:
                performance_status = response.status
                content_type = response.headers.get(
                    "Content-Type",
                    "",
                )

                backend_is_streaming = (
                    content_type
                    .lower()
                    .startswith("text/event-stream")
                )

                #
                #
                #
                #
                if backend_is_streaming:
                    self.send_response(response.status)

                    for key, value in response.headers.items():
                        if key.lower() not in (
                            "transfer-encoding",
                            "connection",
                            "content-length",
                        ):
                            self.send_header(key, value)

                    self.send_header(
                        "Transfer-Encoding",
                        "chunked",
                    )
                    self.end_headers()

                    event_buffer = b""
                    while True:
                        chunk = response.read(8192)
                        if not chunk:
                            break
                        event_buffer += chunk
                        while b"\n" in event_buffer:
                            line, event_buffer = event_buffer.split(b"\n", 1)
                            if performance_ttft is None and sse_has_generated_output(line):
                                performance_ttft = (time.monotonic() - performance_started) * 1000
                        if performance_ttft is None and sse_has_generated_output(event_buffer):
                            performance_ttft = (time.monotonic() - performance_started) * 1000

                        self.wfile.write(
                            f"{len(chunk):X}\r\n".encode("ascii")
                        )
                        self.wfile.write(chunk)
                        self.wfile.write(b"\r\n")
                        self.wfile.flush()

                    self.wfile.write(b"0\r\n\r\n")
                    self.wfile.flush()

                #
                # Standard non-streaming response.
                #
                else:
                    data = response.read()


                    self.send_response(response.status)

                    for key, value in response.headers.items():
                        if key.lower() not in (
                            "transfer-encoding",
                            "connection",
                            "content-length",
                        ):
                            self.send_header(key, value)

                    self.send_header(
                        "Content-Length",
                        str(len(data)),
                    )

                    self.end_headers()
                    self.wfile.write(data)

        except urllib.error.HTTPError as exc:
            performance_status = exc.code
            self.send_response(exc.code)
            data = exc.read()
            self.send_header("Content-Type", exc.headers.get("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as exc:
            performance_status = 503
            try:
                self.send_json(503, {"error": str(exc), "model": model_id})
            except (BrokenPipeError, ConnectionResetError):
                pass
        finally:
            if performance_enabled:
                record_perf(performance_effort, performance_status,
                            (time.monotonic() - performance_started) * 1000, performance_ttft)
            if lease:
                try:request_account.call('end-inference',lease=lease)
                except Exception:
                    # Durable lease intentionally survives uncertain cancellation.
                    print("[WATOOM_REQUEST_ACCOUNTING] completion unverified",flush=True)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"llm-router listening on :{port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
