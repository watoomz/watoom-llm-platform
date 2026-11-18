#!/usr/bin/env python3
"""WatooM Toolkit API: fixed jobs only. No arbitrary shell or package installs over HTTP."""
import job_admission
import publish_3d
import three_d
import creative
import asset_catalog
import kube_worker
import hashlib
import hmac
import json
import os
import pathlib
import re
import secrets
import shutil
import signal
import selectors
import stat
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

HOST = "0.0.0.0"
PORT = int(os.environ.get("WATOOM_PORT", "8879"))
TOKEN = os.environ.get("WATOOM_TOKEN", "")
WORKSPACE = pathlib.Path(os.environ.get("WATOOM_WORKSPACE", "/workspace"))
STATE = pathlib.Path(os.environ.get("WATOOM_STATE", "/state"))
CATALOG_PATH = pathlib.Path(os.environ.get("WATOOM_CATALOG", "/opt/watoom/catalog.json"))
ALLOWED_TIMEOUT = 180
MAX_OUTPUT = 12000
BUSY = threading.Lock()
ASSETS = pathlib.Path(os.environ.get("WATOOM_ASSETS", "/assets"))
ASSET_CATALOG = asset_catalog.Catalog(ASSETS, STATE/"asset-catalog/catalog.json")
ALLOWED = creative.TASKS | {"3d-generate", "3d-inspect", "3d-repair", "probe", "blender-render", "godot-import", "ansible-syntax"}


def safe_path(relative, *, kind="file"):
    if not isinstance(relative, str) or not relative or len(relative) > 400 or relative.startswith("/"):
        raise ValueError("path must be a workspace-relative string")
    try:
        p = (WORKSPACE / relative).resolve(strict=True)
        root = WORKSPACE.resolve(strict=True)
    except (OSError, RuntimeError) as e:
        raise ValueError("path does not exist or cannot be resolved") from e
    if not p.is_relative_to(root):
        raise ValueError("path escapes workspace")
    if (kind == "file" and not p.is_file()) or (kind == "dir" and not p.is_dir()):
        raise ValueError("wrong path type")
    return p


def executable(names):
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None

