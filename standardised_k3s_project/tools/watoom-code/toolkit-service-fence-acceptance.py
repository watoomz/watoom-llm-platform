#!/usr/bin/env python3
"""Owned legacy-image HTTP/Service drain and exact restoration acceptance."""

import argparse, pathlib, json, subprocess, secrets, time, os, threading, urllib.request, urllib.error
from toolkit_service_fence import ServiceFence


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", required=True, type=pathlib.Path)
    a = ap.parse_args()
    evidence = a.evidence.resolve()
    if not evidence.is_relative_to("/data/ai/helper-scripts/reports"):
        raise ValueError("Private evidence required")
    name = "toolkit-fence-" + time.strftime("%Y%m%d%H%M%S", time.gmtime())
    namespace = "watoom-code"
    base = pathlib.Path("/data/ai/builds") / evidence.name / name
    base.mkdir()
    for part in ("state", "workspace", "fixture"):
        (base / part).mkdir()
        os.chown(base / part, 1009, 1009)
        os.chmod(base / part, 0o770)

    def kub(*args, body=None):
        p = subprocess.run(
            ["kubectl", "-n", namespace, *args],
            input=json.dumps(body) if body is not None else None,
            text=True,
            capture_output=True,
            timeout=75,
        )
        if p.returncode:
            raise RuntimeError(p.stderr[-700:])
        return json.loads(p.stdout) if p.stdout.strip().startswith(("{", "[")) else p.stdout

    old = kub("get", "deploy", "watoom-toolkit", "-o", "json")
    image = next(c["image"] for c in old["spec"]["template"]["spec"]["containers"] if c["name"] == "toolkit")
    # Extract only maintained program text, never environment/configuration.
    original = kub("exec", "deploy/watoom-toolkit", "-c", "toolkit", "--", "cat", "/opt/watoom/agent.py")
    (base / "fixture/original.py").write_text(original)
    (base / "fixture/agent.py").write_text(
        'import runpy,sys\nsys.path.insert(0,"/opt/watoom")\nns=runpy.run_path("/fixture/original.py",run_name="legacy_fixture")\nns["main"].__globals__["make_command"]=lambda payload,jobdir:[sys.executable,"-c","import time;time.sleep(5);print(123)"]\nns["main"]()\n'
    )
    token = secrets.token_hex(32)
    pod = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": name, "labels": {"app": name}},
        "spec": {
            "restartPolicy": "Never",
            "activeDeadlineSeconds": 180,
            "automountServiceAccountToken": False,
            "securityContext": {"runAsUser": 1009, "runAsGroup": 1009, "fsGroup": 1009},
            "containers": [
                {
                    "name": "toolkit",
                    "image": image,
                    "command": ["python3", "-B", "/opt/watoom/agent.py"],
                    "env": [
                        {"name": "WATOOM_TOKEN", "value": token},
                        {"name": "WATOOM_STATE", "value": "/state"},
                        {"name": "WATOOM_WORKSPACE", "value": "/workspace"},
                    ],
                    "resources": {
                        "requests": {"cpu": "100m", "memory": "128Mi"},
                        "limits": {"cpu": "1", "memory": "512Mi"},
                    },
                    "securityContext": {
                        "allowPrivilegeEscalation": False,
                        "readOnlyRootFilesystem": True,
                        "capabilities": {"drop": ["ALL"]},
                        "seccompProfile": {"type": "RuntimeDefault"},
                    },
                    "volumeMounts": [{"name": x, "mountPath": "/" + x} for x in ("state", "workspace", "fixture")]
                    + [
                        {
                            "name": "fixture",
                            "mountPath": "/opt/watoom/agent.py",
                            "subPath": "agent.py",
                            "readOnly": True,
                        },
                        {"name": "tmp", "mountPath": "/tmp"},
                    ],
                }
            ],
            "volumes": [
                {"name": x, "hostPath": {"path": str(base / x), "type": "Directory"}}
                for x in ("state", "workspace", "fixture")
            ]
            + [{"name": "tmp", "emptyDir": {"sizeLimit": "64Mi"}}],
        },
    }
    service = {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": name},
        "spec": {"selector": {"app": name}, "ports": [{"port": 8879, "targetPort": 8879}], "type": "ClusterIP"},
    }
    created = []
    report = {"status": "RUNNING", "fixture_only": True, "image": image}
    client = None

    def save(value):
        (evidence / "toolkit-service-fence-recovery.private.json").write_text(json.dumps(value, indent=2))
        os.chmod(evidence / "toolkit-service-fence-recovery.private.json", 0o600)

    try:
        p = kub("create", "-f", "-", "-o", "json", body=pod)
        created.append(("pod", name, p["metadata"]["uid"]))
        service = kub("create", "-f", "-", "-o", "json", body=service)
        created.append(("service", name, service["metadata"]["uid"]))
        url = "http://" + service["spec"]["clusterIP"] + ":8879"

        def http(path, body=None, timeout=15):
            req = urllib.request.Request(
                url + path,
                data=json.dumps(body).encode() if body is not None else None,
                headers={"Authorization": "Bearer " + token},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.load(resp)

        deadline = time.monotonic() + 50
        while time.monotonic() < deadline:
            try:
                http("/healthz", timeout=1)
                break
            except (OSError, urllib.error.URLError):
                time.sleep(0.5)
        else:
            raise RuntimeError("Fixture not reachable through observed Service")
        responses = []
        errors = []

        def call():
            try:
                responses.append(http("/api/jobs", {"task": "probe", "timeout": 15}))
            except Exception as error:
                errors.append(str(error))

        client = threading.Thread(target=call)
        client.start()

        def get(kind, item=None, labels=None):
            if kind == "jobs" or (kind == "pods" and labels == {"app": "watoom-toolkit-worker"}):
                return {"items": []}  # This owned fixture launches local processes only.
            args = (
                ["get", kind]
                + ([item] if item else [])
                + (["-l", ",".join(k + "=" + v for k, v in labels.items())] if labels else [])
                + ["-o", "json"]
            )
            return kub(*args)

        def probe(observed):
            actual = kub("get", "pod", name, "-o", "json")
            code = 'import pathlib,json; p=pathlib.Path("/proc/1"); cmd=(p/"cmdline").read_bytes().decode().strip(chr(0)).split(chr(0)); established=sum(1 for table in ("tcp","tcp6") for line in (p/"net"/table).read_text().splitlines()[1:] if line.split()[1].split(":")[1]=="22AF" and line.split()[3]=="01");print(json.dumps({"server_pid":1,"server_command":cmd,"threads":len(list((p/"task").iterdir())),"established":established}))'
            result = kub("exec", name, "-c", "toolkit", "--", "python3", "-c", code)
            result["pod_uid"] = actual["metadata"]["uid"]
            result["container_id"] = next(
                c["containerID"] for c in actual["status"]["containerStatuses"] if c["name"] == "toolkit"
            )
            return result

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if probe(p)["threads"] > 1:
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("Controlled in-flight handler did not start")
        fence = ServiceFence(
            get,
            lambda n, ops: kub("patch", "service", n, "--type=json", "-p", json.dumps(ops)),
            save,
            lambda: None,
            probe,
            service=name,
        )
        fence.acquire(seconds=30)
        client.join(5)
        if errors or not responses or responses[0].get("status") != "PASS":
            raise RuntimeError("In-flight request was interrupted")
        blocked = False
        try:
            http("/healthz", timeout=1)
        except (OSError, urllib.error.URLError):
            blocked = True
        if not blocked:
            raise RuntimeError("Selector fence did not block Service traffic")
        fence.release()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                http("/healthz", timeout=1)
                break
            except (OSError, urllib.error.URLError):
                time.sleep(0.5)
        else:
            raise RuntimeError("Exact Service restoration did not restore application HTTP")
        restored = kub("get", "service", name, "-o", "json")
        if restored["spec"] != service["spec"]:
            raise RuntimeError("Service configuration changed beyond selector")
        report.update(
            status="PASS",
            inflight_completed_naturally=True,
            new_service_requests_blocked=True,
            exact_service_restore=True,
            application_http_after_restore=True,
        )
    except BaseException as error:
        report.update(status="FAIL", error=type(error).__name__ + ": " + str(error))
        raise
    finally:
        if client:
            client.join(20)
        cleanup = []
        for kind, n, uid in reversed(created):
            actual = kub("get", kind, n, "-o", "json")
            if actual["metadata"]["uid"] != uid:
                raise RuntimeError("Owned fixture UID changed")
            try:
                kub("delete", kind, n, "--wait=true", "--timeout=60s")
            except Exception as error:
                cleanup.append(str(error))
        report["cleanup"] = "FAIL" if cleanup else "PASS"
        if cleanup:
            report.update(status="FAIL", cleanup_errors=cleanup)
        (evidence / "toolkit-service-fence-acceptance.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report))


if __name__ == "__main__":
    main()
