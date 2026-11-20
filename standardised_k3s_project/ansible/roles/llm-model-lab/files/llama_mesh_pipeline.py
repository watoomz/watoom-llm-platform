#!/usr/bin/env python3
"""External, locked mesh jobs. No inference dependency in the controller."""

import argparse, base64, fcntl, hashlib, importlib.util, json, math, os, re, shutil, signal, struct, subprocess, sys, time, uuid
from datetime import datetime, timezone
from pathlib import Path
import urllib.request

sys.path.insert(0, "/data/ai/helper-scripts/gpu-controller")
from client import GPUClient

GPU_SOCKET = "/data/ai/helper-scripts/state/gpu-controller-private/worker.sock"


def gpu(action, **fields):
    return GPUClient(GPU_SOCKET, timeout=1500).call(action, **fields)


BASE = Path("/data/ai/helper-scripts")
CFG = BASE / "config/llama-mesh-pipeline.json"


def now():
    return datetime.now(timezone.utc).isoformat()


def read(p):
    return json.loads(Path(p).read_text())


def write(p, obj):
    p = Path(p)
    tmp = p.with_name(p.name + ".new")
    with tmp.open("w") as f:
        f.write(json.dumps(obj, indent=2) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)
    sync_dir(p.parent)


def sync_dir(p):
    fd = os.open(p, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def run(cmd, timeout=60, **kw):
    r = subprocess.run(cmd, timeout=timeout, capture_output=True, **kw)
    if r.returncode:
        raise RuntimeError(f'{cmd[:6]}: rc={r.returncode} {r.stderr.decode(errors="replace")[-2000:]}')
    return r.stdout


def cfg():
    return read(CFG)


def k(c, *args):
    return run(["kubectl", "-n", c["namespace"], *args])


def obj(c, kind, name):
    return json.loads(k(c, "get", kind, name, "-o", "json"))


def url(c, service):
    return "http://" + obj(c, "service", service)["spec"]["clusterIP"] + ":" + str(c["port"])


def http(u, p=None, timeout=30, raw=False):
    body = None if p is None else json.dumps(p).encode()
    req = urllib.request.Request(u, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(8388609)
    if len(data) > 8388608:
        raise RuntimeError("Response too large")
    return data if raw else json.loads(data)


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fingerprint(d):
    s = dict(d["spec"])
    s.pop("replicas", None)
    return s


def baseline(c):
    return read(c["baseline"])


def wait(c, d, ready):
    deadline = time.monotonic() + c["startup_timeout" if ready else "stop_timeout"]
    while time.monotonic() < deadline:
        deployment = obj(c, "deployment", d)
        pods = json.loads(k(c, "get", "pods", "-l", "app=" + d, "-o", "json"))["items"]
        if ready:
            if (
                deployment["spec"]["replicas"] == 1
                and deployment.get("status", {}).get("readyReplicas", 0) == 1
                and deployment["status"].get("observedGeneration", 0) >= deployment["metadata"]["generation"]
            ):
                if http(url(c, d) + "/health").get("status") == "ok":
                    return
        elif deployment["spec"]["replicas"] == 0 and not any(
            p["metadata"].get("deletionTimestamp") or p.get("status", {}).get("phase") not in ["Succeeded", "Failed"]
            for p in pods
        ):
            return
        time.sleep(2)
    raise TimeoutError(f'{d}: {"ready" if ready else "stopped"} timeout')


def scale(c, d, n):
    raise RuntimeError("Direct scaling retired; GPU controller is the sole writer")


def primary_check(c):
    b = baseline(c)
    d = obj(c, "deployment", c["primary"])
    if fingerprint(d) != fingerprint(b["primary"]):
        raise RuntimeError("Primary configuration differs from captured safe baseline")
    if obj(c, "service", c["primary"])["spec"] != b["primary_service"]["spec"]:
        raise RuntimeError("Primary Service drift")
    return d


def health(c):
    wait(c, c["primary"], True)
    primary_check(c)
    r = http(
        url(c, c["router"]) + "/v1/chat/completions",
        {
            "model": "active-model",
            "messages": [{"role": "user", "content": "Reply OK."}],
            "max_tokens": 128,
            "stream": False,
        },
        timeout=120,
    )
    if (
        r.get("model") != c["primary_alias"]
        or not r.get("choices")
        or not r["choices"][0].get("message", {}).get("content")
    ):
        raise RuntimeError("Primary ordinary inference failed or wrong model")
    return {"ready": "yes", "inference": "PASS", "model": r["model"], "checked_at": now()}


def safe(c):
    d = primary_check(c)
    if d["spec"]["replicas"] != 1:
        raise RuntimeError("Expected primary replicas=1")
    b = baseline(c)
    m = obj(c, "deployment", c["mesh"])
    if m["spec"]["replicas"] != 0 or fingerprint(m) != fingerprint(b["mesh"]):
        raise RuntimeError("Mesh configuration differs or already running")
    if obj(c, "service", c["mesh"])["spec"] != b["mesh_service"]["spec"]:
        raise RuntimeError("Mesh Service drift")
    active = [
        d["metadata"]["name"]
        for d in json.loads(k(c, "get", "deploy", "-o", "json"))["items"]
        if d["metadata"]["name"].startswith("llama-cpp-") and d["spec"].get("replicas", 0) > 0
    ]
    if active != [c["primary"]]:
        raise RuntimeError("Unexpected active model deployments: " + str(active))
    if Path(c["model_link"]).resolve() != Path(c["model_path"]):
        raise RuntimeError("Mesh active symlink changed")
    stat = Path(c["model_path"]).stat()
    if [stat.st_size, stat.st_mtime_ns] != c["model_stat"]:
        raise RuntimeError("Model file changed; verify hash and reconfigure")
    slots = http(url(c, c["primary"]) + "/slots")
    if any(s.get("is_processing") for s in slots):
        raise RuntimeError("Primary inference busy; retry when idle")
    if http(url(c, c["router"]) + "/models/status").get("active_deployment") != c["primary"]:
        raise RuntimeError("Router primary differs")


def lock(c, blocking=False):
    f = open(c["lock"], "a+")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
    except BlockingIOError:
        f.close()
        raise RuntimeError("Pipeline lock held")
    return f


def restore(c, state_path):
    state = read(state_path)
    if not state.get("restore_required"):
        return state
    jid = state_path.parent.name
    status = gpu("status")
    if status["phase"] == "qwen-ready" and status["owner"] is None and not status["uncertain"]:
        # Covers controller acknowledgement lost after completed restoration.
        state["restore_required"] = False
    elif status["owner"] != jid:
        raise RuntimeError("Restoration refused: another owner or missing ownership")
    else:
        gpu("restore", job=jid, generation=status["generation"])
        state["restore_required"] = False
    state["primary_health"] = health(c)
    state["PRIMARY_QWEN_RESTORED"] = "yes"
    write(state_path, state)
    return state


CONTAINER_STAGE = r"""
import base64,json,os,subprocess,sys,tempfile
from pathlib import Path
q=json.load(sys.stdin)
with tempfile.TemporaryDirectory(prefix='llama-mesh-') as td:
 p=Path(td);(p/'stage.py').write_text(q['script']);(p/'request.json').write_text(json.dumps(q['request']))
 (p/q['input_name']).write_bytes(base64.b64decode(q['input']))
 r=subprocess.run(['/usr/local/bin/blender','--background','--factory-startup','--threads','1','--python-exit-code','1','--python',str(p/'stage.py'),'--',td],capture_output=True,timeout=180,env=dict(os.environ,CUDA_VISIBLE_DEVICES='-1',OMP_NUM_THREADS='1'))
 files={n:base64.b64encode((p/n).read_bytes()).decode() for n in ['report.json','cleaned.blend','asset.glb'] if (p/n).is_file()}
 files['blender.log']=base64.b64encode(r.stdout+r.stderr).decode()
 print(json.dumps({'returncode':r.returncode,'files':files}))
"""


def blender(c, input_path, out, validate_only=False, glb_only=False, size=None):
    payload = {
        "script": (BASE / "blender/blender_stage.py").read_text(),
        "request": {"validate_only": validate_only, "glb_only": glb_only, "size": size},
        "input_name": "input.glb" if glb_only else "input.obj",
        "input": base64.b64encode(Path(input_path).read_bytes()).decode(),
    }
    result = json.loads(
        run(
            [
                "kubectl",
                "-n",
                c["tools_namespace"],
                "exec",
                "-i",
                "deploy/" + c["tools_deployment"],
                "--",
                "python3",
                "-c",
                CONTAINER_STAGE,
            ],
            timeout=240,
            input=json.dumps(payload).encode(),
        )
    )
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for n, b in result["files"].items():
        (out / n).write_bytes(base64.b64decode(b))
    if result["returncode"] or not (out / "report.json").is_file():
        raise RuntimeError("Blender failed; inspect " + str(out / "blender.log"))
    return read(out / "report.json")


def parse(raw):
    spec = importlib.util.spec_from_file_location("existing_mesh", cfg()["existing_parser"])
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    text, model = m.extract_response(raw)
    return m.parse_obj(text), text, model


def glb(path):
    data = Path(path).read_bytes()
    if len(data) < 20:
        raise ValueError("GLB too small")
    magic, version, length = struct.unpack_from("<III", data)
    if magic != 0x46546C67 or version != 2 or length != len(data):
        raise ValueError("Invalid GLB header")
    off = 12
    doc = None
    binary = b""
    while off < len(data):
        n, t = struct.unpack_from("<II", data, off)
        off += 8
        if off + n > len(data) or n % 4:
            raise ValueError("Invalid GLB chunk")
        chunk = data[off : off + n]
        off += n
        if t == 0x4E4F534A:
            doc = json.loads(chunk)
        elif t == 0x004E4942:
            binary = chunk
    if doc is None:
        raise ValueError("GLB missing JSON")

    def finite_json(value):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Non-finite JSON transform or metadata")
        if isinstance(value, dict):
            for item in value.values():
                finite_json(item)
        elif isinstance(value, list):
            for item in value:
                finite_json(item)

    finite_json(doc)
    for a in doc.get("accessors", []):
        if "sparse" in a:
            raise ValueError("Sparse accessor unsupported by this validator")
        if "bufferView" not in a:
            raise ValueError("Missing accessor bufferView")
        v = doc["bufferViews"][a["bufferView"]]
        n = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT2": 4, "MAT3": 9, "MAT4": 16}[a["type"]]
        fmt = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}[a["componentType"]]
        size = struct.calcsize("<" + fmt * n)
        stride = v.get("byteStride", size)
        start = v.get("byteOffset", 0) + a.get("byteOffset", 0)
        if (
            v.get("buffer", 0) != 0
            or stride < size
            or start + (max(0, a["count"] - 1)) * stride + size
            > min(len(binary), v.get("byteOffset", 0) + v["byteLength"])
        ):
            raise ValueError("Accessor bounds invalid")
        for i in range(a["count"]):
            if not all(math.isfinite(x) for x in struct.unpack_from("<" + fmt * n, binary, start + i * stride)):
                raise ValueError("Non-finite accessor")
    primitives = [p for m in doc.get("meshes", []) for p in m.get("primitives", [])]
    vertices = sum(doc["accessors"][p["attributes"]["POSITION"]]["count"] for p in primitives)
    if not doc.get("scenes") or not primitives or not vertices:
        raise ValueError("Empty GLB scene/mesh")
    for p in primitives:
        position = doc["accessors"][p["attributes"]["POSITION"]]
        if position["type"] != "VEC3":
            raise ValueError("Invalid position accessor")
        if "indices" in p:
            a = doc["accessors"][p["indices"]]
            v = doc["bufferViews"][a["bufferView"]]
            fmt = {5121: "B", 5123: "H", 5125: "I"}[a["componentType"]]
            size = struct.calcsize(fmt)
            start = v.get("byteOffset", 0) + a.get("byteOffset", 0)
            if any(
                struct.unpack_from("<" + fmt, binary, start + i * size)[0] >= position["count"]
                for i in range(a["count"])
            ):
                raise ValueError("Index outside vertex array")
    return dict(
        GLB_EXISTS="yes",
        GLB_SIZE=len(data),
        SCENE_COUNT=len(doc["scenes"]),
        NODE_COUNT=len(doc.get("nodes", [])),
        MESH_COUNT=len(doc["meshes"]),
        PRIMITIVE_COUNT=len(primitives),
        VERTEX_COUNT=vertices,
        FINITE_VALUES="PASS",
        MATERIAL_COUNT=len(doc.get("materials", [])),
        result="PASS",
    )


def safe_when_idle(c, phase):
    deadline = time.monotonic() + 90
    while True:
        try:
            safe(c)
            return
        except RuntimeError as error:
            if str(error) != "Primary inference busy; retry when idle" or time.monotonic() >= deadline:
                raise
            phase("waiting-primary-idle")
            time.sleep(2)


def generate(c, request, job):

    output = Path(request["output_dir"])
    output.mkdir(parents=True, exist_ok=False)
    for name in ["requests", "raw", "cleaned", "game-ready", "manifests", "logs"]:
        (output / name).mkdir()
    prompt = (job / "prompt.txt").read_text()
    (output / "requests/prompt.txt").write_text(prompt)
    state_path = job / "swap-state.json"
    write(state_path, {"restore_required": False, "primary_replicas": 1})
    meta = {
        "job_id": request["job_id"],
        "asset_name": request["name"],
        "created_at": request["created_at"],
        "started_at": now(),
        "prompt": prompt,
        "prompt_sha256": sha(job / "prompt.txt"),
        "model": c["model_alias"],
        "model_path": c["model_path"],
        "model_sha256": c["model_sha256"],
        "runtime": c["runtime"],
        "generation_settings": request["sampling"],
        "generation_parameters": request["sampling"],
        "godot_import_validation": {"result": "NOT_RUN", "reason": "Optional standalone validator"},
        "validation_result": "FAIL",
        "result": "FAIL",
    }
    failure = None

    def phase(name):
        write(
            job / "status.json",
            {
                "job_id": request["job_id"],
                "state": "running",
                "phase": name,
                "started_at": meta["started_at"],
                "updated_at": now(),
            },
        )
        print("PHASE=" + name, flush=True)

    try:
        phase("preflight")
        safe_when_idle(c, phase)
        write(job / "primary-before.json", obj(c, "deployment", c["primary"]))
        generation = gpu("begin", job=request["job_id"])["generation"]
        write(
            state_path, {"restore_required": True, "primary_replicas": 1, "generation": generation, "started_at": now()}
        )
        # Persist restoration intent before the mutating call (covers unknown outcomes).
        write(
            state_path, {"restore_required": True, "primary_replicas": 1, "generation": generation, "started_at": now()}
        )
        phase("controller-activating-mesh")
        gpu("activate", job=request["job_id"], generation=generation)
        meta["MODEL_SWAP_TO_MESH"] = "PASS"
        meta["LLAMA_MESH_READY"] = "PASS"
        models = http(url(c, c["mesh"]) + "/v1/models")
        if c["model_alias"] not in [m["id"] for m in models["data"]]:
            raise RuntimeError("Wrong loaded mesh model")
        payload = {
            "model": c["model_alias"],
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            **request["sampling"],
        }
        phase("generating")
        raw = http(url(c, c["mesh"]) + "/v1/chat/completions", payload, c["generation_timeout"], raw=True)
        (output / "raw/response.json").write_bytes(raw)
        mesh, text, model = parse(raw.decode())
        (output / "raw/response.txt").write_text(text)
        if model != c["model_alias"]:
            raise RuntimeError("Completion reported unexpected model identity")
        (output / "raw/mesh.obj").write_text(mesh["obj"])
        with (output / "raw/mesh.obj").open("rb") as asset:
            os.fsync(asset.fileno())
        sync_dir(output / "raw")
        gpu("asset-saved", job=request["job_id"], generation=generation)
        meta["GENERATION"] = "PASS"
        meta["RAW_MESH_CREATED"] = "PASS"
        meta["parser_warnings"] = mesh["warnings"]
    except BaseException as e:
        failure = e
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            phase("restoring-primary")
        except Exception:
            pass  # Status/log failures must never prevent restoration.
        try:
            restoration = restore(c, state_path)
            meta["PRIMARY_QWEN_RESTORED"] = restoration.get("PRIMARY_QWEN_RESTORED", "not-needed")
            meta["primary_health"] = restoration.get("primary_health")
        except BaseException as e:
            failure = e
            meta["PRIMARY_QWEN_RESTORED"] = "no"
    # CPU geometry work happens only once primary inference has been restored.
    if failure is None:
        try:
            phase("blender-cleanup-and-glb-validation")
            r = blender(c, output / "raw/mesh.obj", output / "cleaned")
            meta["raw_validation"] = r["raw"]
            meta["cleanup"] = r["cleaned"]
            meta["reimport"] = r["reimport"]
            (output / "cleaned/asset.glb").rename(output / "game-ready/asset.glb")
            meta["glb_validation"] = glb(output / "game-ready/asset.glb")
            meta["result"] = "PASS"
            meta["validation_result"] = r["raw"]["result"]
        except BaseException as e:
            failure = e
    meta["finished_at"] = now()
    meta["raw_output"] = str(output / "raw/response.json")
    meta["raw_path"] = str(output / "raw/mesh.obj")
    meta["cleaned_path"] = str(output / "cleaned/cleaned.blend")
    meta["game_ready_path"] = str(output / "game-ready/asset.glb")
    meta["cleaned_output"] = meta["cleaned_path"]
    meta["game_ready_output"] = meta["game_ready_path"]
    meta["cleaned_validation"] = meta.get("cleanup", {"result": "NOT_RUN"})
    meta["timestamps"] = {k: meta[k] for k in ["created_at", "started_at", "finished_at"]}
    meta["warnings"] = meta.get("parser_warnings", []) + [
        "Geometry prototype: no rig, authored UVs or textures; inspect silhouette before production use."
    ]
    meta["tool_versions"] = {"blender": "4.2.23", "runtime": c["runtime"], "python": sys.version.split()[0]}
    for key, p in [
        ("raw_sha256", output / "raw/mesh.obj"),
        ("cleaned_sha256", output / "cleaned/cleaned.blend"),
        ("glb_sha256", output / "game-ready/asset.glb"),
    ]:
        if p.exists():
            meta[key] = sha(p)
    if failure is not None:
        meta["error"] = str(failure)
    if (output / "cleaned/blender.log").exists():
        shutil.copyfile(output / "cleaned/blender.log", output / "logs/blender.log")
    write(output / "manifests/manifest.json", meta)
    write(job / "result/manifest.json", meta)
    if failure is not None:
        raise RuntimeError(str(failure))
    return meta


def find_job(c, jid):
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", jid):
        raise ValueError("Invalid job ID")
    for state in ["pending", "running", "complete", "failed"]:
        p = Path(c["job_root"]) / state / jid
        if p.exists():
            return p
    raise ValueError("Unknown job " + jid)


def start_job(jid):
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", jid):
        raise ValueError("Invalid job ID")
    run(
        [
            "systemd-run",
            "--quiet",
            "--unit=llama-mesh-" + jid,
            "--property=Type=exec",
            "--property=TimeoutStopSec=600",
            "--property=RuntimeMaxSec=3600",
            "--property=ExecStopPost=/usr/bin/python3 " + str(BASE / "llama_mesh_pipeline.py") + " recover " + jid,
            "/usr/bin/python3",
            str(BASE / "llama_mesh_pipeline.py"),
            "worker",
            jid,
        ]
    )


def recover_queue(c):
    # Boot reconciliation: persistent request/state files outlive transient units.
    deadline = time.monotonic() + c["startup_timeout"]
    while True:
        try:
            obj(c, "deployment", c["primary"])
            break
        except Exception:
            if time.monotonic() >= deadline:
                raise
            time.sleep(2)
    spool = Path(c["job_root"])
    recovered = []
    resumed = []
    controller_status = gpu("status")
    controller_owner = controller_status["owner"]
    if controller_owner and controller_status.get("owner_kind") == "router":
        gpu("recover", job=controller_owner, generation=controller_status["generation"])
        controller_owner = None

    def active(jid):
        r = subprocess.run(
            ["systemctl", "show", "llama-mesh-" + jid, "--property=ActiveState", "--value"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return r.stdout.strip() in ["active", "activating", "deactivating"]

    for kind in ["running", "failed"]:
        for job in sorted((spool / kind).iterdir()):
            if not job.is_dir() or active(job.name):
                continue
            state = job / "swap-state.json"
            if (
                job.name == controller_owner
                or kind == "running"
                or (state.exists() and read(state).get("restore_required"))
            ):
                recover(c, job.name)
                recovered.append(job.name)
    for job in sorted((spool / "pending").iterdir()):
        if job.is_dir() and not active(job.name):
            subprocess.run(["systemctl", "reset-failed", "llama-mesh-" + job.name], capture_output=True, timeout=10)
            start_job(job.name)
            resumed.append(job.name)
    result = {"result": "PASS", "recovered_jobs": recovered, "resumed_jobs": resumed, "checked_at": now()}
    write(BASE / "state/queue-recovery.json", result)
    print(json.dumps(result))


def submit(c, a):
    if (BASE / "state/gpu-controller-maintenance").exists():
        raise RuntimeError("GPU controller maintenance: submission paused")
    prompt = Path(a.prompt_file).resolve(strict=True)
    if not prompt.is_file() or not 0 < prompt.stat().st_size <= 8192 or not prompt.read_text().strip():
        raise ValueError("Prompt must be a nonempty UTF-8 file <=8192 bytes")
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,59}", a.name):
        raise ValueError("Invalid asset name")
    output = Path(a.output_dir)
    if not output.is_absolute():
        raise ValueError("Output must be absolute")
    output = output.resolve()
    root = Path(c["asset_root"]).resolve()
    if root not in output.parents or output.exists():
        raise ValueError("Output must be a new directory below " + str(root))
    jid = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    req = {
        "job_id": jid,
        "name": a.name,
        "output_dir": str(output),
        "created_at": now(),
        "prompt_sha256": sha(prompt),
        "sampling": dict(c["sampling"]),
        "model_path": c["model_path"],
        "model_sha256": c["model_sha256"],
        "model_name": c["model_alias"],
        "runtime_version": c["runtime"],
    }
    for arg in ["seed", "temperature", "max_tokens"]:
        if getattr(a, arg, None) is not None:
            req["sampling"][arg] = getattr(a, arg)
    if not 1 <= req["sampling"]["max_tokens"] <= 7000 or not 0 <= req["sampling"]["temperature"] <= 2:
        raise ValueError("Invalid sampling range")
    req["test_fail_after_down"] = bool(getattr(a, "test_fail_after_down", False))
    if getattr(a, "dry_run", False):
        with lock(c):
            safe(c)
        print(json.dumps({"result": "PASS", "dry_run": True, "request": req}))
        return
    spool = Path(c["job_root"])
    tmp = spool / ("staging-" + jid)
    tmp.mkdir(mode=0o750)
    (tmp / "result").mkdir()
    (tmp / "prompt.txt").write_bytes(prompt.read_bytes())
    write(tmp / "request.json", req)
    write(tmp / "status.json", {"job_id": jid, "state": "pending", "created_at": now()})
    with (tmp / "prompt.txt").open("rb") as f:
        os.fsync(f.fileno())
    (tmp / "stdout.log").touch()
    (tmp / "stderr.log").touch()
    sync_dir(tmp)
    tmp.rename(spool / "pending" / jid)
    sync_dir(spool / "pending")
    sync_dir(spool)
    try:
        start_job(jid)
    except Exception as e:
        p = spool / "pending" / jid
        write(p / "status.json", {"job_id": jid, "state": "failed", "error": str(e)})
        p.rename(spool / "failed" / jid)
        raise
    print("JOB_ID=" + jid)
    if a.command == "generate":
        while True:
            status = read(find_job(c, jid) / "status.json")
            if status["state"] in ["complete", "failed"]:
                print(json.dumps(status))
                if status["state"] == "failed":
                    raise RuntimeError(status["error"])
                return
            time.sleep(2)


def worker(c, jid):
    p = find_job(c, jid)
    if p.parent.name != "pending":
        raise RuntimeError("Job is not pending")
    # Serialize workers while allowing callers to submit durable complete requests.
    with lock(c, blocking=True):
        p = find_job(c, jid)
        target = Path(c["job_root"]) / "running" / jid
        p.rename(target)
        p = target
        sync_dir(p.parent)
        sync_dir(Path(c["job_root"]) / "pending")
        write(p / "status.json", {"job_id": jid, "state": "running", "started_at": now()})

        def interrupt(s, f):
            raise RuntimeError("Interrupted by signal " + str(s))

        signal.signal(signal.SIGTERM, interrupt)
        signal.signal(signal.SIGINT, interrupt)
        state = "complete"
        error = None
        with (p / "stdout.log").open("a", buffering=1) as stdout, (p / "stderr.log").open("a", buffering=1) as stderr:
            original = (sys.stdout, sys.stderr)
            sys.stdout, sys.stderr = stdout, stderr
            try:
                result = generate(c, read(p / "request.json"), p)
                print(json.dumps(result))
            except BaseException as e:
                state = "failed"
                error = str(e)
                print(error, file=sys.stderr)
            finally:
                sys.stdout, sys.stderr = original
        output = Path(read(p / "request.json")["output_dir"])
        if (output / "logs").is_dir():
            for name in ["stdout.log", "stderr.log"]:
                shutil.copyfile(p / name, output / "logs" / name)
            for f in output.rglob("*"):
                if f.is_file():
                    with f.open("rb") as handle:
                        os.fsync(handle.fileno())
            for directory in [d for d in output.rglob("*") if d.is_dir()] + [output]:
                sync_dir(directory)
        write(
            p / "status.json",
            {"job_id": jid, "state": state, "finished_at": now(), "error": error, "output_dir": str(output)},
        )
        p.rename(Path(c["job_root"]) / state / jid)
        sync_dir(Path(c["job_root"]) / state)
        sync_dir(Path(c["job_root"]) / "running")
        if error:
            raise RuntimeError(error)


def recover(c, jid):
    with lock(c, blocking=True):
        p = find_job(c, jid)
        status = gpu("status")
        if status["owner"] is not None:
            if status["owner"] != jid:
                raise RuntimeError("Recovery refused: another owner")
            gpu("recover", job=jid, generation=status["generation"])
        elif status["phase"] != "qwen-ready" or status["uncertain"]:
            raise RuntimeError("Unowned unsafe controller state requires operator investigation")
        if (p / "swap-state.json").exists():
            state = read(p / "swap-state.json")
            state["restore_required"] = False
            state["PRIMARY_QWEN_RESTORED"] = "yes"
            state["primary_health"] = health(c)
            write(p / "swap-state.json", state)
        if p.parent.name == "running":
            write(
                p / "status.json",
                {
                    "job_id": jid,
                    "state": "failed",
                    "error": "Worker terminated; controller recovery completed",
                    "finished_at": now(),
                },
            )
            p.rename(Path(c["job_root"]) / "failed" / jid)


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="command", required=True)
    for name in ["generate", "submit"]:
        p = sp.add_parser(name)
        p.add_argument("--prompt-file", required=True)
        p.add_argument("--output-dir", required=True)
        p.add_argument("--name", required=True)
        p.add_argument("--seed", type=int)
        p.add_argument("--temperature", type=float)
        p.add_argument("--max-tokens", type=int)
        p.add_argument("--dry-run", action="store_true")
        p.add_argument("--test-fail-after-down", action="store_true", help=argparse.SUPPRESS)
    for name in ["worker", "status", "recover"]:
        sp.add_parser(name).add_argument("job_id")
    sp.add_parser("health")
    sp.add_parser("recover-queue")
    p = sp.add_parser("frontend")
    p.add_argument("--project", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--prompt-file", required=True)
    p.add_argument("--seed", type=int)
    p.add_argument("--temperature", type=float)
    p.add_argument("--max-tokens", type=int)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--wait", action="store_true")
    p = sp.add_parser("validate")
    p.add_argument("--input", required=True)
    p.add_argument("--output-dir", required=True)
    p = sp.add_parser("clean")
    p.add_argument("--input", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--size", type=float)
    p = sp.add_parser("glb")
    p.add_argument("--input", required=True)
    p.add_argument("--output-dir", required=True)
    a = ap.parse_args()
    c = cfg()
    if a.command == "frontend":
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,59}", a.project):
            raise ValueError("Invalid project name")
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,59}", a.name):
            raise ValueError("Invalid asset name")
        a.output_dir = str(
            Path(c["asset_root"])
            / a.project
            / "runs"
            / (a.name + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
        )
        a.command = "generate" if a.wait else "submit"
    if a.command in ["validate", "clean", "glb"]:
        source = Path(a.input).resolve(strict=True)
        destination = Path(a.output_dir)
        if not source.is_file() or source.stat().st_size > 32 * 1024 * 1024:
            raise ValueError("Input must be a file <=32 MiB")
        if not destination.is_absolute() or Path(c["asset_root"]).resolve() not in destination.resolve().parents:
            raise ValueError("Output must be below asset_root")
        if destination.exists() and any(destination.iterdir()):
            raise ValueError("Refuse to overwrite existing validation/cleanup output")
        if a.command in ["validate", "clean"]:
            parse(source.read_text())
    if a.command in ["submit", "generate"]:
        submit(c, a)
    elif a.command == "worker":
        worker(c, a.job_id)
    elif a.command == "recover":
        recover(c, a.job_id)
    elif a.command == "status":
        p = find_job(c, a.job_id)
        print(json.dumps({"job_dir": str(p), **read(p / "status.json")}, indent=2))
    elif a.command == "health":
        print(json.dumps(health(c)))
    elif a.command == "recover-queue":
        recover_queue(c)
    elif a.command == "validate":
        print(json.dumps(blender(c, a.input, a.output_dir, validate_only=True)))
    elif a.command == "clean":
        if a.size is not None and (not math.isfinite(a.size) or a.size <= 0):
            raise ValueError("Size must be positive and finite")
        print(json.dumps(blender(c, a.input, a.output_dir, size=a.size)))
    elif a.command == "glb":
        print(json.dumps({"structure": glb(a.input), "blender": blender(c, a.input, a.output_dir, glb_only=True)}))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("ERROR: " + str(e), file=sys.stderr)
        sys.exit(1)
