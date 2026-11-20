#!/usr/bin/env python3
"""Exercise the production fences and digest validator on the owned isolated pair."""

import argparse, copy, hashlib, json, os, pathlib, shutil, sqlite3, subprocess, tempfile, time
from maintenance_guard import Maintenance
from toolkit_release_fence import ToolkitFence
from creative_release import Release
from release_guard import UnsafeRelease, durable_clearance


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def clean(value):
    value = copy.deepcopy(value)
    value.pop("status", None)
    for key in ("uid", "resourceVersion", "creationTimestamp", "generation", "managedFields"):
        value["metadata"].pop(key, None)
    value["metadata"].get("annotations", {}).pop("kubectl.kubernetes.io/last-applied-configuration", None)
    value["spec"]["replicas"] = 1
    return value


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", required=True, type=pathlib.Path)
    ap.add_argument("--resume-old", action="store_true")
    a = ap.parse_args()
    evidence = a.evidence.resolve()
    out = evidence / "native-candidate"
    root = pathlib.Path(__file__).resolve().parents[2]
    identity = json.loads((out / "identity.json").read_text())
    app = identity["name"]
    toolkit = identity["toolkit"]
    ns = identity["namespace"]
    if (
        app != "watoom-code-dungeon-candidate"
        or toolkit != "watoom-toolkit-dungeon-candidate"
        or identity["owner"] != evidence.name
    ):
        raise ValueError("Owned isolated pair required")
    for name in ("native-api-acceptance.json", "native-cancel-acceptance.json", "native-restart-acceptance.json"):
        if json.loads((out / name).read_text())["status"] != "PASS":
            raise ValueError("Complete focused candidate tests first")
    report = out / "rollback-native"
    report.mkdir(mode=0o700, exist_ok=a.resume_old)
    if a.resume_old:
        assert json.loads((report / "01-prior-working-pair/verification.json").read_text())["status"] == "PASS"
        assert json.loads((report / "old-real-inspect.json").read_text())["status"] == "FAIL"
        assert not (report / "old-retry-real-inspect.json").exists()
    m = Maintenance(ns, app, out, True, True)

    def cmd(args, input=None, timeout=60, cwd=None):
        p = subprocess.run(args, input=input, capture_output=True, timeout=timeout, cwd=cwd)
        if p.returncode:
            raise RuntimeError(p.stderr.decode(errors="replace")[-500:])
        return p.stdout

    def guard():
        if m.request("/api/session/active")["data"] != {}:
            raise UnsafeRelease("Active isolated execution; never interrupt it")
        g = m.request("/api/session/deployment-guard")["data"]
        if g.get("held") is not True or g.get("leases") != 0:
            raise UnsafeRelease("Native guard must stay held")
        durable_clearance(out / "state/application.sqlite")

    def atomic(path, data, uid):
        fd, tmp = tempfile.mkstemp(prefix=".owned-rollback-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as f:
                os.fchmod(f.fileno(), 0o600)
                os.fchown(f.fileno(), uid, 1009)
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def rows():
        with sqlite3.connect("file:" + str(out / "state/application.sqlite") + "?mode=ro", uri=True) as db:
            return list(db.execute("SELECT id,phase,outcome FROM _watoom_specialist_job ORDER BY id"))

    guard()
    before = rows()
    for name in (app, toolkit):
        d = m.kub("get", "deploy", name)
        if d["metadata"]["labels"]["watoom-test-owner"] != evidence.name:
            raise ValueError("Resource ownership changed")
    current_app = clean(m.kub("get", "deploy", app))
    current_toolkit = clean(m.kub("get", "deploy", toolkit))
    current_config = (out / "config/opencode.json").read_bytes()
    current_catalog = (out / "toolkit-state/asset-catalog/catalog.json").read_bytes()
    if a.resume_old:
        current_app = clean(json.loads((out / (app + ".deployment.private.json")).read_text()))
        current_toolkit = clean(json.loads((out / (toolkit + ".deployment.private.json")).read_text()))
        current_config = (report / "current-config.private.json").read_bytes()
        current_catalog = (report / "current-catalog.json").read_bytes()
    old_app = clean(json.loads((out / (app + ".rollback.private.json")).read_text()))
    old_toolkit = clean(json.loads((out / (toolkit + ".rollback.private.json")).read_text()))
    old_config = (out / "rollback-config.private.json").read_bytes()
    old_catalog = (out / "rollback-catalog.private.json").read_bytes()
    old_images = json.loads((out / "rollback-images.json").read_text())
    artifacts = json.loads((out / "native-api-acceptance.json").read_text())["artifacts"]
    for name, data in (("current-config.private.json", current_config), ("current-catalog.json", current_catalog)):
        (report / name).write_bytes(data)
        (report / name).chmod(0o600)
    # Reuse the exact production digest/capabilities validator; redirect its read-only
    # selector to the explicitly owned candidate, never to the live application.
    verifier = Release.__new__(Release)
    verifier.image = identity["toolkit_image"]
    verifier.cmd = cmd

    def verify_kub(*args):
        if args != ("get", "pods", "-l", "app=watoom-toolkit"):
            raise ValueError("Unexpected verifier operation")
        return m.kub("get", "pods", "-l", "app=" + toolkit)

    verifier.kub = verify_kub

    def ready(expected_app, expected_toolkit):
        deadline = time.monotonic() + 45
        while True:
            try:
                guard()
                info = m.request("/api/info")
                if not isinstance(info.get("version"), str):
                    raise ValueError("Application contract unavailable")
                commands = m.request("/api/command?directory=/workspace")["data"]
                if not {"remember", "recall"} <= {x["name"] for x in commands}:
                    raise ValueError("Memory commands lost")
                pods = m.kub("get", "pods", "-l", "app=" + app)["items"]
                running = [
                    p for p in pods if p["status"]["phase"] == "Running" and not p["metadata"].get("deletionTimestamp")
                ]
                if (
                    len(running) != 1
                    or running[0]["status"]["containerStatuses"][0]["imageID"].split("@")[-1]
                    != expected_app.split("@")[-1]
                ):
                    raise ValueError("App digest mismatch")
                verifier.verify(expected_toolkit)
                return
            except Exception:
                if time.monotonic() > deadline:
                    raise
                time.sleep(1)

    def pair(appvalue, toolkitvalue, config, catalog, label):
        guard()
        phase = report / label
        phase.mkdir(mode=0o700)
        fence = ToolkitFence(
            m.kub, cmd, root, phase, guard, namespace=ns, service=toolkit, state=out / "toolkit-state", state_cwd=True
        )
        fence.acquire()
        atomic(out / "config/opencode.json", config, 1001)
        atomic(out / "toolkit-state/asset-catalog/catalog.json", catalog, 1009)
        for value, name in ((toolkitvalue, toolkit), (appvalue, app)):
            target = clean(value)
            target["spec"]["template"]["metadata"].setdefault("annotations", {})["watoom-owned-rollback-phase"] = label
            cmd(["kubectl", "apply", "-f", "-"], input=json.dumps(target).encode())
            cmd(["kubectl", "-n", ns, "rollout", "status", "deployment/" + name, "--timeout=120s"], timeout=130)
        expected_app = next(
            c["image"] for c in appvalue["spec"]["template"]["spec"]["containers"] if c["name"] == "app"
        )
        expected_toolkit = next(
            c["image"] for c in toolkitvalue["spec"]["template"]["spec"]["containers"] if c["name"] == "toolkit"
        )
        ready(expected_app, expected_toolkit)
        fence.assert_held()
        fence.release()
        entry = next(
            e for e in json.loads(config)["watoom_specialists"]["entries"] if e["descriptor"]["id"] == "local-toolkit"
        )
        route = 'import os,json,sys,urllib.request;r=urllib.request.Request(sys.argv[1]+"/api/catalog",headers={"Authorization":"Bearer "+os.environ["WATOOM_TOKEN"]});d=json.load(urllib.request.urlopen(r,timeout=10));assert isinstance(d["generators"],list);print("ROUTE_PASS")'
        deadline = time.monotonic() + 20
        while True:
            try:
                if m.exec(route, entry["url"]).strip() != b"ROUTE_PASS":
                    raise ValueError("Authenticated route failed")
                break
            except Exception:
                if time.monotonic() > deadline:
                    raise
                time.sleep(1)
        (phase / "verification.json").write_text(
            json.dumps(
                {
                    "status": "PASS",
                    "app_image": expected_app,
                    "toolkit_image": expected_toolkit,
                    "native_guard_held": True,
                    "authenticated_application_and_backend": True,
                },
                indent=2,
            )
        )
        print("PASS owned pair " + label, flush=True)

    catalog = json.loads(current_catalog)
    record = next(v for v in catalog["records"].values() if v["path"].endswith("/builder-floor.glb"))
    source = pathlib.Path("/data/ai/assets") / record["path"]
    if sha(source) != record["sha256"]:
        raise ValueError("Verified probe source changed")
    target = out / "workspace/owned-rollback-probe.glb"
    if a.resume_old:
        if sha(target) != sha(source):
            raise ValueError("Existing owned probe changed")
    else:
        if target.exists():
            raise ValueError("Inspect existing probe; do not overwrite")
        shutil.copyfile(source, target)
        os.chown(target, 1009, 1009)
        target.chmod(0o640)

    def probe(image, label):
        pods = m.kub("get", "pods", "-l", "app=" + toolkit)["items"]
        pod = next(p for p in pods if p["status"]["phase"] == "Running" and not p["metadata"].get("deletionTimestamp"))
        code = 'import os,json,urllib.request;r=urllib.request.Request("http://127.0.0.1:"+os.environ.get("WATOOM_PORT","8879")+"/api/jobs",headers={"Authorization":"Bearer "+os.environ["WATOOM_TOKEN"],"Content-Type":"application/json"},data=json.dumps({"task":"3d-inspect","path":"owned-rollback-probe.glb","timeout":180}).encode());print(urllib.request.urlopen(r,timeout=200).read().decode())'
        value = json.loads(
            cmd(
                ["kubectl", "-n", ns, "exec", pod["metadata"]["name"], "-c", "toolkit", "--", "python3", "-c", code],
                timeout=210,
            )
        )
        (report / (label + "-real-inspect.json")).write_text(json.dumps(value, indent=2))
        if (
            value["status"] != "PASS"
            or value["verification"]["status"] != "PASS"
            or value["worker"]["image_id"].split("@")[-1] != image.split("@")[-1]
        ):
            raise ValueError("Actual isolated Blender inspection failed: " + label)

    try:
        if a.resume_old:
            ready(old_images[app], old_images[toolkit])
            probe(old_images[toolkit], "old-retry")
        else:
            pair(old_app, old_toolkit, old_config, old_catalog, "01-prior-working-pair")
            probe(old_images[toolkit], "old")
        pair(current_app, current_toolkit, current_config, current_catalog, "02-new-before-injection")
        probe(identity["toolkit_image"], "new")
        try:
            verifier.verify(old_images[toolkit])
        except UnsafeRelease as error:
            if "Toolkit runtime digest mismatch" not in str(error):
                raise
            pair(old_app, old_toolkit, old_config, old_catalog, "03-automatic-digest-failure-rollback")
        else:
            raise ValueError("Injected wrong digest was not rejected by production validator")
        pair(current_app, current_toolkit, current_config, current_catalog, "04-final-new-pair-restored")
        if rows() != before:
            raise ValueError("Native durable outcomes changed during rollback")
        if (out / "config/opencode.json").read_bytes() != current_config or (
            out / "toolkit-state/asset-catalog/catalog.json"
        ).read_bytes() != current_catalog:
            raise ValueError("Final exact configuration/Catalog not restored")
        for artifact in artifacts:
            if sha(out / "published" / artifact["reference"][9:]) != artifact["sha256"]:
                raise ValueError("Prior native artifact changed")
        if sha(source) != record["sha256"]:
            raise ValueError("Original probe source modified")
        result = {
            "status": "PASS",
            "image": identity["image"],
            "toolkit_image": identity["toolkit_image"],
            "old_app": old_images[app],
            "old_toolkit": old_images[toolkit],
            "injected_failure_automatic_rollback": "PASS production digest validator rejected wrong actual image expectation",
            "old_toolkit_real_execution": "PASS actual isolated Blender inspect/export/reimport",
            "new_toolkit_legacy_regression": "PASS actual isolated Blender inspect/export/reimport",
            "final_pair_restored": "PASS exact images/config/Catalog",
            "native_rows_preserved": len(before),
            "native_artifacts_preserved": len(artifacts),
            "native_guard_held": True,
            "live_application_changed": False,
        }
        (out / "independent-native-pair-rollback.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result), flush=True)
    except Exception as error:
        (report / "continuation-required.json").write_text(
            json.dumps(
                {
                    "status": "BLOCKED_TEST_STATE_PRESERVED",
                    "error": str(error),
                    "action": "Inspect owned phase fence and actual active work; never force rollout or erase evidence",
                },
                indent=2,
            )
        )
        raise


if __name__ == "__main__":
    main()
