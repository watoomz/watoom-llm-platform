"""Narrow render-routing activation through the existing release coordinator."""

import argparse, hashlib, json, os, pathlib, shutil, subprocess
import release_guard
from maintenance_guard import Maintenance
from skills_release import NativeRelease


def promote():
    p = argparse.ArgumentParser()
    p.add_argument("--render-routing-only", action="store_true")
    p.add_argument("--iac-root", required=True, type=pathlib.Path)
    p.add_argument("--evidence", required=True, type=pathlib.Path)
    p.add_argument("--i-approve", action="store_true")
    p.add_argument("--update-owned-native", type=pathlib.Path)
    p.add_argument("--update-shell-guard", action="store_true")
    p.add_argument("--asset-capture-worker", action="store_true")
    a = p.parse_args()
    if not a.i_approve:
        raise RuntimeError("--i-approve required")
    root = a.iac_root.resolve()
    out = a.evidence.resolve()
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    m = Maintenance("watoom-code", "watoom-code", out, True, True)
    get = m.request
    names = ["sims"] + [
        "sims4-" + x
        for x in (
            "package-inspector",
            "asset-editor",
            "cas",
            "textures",
            "animation",
            "render",
            "gameplay",
            "package-builder",
            "release",
            "unreal",
        )
    ]
    release = NativeRelease(root, out, names, previous=a.update_owned_native, provenance=[])
    source = root / "ansible/roles/watoom-code/files/skills/asset-image-clip-capture"
    target = release.target / "asset-image-clip-capture"
    if target.is_symlink() or not target.is_dir():
        raise RuntimeError("Managed capture skill missing or unsafe")
    old_capture = NativeRelease.digest(target)
    expected_capture = NativeRelease.digest(source)
    rule = (source / "references/default-recipe.md").read_text().strip()
    if not rule.startswith("## Default generic asset render and capture procedure"):
        raise RuntimeError("Default rule missing")
    agents = [
        pathlib.Path("/data/ai/watoom-code/config/agents") / (x + ".md") for x in ("watoom-workflow", "watoom-builder")
    ]
    originals = {str(f): f.read_bytes() for f in agents}
    for f in agents:
        if f.is_symlink():
            raise RuntimeError("Agent symlink rejected")
        (out / (f.name + ".before")).write_bytes(originals[str(f)])
    baseline = m.kub("get", "deploy", "watoom-code")
    before = get("/api/skill?directory=/workspace")["data"]
    (out / "application-before.json").write_text(json.dumps(baseline, indent=2))
    (out / "skills-before.json").write_text(json.dumps(before, indent=2))

    def clearance():
        release_guard.active_clear(get("/api/session/active"))
        release_guard.durable_clearance(pathlib.Path("/data/ai/watoom-code/application.sqlite"))
        if any(j.get("status", {}).get("active") for j in m.kub("get", "jobs")["items"]):
            raise RuntimeError("Worker active")

    def save(owner):
        path = out / "guard-owner.private"
        path.write_text(owner)
        path.chmod(0o600)
        with path.open("rb") as f:
            os.fsync(f.fileno())

    owner = release_guard.acquire(get, lambda path, body: m.request(path, body), save, clearance)
    config = pathlib.Path("/data/ai/watoom-code/config/opencode.json")
    config_before = config.read_bytes()
    config_after = None
    if a.update_shell_guard:
        (out / "opencode-before.private.json").write_bytes(config_before)
    worker_config = pathlib.Path("/etc/watoom-asset-capture.json")
    worker_before = worker_config.read_bytes() if worker_config.exists() else None
    if worker_before is not None:
        (out / "asset-worker-before.json").write_bytes(worker_before)
    healthy = True
    moved = False
    agent_after = {}
    try:
        release_guard.snapshot_database(
            pathlib.Path("/data/ai/watoom-code/application.sqlite"), out / "application-before.private.sqlite"
        )
        if NativeRelease.digest(target) != old_capture or any(f.read_bytes() != originals[str(f)] for f in agents):
            raise RuntimeError("Concurrent managed instruction change")
        healthy = False
        target.rename(out / "capture-before")
        moved = True
        release.apply()
        command = [
            "ansible-playbook",
            "-i",
            "localhost,",
            "ansible/playbooks/watoom-code-render-routing.yml",
            "-e",
            "watoom_render_routing_guard_held=true",
        ]
        if a.update_shell_guard:
            command += ["-e", "watoom_render_routing_shell_guard=true"]
        if a.asset_capture_worker:
            command += ["-e", "watoom_render_routing_asset_worker=true"]
        env = dict(
            os.environ, ANSIBLE_CONFIG=str(root / "ansible/ansible.cfg"), ANSIBLE_ROLES_PATH=str(root / "ansible/roles")
        )
        r = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True, timeout=90)
        (out / "ansible-apply.log").write_text(r.stdout + r.stderr)
        if a.update_shell_guard:
            config_after = config.read_bytes()
        for f in agents:
            agent_after[str(f)] = f.read_bytes()
        if r.returncode:
            raise RuntimeError("Scoped Ansible activation failed; inspect log")
        if NativeRelease.digest(target) != expected_capture:
            raise RuntimeError("Capture tree differs from reviewed source")
        if any(rule not in f.read_text() for f in agents):
            raise RuntimeError("Default routing block missing")
        guard_verification = "NOT_CHANGED"
        if a.update_shell_guard:
            digest = hashlib.sha256(
                (root / "ansible/roles/watoom-code/files/coordinator-guard/index.js").read_bytes()
            ).hexdigest()
            installed = config.parent / "watoom-tools" / ("coordinator-guard-" + digest) / "index.js"
            if not installed.is_file() or hashlib.sha256(installed.read_bytes()).hexdigest() != digest:
                raise RuntimeError("Installed shell guard identity mismatch")
            expected = "/config/watoom-tools/coordinator-guard-" + digest
            entries = json.loads(config.read_text()).get("plugins", [])
            if not any((x if isinstance(x, str) else x.get("package")) == expected for x in entries):
                raise RuntimeError("Shell guard not selected")
            guard_verification = "PASS"
        verification = release.verify(get, [x["id"] for x in before])
        live = get("/api/skill?directory=/data/ai/projects/images")["data"]
        live_names = {x["name"] for x in live}
        if not set(names + ["asset-image-clip-capture"]).issubset(live_names):
            raise RuntimeError("Project-scoped skills unavailable")
        if m.kub("get", "deploy", "watoom-code")["spec"] != baseline["spec"]:
            raise RuntimeError("Application deployment changed")
        # An idempotent second apply is a meaningful durability gate.
        r = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True, timeout=90)
        (out / "ansible-repeat.log").write_text(r.stdout + r.stderr)
        if r.returncode or "changed=0" not in r.stdout:
            raise RuntimeError("Repeat apply was not unchanged")
        result = dict(
            status="PASS",
            default="generic source inspection, preparation, render and capture; recipes optional",
            native_skills=verification,
            project_discovery="PASS",
            repeat_apply="UNCHANGED",
            application_restarted=False,
            engines_started=False,
            native_execution_idle=True,
            shell_guard=guard_verification,
        )
        (out / "result.json").write_text(json.dumps(result, indent=2))
        healthy = True
        print(json.dumps(result))
    except BaseException:
        if a.asset_capture_worker:
            if worker_before is None:
                worker_config.unlink(missing_ok=True)
            else:
                worker_config.write_bytes(worker_before)
        if a.update_shell_guard and config_after is not None:
            if config.read_bytes() != config_after:
                raise RuntimeError("Concurrent application config change; admission retained")
            import tempfile

            metadata = config.stat()
            fd, name = tempfile.mkstemp(prefix=".routing-config-rollback-", dir=config.parent)
            with os.fdopen(fd, "wb") as file:
                os.fchmod(file.fileno(), metadata.st_mode & 0o777)
                os.fchown(file.fileno(), metadata.st_uid, metadata.st_gid)
                file.write(config_before)
                file.flush()
                os.fsync(file.fileno())
            os.replace(name, config)
        release.rollback()
        if moved:
            if target.exists():
                if NativeRelease.digest(target) != expected_capture:
                    raise RuntimeError("Unknown capture bytes; admission retained for recovery")
                target.rename(out / "retained-capture-failed")
            (out / "capture-before").rename(target)
        for f in agents:
            if f.read_bytes() not in (originals[str(f)], agent_after.get(str(f), originals[str(f)])):
                raise RuntimeError("Concurrent agent change; admission retained")
            f.write_bytes(originals[str(f)])
        healthy = True
        raise
    finally:
        if healthy:
            release_guard.release(get, lambda path, body: m.request(path, body), owner)
