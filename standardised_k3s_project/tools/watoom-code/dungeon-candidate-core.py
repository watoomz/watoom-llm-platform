#!/usr/bin/env python3
"""Exact-image owned candidate memory and admission race acceptance; no model calls."""

import argparse, base64, concurrent.futures, json, pathlib, sys, time, urllib.request, urllib.error
from maintenance_guard import Maintenance
from release_guard import durable_clearance


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", required=True, type=pathlib.Path)
    a = ap.parse_args()
    out = a.evidence.resolve() / "native-candidate"
    identity = json.loads((out / "identity.json").read_text())
    assert identity["name"] == "watoom-code-dungeon-candidate" and identity["owner"] == a.evidence.name
    assert json.loads((out / "independent-native-pair-rollback.json").read_text())["status"] == "PASS"
    report = out / "core-acceptance.json"
    assert not report.exists(), "Preserve completed acceptance"
    m = Maintenance(identity["namespace"], identity["name"], out, True, True)
    base = "http://" + m.kub("get", "svc", m.name)["spec"]["clusterIP"] + ":4096"
    auth = "Basic " + base64.b64encode(("opencode:" + m.password).encode()).decode()

    def api(path, body=None, method=None):
        req = urllib.request.Request(
            base + path,
            headers={"Authorization": auth, "Content-Type": "application/json"},
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read()
            return json.loads(raw) if raw else None

    owner = (out / "guard-owner.private").read_text().strip()
    assert api("/api/session/active")["data"] == {}
    assert api("/api/session/deployment-guard")["data"]["held"]
    durable_clearance(out / "state/application.sqlite")
    api("/api/session/deployment-guard", {"action": "release", "owner": owner})
    try:
        sessions = [
            api(
                "/api/session",
                {
                    "agent": "build",
                    "permissions": [
                        {"action": action, "resource": identity["project"], "effect": "allow"}
                        for action in ("watoom_memory_remember", "watoom_memory_recall")
                    ],
                    "location": {"directory": identity["project"]},
                    "title": "Owned exact-image memory and admission fixture",
                },
            )["data"]["id"]
            for _ in range(2)
        ]
        (out / "core-sessions.private.json").write_text(json.dumps(sessions))
        fact = "Owned dungeon release memory fixture 20261017 core-marker-7fba"
        api("/api/session/" + sessions[0] + "/command", {"name": "remember", "text": fact})
        api("/api/session/" + sessions[1] + "/command", {"name": "recall", "text": "core-marker-7fba"})
        assert fact in json.dumps(api("/api/session/" + sessions[1] + "/message"))
        with concurrent.futures.ThreadPoolExecutor(1) as pool:
            pending = pool.submit(
                api, "/api/session/" + sessions[0] + "/shell", {"command": "python3 -c 'import time;time.sleep(2)'"}
            )
            for _ in range(80):
                if api("/api/session/deployment-guard")["data"]["leases"] > 0:
                    break
                time.sleep(0.025)
            else:
                raise ValueError("Actual shell lease missing")
            try:
                api("/api/session/deployment-guard", {"action": "acquire", "owner": owner})
            except urllib.error.HTTPError as error:
                assert error.code == 409
            else:
                raise ValueError("Active shell incorrectly fenced")
            pending.result()
        for item in api("/api/session/" + sessions[0] + "/inbox")["data"]:
            assert item["type"] == "synthetic"
            api("/api/session/" + sessions[0] + "/inbox/" + item["id"], method="DELETE")
    finally:
        assert api("/api/session/active")["data"] == {}, "Do not fence or stop active work"
        api("/api/session/deployment-guard", {"action": "acquire", "owner": owner})
    try:
        api(
            "/api/session/" + sessions[0] + "/command",
            {"name": "remember", "text": "must not write under deployment fence"},
        )
    except urllib.error.HTTPError as error:
        assert error.code in (400, 409, 500, 503)
    else:
        raise ValueError("Held deployment guard admitted memory command")
    durable_clearance(out / "state/application.sqlite")
    result = {
        "status": "PASS",
        "image": identity["image"],
        "memory": "PASS real cross-session remember/recall",
        "guard_race": "PASS actual shell lease prevents acquisition",
        "held_guard_rejection": "PASS",
        "model_calls": 0,
        "native_guard_held": True,
    }
    report.write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
