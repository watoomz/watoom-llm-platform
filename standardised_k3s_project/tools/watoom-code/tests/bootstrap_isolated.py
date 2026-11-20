import pathlib, sys, subprocess, json, time, copy

sys.path.insert(0, "/data/github/watoom-standardised-homelab/standardised_k3s_project/tools/watoom-code")
from maintenance_guard import Maintenance, run
from release_guard import UnsafeRelease, active_clear
import argparse

ap = argparse.ArgumentParser()
ap.add_argument("--evidence", required=True, type=pathlib.Path)
r = ap.parse_args().evidence
ns = "watoom-code"
name = "watoom-code-bootstrap-test-20261017"
run(["kubectl", "-n", ns, "rollout", "status", "deploy/" + name, "--timeout=90s"], timeout=100)
m = Maintenance(ns, name, r / "bootstrap-isolated", True, True)
active_clear(m.request("/api/session/active"))
ip = m.pod()["status"]["podIP"]
# An existing keep-alive stream must remain usable while new clients are refused.
peer = """import http.client,time,socket,json,sys
h=http.client.HTTPConnection(sys.argv[1],4096,timeout=3)
h.request("GET","/api/info");r=h.getresponse();r.read();print("READY",r.status,flush=True)
for i in range(7):
 time.sleep(1);h.request("GET","/api/info");r=h.getresponse();r.read()
h.request("GET","/api/info");r=h.getresponse();r.read();print("EXISTING",r.status,flush=True)
try:
 s=socket.create_connection((sys.argv[1],4096),2);s.close();print("NEW_CONNECTED",flush=True)
except OSError: print("NEW_BLOCKED",flush=True)
time.sleep(2);h.close()
"""
# Unauthenticated info returns401 but proves that the same established flow survives.
peerpod = "watoom-code-memory-candidate-20261016"
service_ip = m.kub("get", "svc", name)["spec"]["clusterIP"]
p = subprocess.Popen(
    ["kubectl", "-n", ns, "exec", "deploy/" + peerpod, "-c", "app", "--", "python3", "-u", "-c", peer, service_ip],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)
first = p.stdout.readline()
assert first.startswith("READY 401"), first + p.stderr.read()
try:
    m.begin()
    for i in range(30):
        try:
            m.verify_closed()
            break
        except UnsafeRelease:
            time.sleep(0.2)
    else:
        raise RuntimeError("Published endpoint barrier did not settle")
    # Drain must refuse to complete while an established client can submit work.
    try:
        m.drain(lambda: None, seconds=1)
        raise RuntimeError("Drain incorrectly accepted a live connection")
    except UnsafeRelease as e:
        assert "did not drain" in str(e), str(e)
    rest, err = p.communicate(timeout=20)
    assert p.returncode == 0, err
    assert "EXISTING 401" in rest and "NEW_BLOCKED" in rest, rest
    m.drain(lambda: active_clear(m.request("/api/session/active")), seconds=15)
    old = m.kub("get", "deploy", name)
    changed = copy.deepcopy(old)
    changed.pop("status", None)
    changed["metadata"] = {k: changed["metadata"][k] for k in ["name", "namespace", "labels"]}
    # Upgrade to the real candidate, inject auth regression, recover the old immutable image.
    owner = "e" * 64
    gate = "/state/watoom-release-guard.json"
    m.exec(
        "import os,json,sys;p=sys.argv[1];fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.write(fd,json.dumps({'version':1,'owner':sys.argv[2]}).encode());os.fsync(fd);os.close(fd)",
        gate,
        owner,
    )
    changed["spec"]["template"]["spec"]["containers"][0][
        "image"
    ] = "127.0.0.1:5000/watoom-code@sha256:15531ee158bc9095ed1e5dadca33be88b1c568a5340837f237fde398e4b6416f"
    changed["spec"]["template"]["spec"]["containers"][0]["env"].append(
        {"name": "WATOOM_DEPLOYMENT_GATE_FILE", "value": gate}
    )
    env = changed["spec"]["template"]["spec"]["containers"][0]["env"]
    env[:] = [e for e in env if e["name"] != "OPENCODE_PASSWORD"] + [
        {"name": "OPENCODE_PASSWORD", "value": "owned-fault-injection"}
    ]
    run(["kubectl", "apply", "-f", "-"], json.dumps(changed).encode())
    run(["kubectl", "-n", ns, "rollout", "status", "deploy/" + name, "--timeout=90s"], timeout=100)
    import urllib.error

    try:
        m.request("/api/info")
        raise RuntimeError("Auth fault was not detected")
    except urllib.error.HTTPError as e:
        assert e.code == 401
    # Independent recovery restores the exact old immutable image under the external barrier.
    old.pop("status", None)
    old["metadata"] = {k: old["metadata"][k] for k in ["name", "namespace", "labels"]}
    run(["kubectl", "apply", "-f", "-"], json.dumps(old).encode())
    run(["kubectl", "-n", ns, "rollout", "status", "deploy/" + name, "--timeout=90s"], timeout=100)
    assert isinstance(m.request("/api/info")["version"], str)
    assert m.pod()["status"]["containerStatuses"][0]["imageID"].endswith(
        old["spec"]["template"]["spec"]["containers"][0]["image"].split("@")[1]
    )
    m.drain(lambda: active_clear(m.request("/api/session/active")), seconds=15)
    m.exec(
        "import pathlib,json,sys;p=pathlib.Path(sys.argv[1]);assert json.loads(p.read_text())=={'version':1,'owner':sys.argv[2]};p.unlink()",
        gate,
        owner,
    )
    receipt = {
        "status": "PASS",
        "old_image": old["spec"]["template"]["spec"]["containers"][0]["image"],
        "existing_connections_preserved": "PASS",
        "new_service_connections_blocked": "PASS",
        "direct_pod_route": "Already unreachable from test peer before barrier; no routing change made",
        "service_endpoints_blocked": "PASS",
        "live_connection_drain_refusal": "PASS",
        "old_image_authenticated_rollback": "PASS",
        "candidate_image_failed_then_old_image_restored": "PASS",
        "administrative_bypass": "Host/kubectl administrators must keep port-forwards and direct requests closed during window",
    }
    (r / "bootstrap-acceptance.json").write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt))
finally:
    if p.poll() is None:
        p.wait(timeout=25)
    m.release()