def inspection_path(relative):
    if isinstance(relative,str) and relative.startswith('pipelines/'):
        tail=pathlib.PurePosixPath(relative.removeprefix('pipelines/'))
        if tail.is_absolute() or any(p in ('','..','.') for p in tail.parts):raise ValueError('Unsafe canonical pipeline reference')
        root=pathlib.Path('/data/ai/projects/llm/pipelines').resolve(strict=True)
        path=root.joinpath(*tail.parts)
        if path.resolve(strict=True)!=path or not path.is_file():raise ValueError('Canonical pipeline input is missing or a symlink')
        return path
    prefix = os.environ.get('WATOOM_3D_PUBLIC_REFERENCE', '').rstrip('/') + '/'
    if prefix != '/' and isinstance(relative, str) and relative.startswith(prefix):
        tail = relative[len(prefix):]
        if not re.fullmatch(r'[a-f0-9]{16}/asset\.(glb|blend)', tail):
            raise ValueError('invalid published artifact reference')
        root = pathlib.Path(os.environ['WATOOM_3D_PUBLISH']).resolve(strict=True)
        path = root / tail
        if path.resolve(strict=True) != path or not path.is_file():
            raise ValueError('published artifact path changed')
        manifest = json.loads((path.parent / 'manifest.json').read_text())
        entry = next((item for item in manifest['outputs'] if item['path'] == path.name), None)
        data = path.read_bytes()
        if not entry or len(data) != entry['bytes'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise ValueError('published artifact hash mismatch')
        return path
    return safe_path(relative)


def make_command(payload, output_dir):
    task = payload.get("task")
    if task not in ALLOWED:
        raise ValueError("unknown task")
    if task in creative.TASKS:return creative.command(payload, output_dir, ASSET_CATALOG)
    if task.startswith("3d-"):
        input_path = None
        if task != "3d-generate":
            input_path = inspection_path(payload.get("path"))
            if input_path.suffix.lower() not in (".blend", ".glb"):
                raise ValueError("3D inspection supports packed .blend and .glb files only")
        return three_d.command(payload, output_dir, input_path)
    if task == "probe":
        return ["python3", "-B", "-c", "import json,shutil; print(json.dumps({n:shutil.which(n) for n in ['blender','godot','ansible','gcc','g++','clang','rustc','go','node','java','cmake']}))"]
    if task == "blender-render":
        binary = executable(["blender"])
        if not binary: raise ValueError("blender profile not installed")
        path = safe_path(payload.get("path"))
        if path.suffix.lower() != ".blend": raise ValueError("Blender project must end in .blend")
        frame = payload.get("frame", 1)
        if type(frame) is not int or not 1 <= frame <= 100000: raise ValueError("frame out of range")
        return [binary, "--factory-startup", "--disable-autoexec", "--background", str(path), "--threads", "1", "--python-expr", 'import bpy; bpy.context.scene.render.engine="CYCLES"; bpy.context.scene.cycles.device="CPU"', "--render-format", "PNG", "--render-output", str(output_dir / "render_"), "--render-frame", str(frame)]
    if task == "godot-import":
        binary = executable(["godot", "godot4"])
        if not binary: raise ValueError("godot profile not installed")
        path = safe_path(payload.get("path"),kind="dir")
        if not (path / "project.godot").is_file(): raise ValueError("not a Godot project")
        return [binary, "--headless", "--path", str(path), "--editor", "--quit"]
    if task == "ansible-syntax":
        binary = executable(["ansible-playbook"])
        if not binary: raise ValueError("ansible profile not installed")
        path = safe_path(payload.get("path"))
        if path.suffix.lower() not in (".yml", ".yaml"): raise ValueError("expected YAML playbook")
        # Restricted non-root container; no kubeconfig/ssh keys mounted.
        return [binary, "--syntax-check", str(path)]
    raise ValueError("unknown task")


def run_process(argv, timeout, *, root=None):
    start = time.monotonic()
    home = pathlib.Path(root) / "home" if root else pathlib.Path("/home/toolkit")
    temporary = pathlib.Path(root) / "tmp" if root else pathlib.Path("/tmp")
    if root:
        home.mkdir(mode=0o700)
        temporary.mkdir(mode=0o700)
    p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         start_new_session=True, close_fds=True, stdin=subprocess.DEVNULL,
                         cwd=root, env={
                             "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                             "HOME": str(home), "XDG_CACHE_HOME": str(home / ".cache"),
                             "TMPDIR": str(temporary), "LANG": "C.UTF-8", "ANSIBLE_NOCOLOR": "1",
                         })
    output = bytearray()
    deadline = start + timeout
    termination = None
    stream_open = True
    def stop_group(sig):
        try: os.killpg(p.pid, sig)
        except ProcessLookupError: pass
    try:
        os.set_blocking(p.stdout.fileno(), False)
        with selectors.DefaultSelector() as selector:
            selector.register(p.stdout, selectors.EVENT_READ)
            while stream_open or p.poll() is None:
                now = time.monotonic()
                if now >= deadline:
                    if termination is None:
                        termination = "TIMEOUT"
                        stop_group(signal.SIGTERM)
                        deadline = now + 3
                    elif termination == "TIMEOUT":
                        termination = "KILLED_AFTER_TIMEOUT"
                        stop_group(signal.SIGKILL)
                        deadline = now + 1
                    else: break
                events = selector.select(min(0.05, max(0, deadline - now))) if stream_open else []
                if not stream_open: time.sleep(0.01)
                for key, _ in events:
                    data = os.read(key.fd, 65536)
                    if not data:
                        selector.unregister(key.fileobj)
                        stream_open = False
                        continue
                    output.extend(data)
                    if len(output) > MAX_OUTPUT: del output[:-MAX_OUTPUT]
        if p.poll() is None:
            stop_group(signal.SIGKILL)
            p.wait(timeout=1)
        status = "TIMEOUT" if termination else "CANCELLED" if p.returncode in (-signal.SIGINT, -signal.SIGTERM) else "PASS" if p.returncode == 0 else "FAIL"
    except BaseException:
        stop_group(signal.SIGKILL)
        try: p.wait(timeout=1)
        except subprocess.TimeoutExpired: pass
        raise
    finally:
        stop_group(signal.SIGKILL)
        p.stdout.close()
    return {"status": status, "exit_code": p.returncode,
            "seconds": round(time.monotonic() - start, 2),
            "output": output.decode("utf-8", "replace")}


