"""Scoped approved release: native fence, SQLite backup, IaC apply and runtime identity."""

import argparse, hashlib, json, os, pathlib, shutil, subprocess, time
import release_guard
from maintenance_guard import Maintenance, run


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--iac-root", required=True, type=pathlib.Path)
    p.add_argument("--evidence", required=True, type=pathlib.Path)
    p.add_argument("--i-approve", action="store_true")
    p.add_argument("--manifest", type=pathlib.Path)
    a = p.parse_args()
    if not a.i_approve:
        raise RuntimeError("Explicit rollout approval required")
    root = a.iac_root.resolve()
    out = a.evidence.resolve()
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    manifest = json.loads((a.manifest or root / "tools/watoom-code/source/memory-catalogue-20261026.json").read_text())
    expected = manifest["image"]
    m = Maintenance("watoom-code", "watoom-code", out, True, True)
    state_root = pathlib.Path("/data/ai/helper-scripts/state/gpu-controller")
    baseline = m.kub("get", "deploy", "watoom-code")
    (out / "deployment-before.private.json").write_text(json.dumps(baseline))
    baseline_controller = json.loads((state_root / "state.json").read_text())
    config = pathlib.Path("/data/ai/watoom-code/config/opencode.json")
    config_before = config.read_bytes()
    (out / "opencode-before.private.json").write_bytes(config_before)
    expected_config = json.loads(config_before)
    if manifest.get("updatesCapabilities"):
        for name, value in json.loads(
            (root / "ansible/roles/watoom-code/files/verified-model-capabilities.json").read_text()
        ).items():
            if name in expected_config["providers"]["watoom"]["models"]:
                expected_config["providers"]["watoom"]["models"][name]["capabilities"] = value
    generation = baseline_controller["generation"]
    phase = baseline_controller["phase"]
    if phase not in ("qwen-ready", "model-ready"):
        raise RuntimeError("Controller is not at a supported ready boundary")

    def clearance():
        release_guard.durable_clearance(pathlib.Path("/data/ai/watoom-code/application.sqlite"))
        if any(j.get("status", {}).get("active") for j in m.kub("get", "jobs")["items"]):
            raise RuntimeError("Worker jobs active")
        state = json.loads((state_root / "state.json").read_text())
        leases = json.loads((state_root / "inference-leases.json").read_text())
        if (
            state["generation"] != generation
            or state["owner"] is not None
            or state["uncertain"]
            or state["phase"] != phase
            or leases["leases"]
        ):
            raise RuntimeError("Controller boundary not idle")

    def save(owner):
        f = out / "guard-owner.private"
        f.write_text(owner)
        f.chmod(0o600)
        with f.open("rb") as stream:
            os.fsync(stream.fileno())

    env = dict(
        os.environ, ANSIBLE_CONFIG=str(root / "ansible/ansible.cfg"), ANSIBLE_ROLES_PATH=str(root / "ansible/roles")
    )

    def ansible(playbook, flag):
        cmd = [
            "ansible-playbook",
            "-i",
            "ansible/inventories/homelab/hosts.yml",
            "ansible/playbooks/" + playbook,
            "-e",
            flag + "=true",
        ]
        r = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True, timeout=300)
        (out / (playbook + ".log")).write_text(r.stdout + r.stderr)
        if r.returncode:
            raise RuntimeError("Scoped playbook failed: " + playbook)

    owner = release_guard.acquire(m.request, lambda path, body: m.request(path, body), save, clearance)
    changed = False
    healthy = True
    names = ["watoom-prompt-writing", "watoom-prompt-image", "watoom-prompt-development"]
    skills = pathlib.Path("/data/ai/watoom-code/config/skills")
    try:
        release_guard.snapshot_database(
            pathlib.Path("/data/ai/watoom-code/application.sqlite"), out / "application-before.private.sqlite"
        )
        for name in names:
            shutil.copy2(skills / name / "SKILL.md", out / (name + ".before.md"))
        for f in [
            "/data/ai/helper-scripts/config/gpu-controller.json",
            "/data/ai/helper-scripts/gpu-controller/g3h_service.py",
            "/etc/systemd/system/watoom-gpu-controller.service",
        ]:
            shutil.copy2(f, out / (pathlib.Path(f).name + ".before"))
        clearance()
        if not manifest.get("applicationOnly"):
            ansible("watoom-code-memory-observability.yml", "watoom_memory_observability_release_verified")
        clearance()
        healthy = False
        changed = True
        ansible("watoom-code-memory-catalogue.yml", "watoom_memory_catalogue_guard_held")
        current = m.kub("get", "deploy", "watoom-code")
        actual = next(c["image"] for c in current["spec"]["template"]["spec"]["containers"] if c["name"] == "app")
        release_guard.runtime(m.request, expected, actual)
        info = m.request("/api/info")
        status = m.request("/api/memory/status?location%5Bdirectory%5D=/workspace")["data"]
        catalogue = m.request("/api/skill/index?location%5Bdirectory%5D=/workspace")["data"]
        # Readiness is not discovery convergence; retain each incomplete observation.
        samples = []
        deadline = time.monotonic() + 30
        while catalogue["catalogueSize"] < 131 or sum(x["kind"] == "pipeline" for x in catalogue["entries"]) < 28:
            samples.append(
                {
                    "size": catalogue["catalogueSize"],
                    "pipelines": sum(x["kind"] == "pipeline" for x in catalogue["entries"]),
                }
            )
            (out / "catalogue-readiness-samples.json").write_text(json.dumps(samples))
            if time.monotonic() >= deadline:
                break
            time.sleep(1)
            catalogue = m.request("/api/skill/index?location%5Bdirectory%5D=/workspace")["data"]
        if (
            not status["memory"]["enabled"]
            or not status["memory"]["required"]
            or not status["ownership"]["available"]
            or status["ownership"]["stale"]
        ):
            raise RuntimeError("Memory/ownership runtime gate failed")
        if status["ownership"]["generation"] != generation:
            raise RuntimeError("Ownership changed during release")
        (out / "catalogue-runtime.json").write_text(json.dumps(catalogue, indent=2))
        if catalogue["catalogueSize"] < 131 or sum(x["kind"] == "pipeline" for x in catalogue["entries"]) < 28:
            raise RuntimeError(
                "Installed catalogue incomplete: "
                + str(catalogue["catalogueSize"])
                + " entries, "
                + str(sum(x["kind"] == "pipeline" for x in catalogue["entries"]))
                + " pipelines"
            )
        if manifest.get("stageWorkerSkill"):
            stage = next((x for x in catalogue["entries"] if x["id"] == "workstation-render-stage"), None)
            if not stage or stage["autoinvoke"] is not False:
                raise RuntimeError("Manual-only staging catalogue gate failed")
        for name in names:
            if (skills / name / "SKILL.md").read_bytes() != (
                root / "ansible/roles/watoom-code/files/skills" / name / "SKILL.md"
            ).read_bytes():
                raise RuntimeError("Pipeline source mismatch")
        pod = m.pod()
        imageid = next(c["imageID"] for c in pod["status"]["containerStatuses"] if c["name"] == "app")
        if expected.split("@")[1] not in imageid:
            raise RuntimeError("Running image digest mismatch")
        result = {
            "status": "PASS",
            "sourceCommit": manifest["sourceCommit"],
            "image": expected,
            "imageID": imageid,
            "version": info["version"],
            "memory": status,
            "catalogueSize": catalogue["catalogueSize"],
            "pipelines": sum(x["kind"] == "pipeline" for x in catalogue["entries"]),
            "controllerGenerationUnchanged": generation,
            "databaseBackup": "application-before.private.sqlite",
        }
        (out / "result.json").write_text(json.dumps(result, indent=2))
        healthy = True
        print(json.dumps(result))
    except BaseException:
        if changed:
            if manifest.get("updatesCapabilities"):
                if json.loads(config.read_bytes()) not in (json.loads(config_before), expected_config):
                    raise RuntimeError("Concurrent model configuration change; native fence retained")
                config.write_bytes(config_before)
            run(
                [
                    "kubectl",
                    "-n",
                    m.ns,
                    "patch",
                    "deployment",
                    m.name,
                    "--type=merge",
                    "-p",
                    json.dumps({"spec": {"template": baseline["spec"]["template"]}}),
                ]
            )
            run(["kubectl", "-n", m.ns, "rollout", "status", "deployment/" + m.name, "--timeout=240s"], timeout=260)
            for name in names:
                shutil.copy2(out / (name + ".before.md"), skills / name / "SKILL.md")
            m.request("/api/info")
            healthy = True
        raise
    finally:
        if healthy:
            release_guard.release(m.request, lambda path, body: m.request(path, body), owner)


if __name__ == "__main__":
    main()
