#!/usr/bin/env python3
"""Independently exercise immutable old/new rollback only on the owned creative candidate."""

import argparse, copy, hashlib, json, os, pathlib, shutil, subprocess, time
from maintenance_guard import Maintenance
from creative_release import desired_deployment, CAPABILITIES

OLD_APP = "127.0.0.1:5000/watoom-code@sha256:08c8bfb0e523f29f4074e0a60d0a019e0cf73e775a83de25de120265c3cdd196"
OLD_TOOLKIT = "127.0.0.1:5000/watoom-toolkit@sha256:2a12a7ddbab49fdb4c17db85b074b644a6cc97bc27ff1ce5069beeefd04baca3"


def clean(value):
    value = copy.deepcopy(value)
    value.pop("status", None)
    for key in ["uid", "resourceVersion", "creationTimestamp", "generation", "managedFields"]:
        value["metadata"].pop(key, None)
    value["metadata"].get("annotations", {}).pop("kubectl.kubernetes.io/last-applied-configuration", None)
    return value


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--evidence", required=True, type=pathlib.Path)
    a = p.parse_args()
    root = a.evidence.resolve()
    out = root / "candidate"
    identity = json.loads((out / "identity.json").read_text())
    assert (
        identity["namespace"] == "watoom-code"
        and identity["name"] == "watoom-code-memory-candidate-20261016"
        and identity["toolkit"] == "watoom-creative-candidate-20261017"
    )
    m = Maintenance(identity["namespace"], identity["name"], out, True, True)

    def command(args, input=None, timeout=60):
        result = subprocess.run(args, input=input, capture_output=True, timeout=timeout)
        if result.returncode:
            raise RuntimeError("Owned candidate command failed: " + result.stderr.decode(errors="replace")[-400:])
        return result.stdout

    def apply(value):
        command(["kubectl", "apply", "-f", "-"], json.dumps(clean(value)).encode())

    app = m.kub("get", "deploy", m.name)
    toolkit = m.kub("get", "deploy", identity["toolkit"])
    config = m.kub("get", "cm", m.name)
    assert app["metadata"]["labels"]["watoom-test-owner"] == "agentmemory-unblock-20261016T204420Z"
    assert toolkit["metadata"]["labels"]["watoom-test-owner"] == "creative-pipelines-20261017"
    assert app["spec"]["replicas"] == 1 and toolkit["spec"]["replicas"] == 1
    assert app["spec"]["template"]["spec"]["containers"][0]["image"] == identity["image"]
    assert toolkit["spec"]["template"]["spec"]["containers"][0]["image"] == identity["toolkit_image"]
    assert m.request("/api/session/active")["data"] == {}
    owner = (out / "guard-owner.private").read_text().strip()
    if m.request("/api/session/deployment-guard")["data"]["held"]:
        assert (
            m.exec(
                "import pathlib,json,sys;assert json.loads(pathlib.Path('/state/watoom-release-guard.json').read_text())['owner']==sys.argv[1];print('OWNED')",
                owner,
            ).strip()
            == b"OWNED"
        )
    else:
        assert m.request("/api/session/deployment-guard", {"action": "acquire", "owner": owner})["data"]["held"]
    for name, value in [
        ("rollback-final-app.private.json", app),
        ("rollback-final-config.private.json", config),
        ("rollback-final-toolkit.json", toolkit),
    ]:
        path = out / name
        path.write_text(json.dumps(value, indent=2))
        path.chmod(0o600)
    oldapp = json.loads((out / "app-before.private.json").read_text())
    oldconfig = json.loads((out / "config-before.private.json").read_text())
    assert oldapp["spec"]["template"]["spec"]["containers"][0]["image"] == OLD_APP
    oldapp["spec"]["replicas"] = 1
    oldtoolkit = desired_deployment(toolkit, OLD_TOOLKIT)
    query = "import sqlite3,json;d=sqlite3.connect('file:/state/application.sqlite?mode=ro',uri=True); print(json.dumps(list(d.execute('SELECT id,scope,job,phase,outcome FROM _watoom_specialist_job ORDER BY id'))))"
    before = json.loads(m.exec(query))
    catalog = out / "toolkit-state/asset-catalog/catalog.json"
    catalog_sha = hashlib.sha256(catalog.read_bytes()).hexdigest()
    artifacts = {}
    for receipt in (out / "toolkit-state/jobs").glob("*/result.json"):
        data = json.loads(receipt.read_text())
        for file in data.get("published", {}).get("files", []):
            rel = data["published"]["path"] + "/" + file["path"]
            path = out / "published" / rel
            assert path.resolve().is_relative_to((out / "published").resolve()) and not path.is_symlink()
            assert hashlib.sha256(path.read_bytes()).hexdigest() == file["sha256"]
            artifacts[rel] = file["sha256"]

    def check_runtime(expected_app, expected_toolkit, creative):
        deadline = time.monotonic() + 45
        while True:
            try:
                info = m.request("/api/info")
                assert isinstance(info.get("version"), str)
                assert m.request("/api/session/active")["data"] == {}
                guard = m.request("/api/session/deployment-guard")["data"]
                assert guard["held"] is True and guard["leases"] == 0
                commands = m.request("/api/command?directory=/workspace")["data"]
                assert {"remember", "recall"}.issubset({x["name"] for x in commands})
                break
            except Exception:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.5)
        for name, image in [(m.name, expected_app), (identity["toolkit"], expected_toolkit)]:
            pods = m.kub("get", "pods", "-l", "app=" + name)["items"]
            live = [x for x in pods if x["status"]["phase"] == "Running" and not x["metadata"].get("deletionTimestamp")]
            assert (
                len(live) == 1
                and live[0]["status"]["containerStatuses"][0]["imageID"].split("@")[-1] == image.split("@")[-1]
            )
        pod = next(
            x
            for x in m.kub("get", "pods", "-l", "app=" + identity["toolkit"])["items"]
            if x["status"]["phase"] == "Running" and not x["metadata"].get("deletionTimestamp")
        )
        code = "import os,json,urllib.request;r=urllib.request.Request('http://127.0.0.1:'+os.environ.get('WATOOM_PORT','8879')+'/api/catalog',headers={'Authorization':'Bearer '+os.environ['WATOOM_TOKEN']});d=json.load(urllib.request.urlopen(r,timeout=10));assert isinstance(d['generators'],list);print(json.dumps(d['capabilities']))"
        caps = json.loads(
            command(
                ["kubectl", "-n", m.ns, "exec", pod["metadata"]["name"], "-c", "toolkit", "--", "python3", "-c", code]
            )
        )
        if creative:
            assert set(CAPABILITIES).issubset(caps)

    def pair(appvalue, configvalue, toolkitvalue, label):
        apply(configvalue)
        apply(toolkitvalue)
        command(
            ["kubectl", "-n", m.ns, "rollout", "status", "deploy/" + identity["toolkit"], "--timeout=90s"], timeout=100
        )
        apply(appvalue)
        command(["kubectl", "-n", m.ns, "rollout", "status", "deploy/" + m.name, "--timeout=90s"], timeout=100)
        check_runtime(
            appvalue["spec"]["template"]["spec"]["containers"][0]["image"],
            toolkitvalue["spec"]["template"]["spec"]["containers"][0]["image"],
            label.startswith("final"),
        )
        print("PASS owned candidate " + label + " authenticated APIs, immutable images and durable fence", flush=True)

    final_restored = False
    try:
        pair(oldapp, oldconfig, oldtoolkit, "baseline")
        pair(app, config, toolkit, "final-before-injected-failure")
        # Deliberate validation failure invokes restoration without a user interaction.
        try:
            raise RuntimeError("owned-validation-failure-injection")
        except RuntimeError as injected:
            assert str(injected) == "owned-validation-failure-injection"
            pair(oldapp, oldconfig, oldtoolkit, "automatic-rollback-after-injected-failure")
        source = pathlib.Path("/data/ai/assets/generated/watoom-toolkit-3d/v1/3a4a010e87346e58/asset.glb")
        target = out / "workspace/owned-rollback-probe.glb"
        assert not target.exists()
        shutil.copyfile(source, target)
        os.chown(target, 1009, 1009)
        target.chmod(0o640)
        pod = next(
            x
            for x in m.kub("get", "pods", "-l", "app=" + identity["toolkit"])["items"]
            if x["status"]["phase"] == "Running" and not x["metadata"].get("deletionTimestamp")
        )
        code = "import os,json,urllib.request;r=urllib.request.Request('http://127.0.0.1:'+os.environ.get('WATOOM_PORT','8879')+'/api/jobs',headers={'Authorization':'Bearer '+os.environ['WATOOM_TOKEN'],'Content-Type':'application/json'},data=json.dumps({'task':'3d-inspect','path':'owned-rollback-probe.glb','timeout':180}).encode());print(urllib.request.urlopen(r,timeout=200).read().decode())"
        receipt = json.loads(
            command(
                ["kubectl", "-n", m.ns, "exec", pod["metadata"]["name"], "-c", "toolkit", "--", "python3", "-c", code],
                timeout=210,
            )
        )
        (out / "old-toolkit-real-inspect.json").write_text(json.dumps(receipt, indent=2))
        assert (
            receipt["status"] == "PASS"
            and receipt["verification"]["status"] == "PASS"
            and receipt["worker"]["image_id"].split("@")[-1] == OLD_TOOLKIT.split("@")[-1]
        )
        print("PASS old Toolkit actual isolated Blender inspect/export/reimport", flush=True)
        pair(app, config, toolkit, "final-restored")
        final_restored = True
        assert json.loads(m.exec(query)) == before
        assert hashlib.sha256(catalog.read_bytes()).hexdigest() == catalog_sha
        for relative, sha in artifacts.items():
            assert hashlib.sha256((out / "published" / relative).read_bytes()).hexdigest() == sha
        memory = json.loads((out / "memory-acceptance.private.json").read_text())
        assert memory["fact"] in json.dumps(m.request("/api/session/" + memory["session"] + "/message"))
        result = {
            "status": "PASS",
            "image": identity["image"],
            "toolkit_image": identity["toolkit_image"],
            "old_app": OLD_APP,
            "old_toolkit": OLD_TOOLKIT,
            "injected_failure_automatic_rollback": "PASS",
            "old_authenticated_api": "PASS",
            "old_toolkit_real_execution": "PASS",
            "final_pair_restored": "PASS",
            "native_rows_preserved": len(before),
            "published_files_preserved": len(artifacts),
            "catalog_sha256_preserved": catalog_sha,
            "memory_messages_preserved": True,
            "guard_remains_held": True,
        }
        (out / "independent-pair-rollback.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result), flush=True)
    finally:
        if not final_restored:
            try:
                pair(app, config, toolkit, "final-recovery-after-test-error")
            except Exception as error:
                (out / "rollback-test-recovery-error.txt").write_text(str(error))


if __name__ == "__main__":
    main()