def read_artifact(root, relative, *, started=None, maximum=4194304):
    """Read an owned expected output via no-follow directory/file descriptors."""
    parts = pathlib.PurePosixPath(relative).parts
    if not parts or pathlib.PurePosixPath(relative).is_absolute() or any(p in (".", "..") for p in parts):
        raise ValueError("invalid required artifact path")
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        file = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
        try:
            before = os.fstat(file)
            if not stat.S_ISREG(before.st_mode) or not 1 <= before.st_size <= maximum:
                raise ValueError("required artifact is empty, oversized or not a regular file")
            if started is not None and not started <= before.st_mtime <= time.time() + 1:
                raise ValueError("required artifact is stale or future-dated")
            data = bytearray()
            while len(data) <= before.st_size:
                block = os.read(file, min(65536, before.st_size + 1 - len(data)))
                if not block: break
                data.extend(block)
            after = os.fstat(file)
            if len(data) != before.st_size or (before.st_dev, before.st_ino, before.st_mtime_ns, before.st_ctime_ns, before.st_size) != (after.st_dev, after.st_ino, after.st_mtime_ns, after.st_ctime_ns, after.st_size):
                raise ValueError("required artifact changed during verification")
            return bytes(data)
        finally:
            os.close(file)
    finally:
        os.close(descriptor)


def required_artifacts(payload, jobid):
    if payload["task"] in creative.TASKS:return [(STATE, name, True) for name in creative.required(payload,jobid)]
    if payload["task"].startswith("3d-"):
        return [(STATE, name, True) for name in three_d.required(payload, jobid)]
    if payload["task"] == "godot-import":
        project = safe_path(payload.get("path"), kind="dir")
        return [(WORKSPACE, str((project / name).relative_to(WORKSPACE)), name == ".godot/editor/filesystem_cache10") for name in (
            ".godot/editor/filesystem_cache10", ".godot/global_script_class_cache.cfg", ".godot/editor/project_metadata.cfg")]
    if payload["task"] == "blender-render":
        frame = payload.get("frame", 1)
        return [(STATE, "jobs/" + jobid + "/render_" + str(frame).zfill(4) + ".png", True)]
    return []


def artifact_evidence(payload, jobid, *, started=None):
    evidence = []
    for root, relative, fresh in required_artifacts(payload, jobid):
        data = read_artifact(root, relative, started=started if fresh else None, maximum=67108864 if payload["task"].startswith("3d-") else 33554432 if payload["task"] == "blender-render" else 4194304)
        if payload["task"].startswith("3d-"):
            three_d.validate_artifact(data, relative)
        if relative.endswith("filesystem_cache10"):
            lines = data.decode("utf-8", "strict").splitlines()
            if len(lines) < 2 or not re.fullmatch(r"[0-9a-f]{1,32}", lines[0]) or not lines[1].startswith("::res://::"):
                raise ValueError("partial or invalid Godot import index")
        if payload["task"] == "godot-import" and relative.endswith(".cfg"):
            text = data.decode("utf-8", "strict").strip()
            if relative.endswith("global_script_class_cache.cfg") and not (text.startswith("list=[") and text.endswith("]")):
                raise ValueError("invalid Godot class cache envelope")
            if relative.endswith("project_metadata.cfg") and not re.search(r"^\[editor_metadata\]$", text, re.MULTILINE):
                raise ValueError("invalid Godot editor metadata envelope")
        if relative.endswith(".png"):
            if not data.startswith(bytes.fromhex("89504e470d0a1a0a")) or not data.endswith(bytes.fromhex("0000000049454e44ae426082")):
                raise ValueError("partial PNG envelope")
            # The modeling profile already provides Pillow; no custom image decoder.
            from io import BytesIO
            from PIL import Image
            import warnings
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    with Image.open(BytesIO(data)) as image:
                        if image.format != "PNG" or getattr(image, "n_frames", 1) != 1:
                            raise ValueError("render is not a single PNG image")
                        if image.width < 1 or image.height < 1 or image.width * image.height > 16777216:
                            raise ValueError("render pixel budget exceeded")
                        if image.width * image.height * max(4, len(image.getbands())) > 67108864:
                            raise ValueError("decoded render memory budget exceeded")
                        image.verify()
                    with Image.open(BytesIO(data)) as image:
                        image.load()
            except (OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
                raise ValueError("corrupt, partial or oversized render") from error
        evidence.append({"root": "workspace" if root == WORKSPACE else "state", "path": relative, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    if payload["task"].startswith("asset-"):
        relative="jobs/"+jobid+"/worker/artifacts/manifest.json"
        creative.validate_catalog_manifest(evidence, read_artifact(STATE, relative, maximum=1048576))
    if payload["task"].startswith("3d-"):
        relative="jobs/"+jobid+"/worker/artifacts/manifest.json"
        three_d.validate_manifest(evidence, read_artifact(STATE, relative, maximum=1048576))
        if three_d.engine_validation(payload):
            manifest=json.loads(read_artifact(STATE, relative, maximum=1048576))
            engines=manifest.get('engine_validation',{})
            if engines.get('status')!='PASS' or engines.get('godot',{}).get('status')!='PASS' or engines.get('unreal',{}).get('status')!='PASS':raise ValueError('Real engine validation receipt missing')
    return evidence



def operation_contract(payload, argv, jobdir):
    task = payload["task"]
    if task in creative.TASKS:return {"id":"watoom-creative/v1","available": task.startswith("asset-") or bool(os.environ.get("WATOOM_WORKER_IMAGE"))}
    if task.startswith("3d-"):
        return {"id": "watoom-3d/v1", "available": bool(os.environ.get("WATOOM_WORKER_IMAGE"))}
    if task == "godot-import":
        # Output layouts are version-specific. Only the inspected/tested 4.7.2 contract is enabled.
        probe = jobdir / "capability"
        probe.mkdir(mode=0o700)
        result = run_process([argv[0], "--version"], 5, root=probe)
        version = result["output"].strip()
        return {"id": "godot-import/4.7.2-cache10/v1", "runtime": version,
                "available": result["status"] == "PASS" and re.fullmatch(r"4\.7\.2\.[A-Za-z0-9_.-]+", version) is not None}
    if task == "blender-render":
        import importlib.util
        return {"id": "blender-render/png/v1", "available": importlib.util.find_spec("PIL") is not None}
    return {"id": "process-exit/v1", "available": True}

def verify_receipt(payload, receipt):
    """Recheck required output fingerprints; process success alone is insufficient."""
    if receipt.get("status") != "PASS": return {"status": receipt.get("status", "BLOCKED")}
    try:
        if type(receipt.get("exit_code")) is not int or receipt["exit_code"] != 0: raise ValueError("process and receipt status disagree")
        if receipt.get("task") != payload["task"] or not re.fullmatch(r"[a-f0-9]{16}", receipt.get("id", "")): raise ValueError("receipt identity mismatch")
        contract = receipt.get("contract", {})
        if not isinstance(contract, dict): raise ValueError("invalid output contract")
        expected_contract = "watoom-creative/v1" if payload["task"] in creative.TASKS else "watoom-3d/v1" if payload["task"].startswith("3d-") else "godot-import/4.7.2-cache10/v1" if payload["task"] == "godot-import" else "blender-render/png/v1" if payload["task"] == "blender-render" else "process-exit/v1"
        if contract.get("id") != expected_contract or contract.get("available") is not True:
            raise ValueError("unsupported operation output contract")
        expected = artifact_evidence(payload, receipt["id"])
        if expected != receipt.get("artifacts", []) or contract.get("outputs") != [{"root":item["root"],"path":item["path"]} for item in expected]: raise ValueError("required artifact hash or identity mismatch")
        return {"status": "PASS"}
    except (OSError, ValueError, UnicodeError, TypeError, AttributeError):
        return {"status": "FAIL", "verification_error": "required artifact or receipt verification failed"}

def reconcile_admission():
    try:return job_admission.reconcile(STATE,lambda marker:marker["mode"]=="kube" and kube_worker.worker_stopped(marker["job_id"]))
    except (RuntimeError,OSError,ValueError):return False

def perform(payload):
    if not BUSY.acquire(blocking=False):
        return 409, {"error": "another toolkit job is running"}
    lease=None;dispatched=False;jobid=secrets.token_hex(8);isolated=bool(os.environ.get("WATOOM_WORKER_IMAGE")) and not payload.get("task","").startswith("asset-")
    try:
        reconcile_admission()
        lease=job_admission.start(STATE,jobid,"kube" if isolated else "local")
        operation=payload.get("operation_id")
        if isinstance(operation,str) and re.fullmatch("[a-f0-9]{64}",operation) and (STATE/"jobs"/(".cancel-"+operation)).exists():
            return 200,{"status":"CANCELLED","operation_id":operation,"task":payload.get("task"),"exit_code":None}
        STATE.mkdir(parents=True, exist_ok=True)
        jobdir = STATE / "jobs" / jobid
        argv = make_command(payload, jobdir)
        maximum=420 if three_d.engine_validation(payload) else 840 if payload.get("task")=="3d-creative" and "dungeon" in payload else ALLOWED_TIMEOUT
        requested = payload.get("timeout", maximum)
        if type(requested) is not int or not 1 <= requested <= maximum:
            raise ValueError("timeout must be an integer between1and"+str(maximum)+"seconds")
        jobdir.mkdir(parents=True, exist_ok=False)
        asset_catalog.atomic(jobdir / "request.json",{"id": jobid, "task": payload["task"], "status": "RUNNING", "created": time.time(), "operation_id":payload.get("operation_id"), "input_sha256":hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()})
        contract = operation_contract(payload, argv, jobdir)
        started = time.time()
        if (jobdir/"cancel.requested").exists() or (isinstance(operation,str) and re.fullmatch("[a-f0-9]{64}",operation) and (STATE/"jobs"/(".cancel-"+operation)).exists()):
            response={"id":jobid,"task":payload["task"],"operation_id":operation,"status":"CANCELLED","exit_code":None,"seconds":0,"output":"cancelled during preparation; worker not launched"}
            asset_catalog.atomic(jobdir/"result.json",response)
            return 200,response
        dispatched=isolated and contract["available"]
        response = (kube_worker.execute(argv, requested, jobdir, STATE, WORKSPACE, payload)
                    if os.environ.get("WATOOM_WORKER_IMAGE") and not payload["task"].startswith("asset-") else run_process(argv, requested, root=jobdir)) if contract["available"] else {
            "status": "BLOCKED", "exit_code": None, "seconds": 0,
            "output": "Verified runtime/output contract or image validation dependency unavailable"}
        contract["outputs"] = [{"root": "workspace" if root == WORKSPACE else "state", "path": relative}
                               for root, relative, _ in required_artifacts(payload, jobid)] if contract["available"] else []
        response["contract"] = contract
        if response["status"] == "PASS":
            try:
                if payload["task"] == "blender-render" and os.environ.get("WATOOM_WORKER_IMAGE"):
                    filename="render_"+str(payload.get("frame",1)).zfill(4)+".png"
                    data=read_artifact(STATE, "jobs/"+jobid+"/worker/"+filename, maximum=33554432)
                    descriptor=os.open(jobdir / filename, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o644)
                    with os.fdopen(descriptor,"wb") as file: file.write(data)

                if type(response.get("exit_code")) is not int or response["exit_code"] != 0:
                    raise ValueError("process and receipt status disagree")
                evidence = artifact_evidence(payload, jobid, started=started)
                if evidence: response["artifacts"] = evidence
            except (OSError, ValueError, UnicodeError):
                response["status"] = "FAIL"
                response["verification_error"] = "required fresh artifact verification failed"
        if response["status"]=="PASS" and payload["task"].startswith("asset-"):
            response["result"]=json.loads((jobdir/"worker/artifacts/result.json").read_text())
        response.update({"id": jobid, "task": payload["task"]})
        if payload["task"] in creative.TASKS:response["operation_id"]=payload.get("operation_id")
        response["verification"] = verify_receipt(payload, response)
        if response["status"] == "PASS" and response["verification"]["status"] != "PASS":
            response["status"] = "FAIL"
        if response["status"] == "PASS" and (payload["task"].startswith("3d-") or payload["task"].startswith("asset-")):
            try:
                response["published"] = publish_3d.publish(jobid, response["artifacts"], lambda relative: read_artifact(STATE, relative, maximum=67108864))
            except (OSError, ValueError):
                response["status"] = "FAIL"
                response["verification"] = {"status":"FAIL", "verification_error":"immutable artifact publication failed"}
        asset_catalog.atomic(jobdir / "result.json",response)
        return 200, response
    except job_admission.Held as e:
        return 503, {"error":str(e)}
    except job_admission.Busy as e:
        return 409, {"error":str(e)}
    except (ValueError, OSError, RuntimeError) as e:
        return 400, {"error": str(e)}
    finally:
        try:
            if lease is not None:
                stopped=True
                if dispatched:
                    try:stopped=kube_worker.worker_stopped(jobid,seconds=40)
                    except (RuntimeError,OSError,ValueError):stopped=False
                lease.close(clear=stopped)
        finally:BUSY.release()



def request_cancellation(body):
    """Persist cancellation even if an aborted native request has not created its job yet."""
    if set(body) not in ({"id"},{"operation_id"}):raise ValueError("Select one cancellation identity")
    jobs=STATE/"jobs";jobs.mkdir(parents=True,exist_ok=True)
    jobid=body.get("id")
    if "operation_id" in body:
        operation=body["operation_id"]
        if not isinstance(operation,str) or not re.fullmatch("[a-f0-9]{64}",operation):raise ValueError("Invalid operation identity")
        descriptor=os.open(jobs/(".cancel-"+operation),os.O_CREAT|os.O_WRONLY|os.O_NOFOLLOW,0o600)
        os.fsync(descriptor);os.close(descriptor)
        descriptor=os.open(jobs,os.O_RDONLY);os.fsync(descriptor);os.close(descriptor)
        matches=[];count=0
        for directory in jobs.iterdir():
            if not directory.is_dir() or not re.fullmatch("[a-f0-9]{16}",directory.name):continue
            count+=1
            if count>8192:raise ValueError("Cancellation lookup budget exceeded")
            request=directory/"request.json"
            if request.is_file() and json.loads(request.read_text()).get("operation_id")==operation:matches.append(directory.name)
        if len(matches)>1:raise ValueError("Ambiguous native operation identity")
        if not matches:return {"operation_id":operation,"status":"CANCELLATION_REQUESTED"}
        jobid=matches[0]
    if not isinstance(jobid,str) or not re.fullmatch("[a-f0-9]{16}",jobid):raise ValueError("Invalid cancellation job")
    directory=jobs/jobid
    request=json.loads((directory/"request.json").read_text())
    if not request.get("task","").startswith("3d-"):raise ValueError("Not an isolated3Djob")
    outcome=directory/"result.json"
    if outcome.exists():return {"id":jobid,"status":"ALREADY_FINISHED","outcome":json.loads(outcome.read_text()).get("status")}
    descriptor=os.open(directory/"cancel.requested",os.O_CREAT|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    os.fsync(descriptor);os.close(descriptor)
    if os.environ.get("WATOOM_WORKER_IMAGE"):kube_worker.cancel(jobid)
    return {"id":jobid,"status":"CANCELLATION_REQUESTED"}


def recent_jobs():
    """Bounded durable receipts. Missing outcomes are uncertain and never replayed."""
    root = STATE / "jobs"
    if root.is_symlink():
        return [{"status": "BLOCKED", "error": "unsafe persisted jobs root"}]
    if not root.exists():
        return []
    results = []
    try:
        inventory = []
        for directory in root.iterdir():
            if len(inventory) >= 10000:
                return [{"status": "BLOCKED", "error": "persisted job inventory budget exceeded"}]
            inventory.append((directory.lstat().st_mtime, directory))
        directories = [p for _,p in sorted(inventory, key=lambda item: item[0], reverse=True)[:20]]
    except OSError:
        return [{"status": "BLOCKED", "error": "persisted jobs inaccessible"}]
    for directory in directories:
        jobid = directory.name
        if not re.fullmatch(r"[a-f0-9]{16}", jobid) or directory.is_symlink() or not directory.is_dir():
            results.append({"id": jobid[:32], "status": "BLOCKED", "error": "unsafe persisted job identity"})
            continue
        result = directory / "result.json"
        if not result.exists():
            results.append({"id": jobid, "status": "UNCERTAIN", "error": "no persisted outcome; no automatic replay"})
            continue
        if result.is_symlink() or not result.is_file() or result.stat().st_size > 32768:
            results.append({"id": jobid, "status": "BLOCKED", "error": "unsafe or oversized persisted receipt"})
            continue
        try:
            data = json.loads(result.read_text())
            if not isinstance(data, dict) or data.get("id") != jobid or data.get("task") not in ALLOWED or data.get("status") not in ("PASS", "FAIL", "TIMEOUT", "CANCELLED", "BLOCKED"):
                raise ValueError("invalid receipt identity")
            results.append(data)
        except (ValueError, OSError):
            results.append({"id": jobid, "status": "BLOCKED", "error": "unreadable or invalid persisted receipt"})
    return results


HTML = """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>WatooM Toolkit</title><style>body{font:16px system-ui;background:#10141a;color:#e9eff8;max-width:880px;margin:35px auto;padding:14px}button,input,select{background:#202c3d;color:white;padding:10px;border:1px solid #58708a;border-radius:5px}button{cursor:pointer}pre{white-space:pre-wrap;background:#192331;padding:14px;border-radius:6px}table{width:100%;border-collapse:collapse}td,th{padding:8px;border-bottom:1px solid #344}small{color:#c0cada}</style></head><body><h2>WatooM Toolkit</h2><p><small>Tool profiles are immutable per image. Selection requests are staged for host approval and rebuild; no live package installs.</small></p><label>Access token <input id='token' type='password' autocomplete='off' placeholder='Token from host'></label><button onclick='load()'>Connect</button><h3>Installed profiles</h3><div id='installed'></div><h3>Available profiles</h3><div id='profiles'></div><button onclick='requestProfiles()'>Request selected profile set</button><h3>Read-only probe</h3><button onclick='probe()'>Run tool discovery</button><pre id='out'></pre><script>
let tok='';let cat=null;
async function api(path,method='GET',body=null){const r=await fetch(path,{method,headers:{Authorization:'Bearer '+tok,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});const j=await r.json();if(!r.ok)throw Error(j.error||r.status);return j}
async function load(){tok=document.getElementById('token').value;try{cat=await api('/api/catalog');document.getElementById('installed').textContent=cat.installed.join(', ');document.getElementById('profiles').innerHTML=Object.entries(cat.profiles).map(([k,v])=>`<label style='display:block;margin:5px'><input type='checkbox' value='${k}' ${cat.installed.includes(k)?'checked':''}> ${k}: ${v.description}</label>`).join('');document.getElementById('out').textContent='Connected'}catch(e){document.getElementById('out').textContent=e.message}}
async function requestProfiles(){try{const ps=[...document.querySelectorAll('#profiles input:checked')].map(x=>x.value);const j=await api('/api/profile-requests','POST',{profiles:ps});document.getElementById('out').textContent='Request created: '+j.id+' (host approval required)'}catch(e){document.getElementById('out').textContent=e.message}}
async function probe(){try{const j=await api('/api/jobs','POST',{task:'probe'});document.getElementById('out').textContent=JSON.stringify(j,null,2)}catch(e){document.getElementById('out').textContent=e.message}}
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Do not log Authorization or request bodies.
        print("http", self.client_address[0], self.command, urlsplit(self.path).path, flush=True)

    def respond(self, status, data):
        output = json.dumps(data, sort_keys=True).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(output)))
        self.end_headers()
        self.wfile.write(output)

    def authorized(self):
        provided = self.headers.get("Authorization", "")
        return bool(TOKEN) and hmac.compare_digest(provided, "Bearer " + TOKEN)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/healthz":
            self.respond(200, {"status": "ok"})
            return
        if path == "/":
            data=HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type","text/html; charset=utf-8")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; form-action 'none'; base-uri 'none'")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length",str(len(data)))
            self.end_headers();self.wfile.write(data);return
        if not self.authorized(): self.respond(401, {"error": "unauthorized"}); return
        if path == "/api/maintenance":
            reconcile_admission()
            self.respond(200,job_admission.status(STATE));return
        if path == "/api/catalog":
            catalog = json.loads(CATALOG_PATH.read_text())
            self.respond(200, {"profiles": catalog["profiles"], "installed": os.environ.get("WATOOM_PACKS", "").split(","), "generators": three_d.registry(), "capabilities": ["mesh-inspection", "mesh-repair", "asset-export", "asset.index", "asset.search", "asset.inspect", "asset.optimize", "world.compose", "character.prepare", "material.derive"], "creative_contract": {"schema":"watoom-creative/v1","asset_references":"indexed ast_ IDs; source library read-only","tasks":sorted(creative.TASKS),"operations":sorted(creative.OPERATIONS)}})
        elif path == "/api/jobs":
            self.respond(200, {"jobs": recent_jobs()})
        else: self.respond(404, {"error": "not found"})

    def do_POST(self):
        path=urlsplit(self.path).path
        if not self.authorized(): self.respond(401, {"error": "unauthorized"}); return
        try:
            n=int(self.headers.get("Content-Length", "0"))
            if not 1 <= n <= 4096: raise ValueError("invalid body size")
            body=json.loads(self.rfile.read(n))
            if not isinstance(body, dict): raise ValueError("expected object")
            if path=="/api/maintenance":
                reconcile_admission()
                try:self.respond(200,job_admission.change(STATE,body.get("action"),body.get("owner")))
                except (job_admission.Busy,job_admission.Held) as error:self.respond(409,{"error":str(error)})
                return
            if path=="/api/jobs/cancel":
                self.respond(200,request_cancellation(body));return
            if path=="/api/jobs":
                status,result=perform(body)
                self.respond(status,result);return
            if path=="/api/profile-requests":
                catalog=json.loads(CATALOG_PATH.read_text())
                profiles=body.get("profiles")
                if not isinstance(profiles,list) or not profiles or any(type(x)!=str or x not in catalog['profiles'] for x in profiles):
                    raise ValueError("invalid profiles")
                selected=sorted(set(profiles)|{'base'})
                if any(any(dep not in selected for dep in catalog['profiles'][p].get('requires',[])) for p in selected):
                    raise ValueError("missing required profiles")
                STATE.joinpath('requests').mkdir(parents=True,exist_ok=True)
                requestid=secrets.token_hex(8)
                STATE.joinpath('requests',requestid+'.json').write_text(json.dumps({"profiles":selected,"created":int(time.time())}))
                self.respond(202,{"id":requestid,"status":"AWAITING_HOST_APPROVAL"});return
            self.respond(404,{"error":"not found"})
        except (ValueError, OSError, RuntimeError, json.JSONDecodeError) as e: self.respond(400,{"error":str(e)})


def main():
    if len(TOKEN) < 32:
        raise SystemExit("missing or insufficient WATOOM_TOKEN; refusing to bind")
    if not WORKSPACE.is_dir():
        raise SystemExit("workspace mount unavailable")
    ThreadingHTTPServer((HOST,PORT), Handler).serve_forever()


if __name__ == '__main__':main()
