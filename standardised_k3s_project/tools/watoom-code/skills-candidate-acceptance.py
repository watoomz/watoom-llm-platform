#!/usr/bin/env python3
"""Aggregate existing evidence, then verify the exact fenced candidate and final GUI session."""

import argparse, pathlib, json, sys, hashlib, re, time, urllib.error, sqlite3
from maintenance_guard import Maintenance
import release_guard


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--evidence", required=True, type=pathlib.Path)
    a = p.parse_args()
    root = a.evidence.resolve()
    out = root / "candidate"
    identity = json.loads((out / "identity.json").read_text())
    assert identity["name"] == "watoom-code-skills-candidate-20261017" and identity["owner"] == root.name
    m = Maintenance(identity["namespace"], identity["name"], out, True, True)
    release_guard.validate(m.request("/api/session/deployment-guard"), True)
    release_guard.active_clear(m.request("/api/session/active"))
    release_guard.durable_clearance(out / "state/application.sqlite")
    pod = m.pod()
    container = next(x for x in pod["status"]["containerStatuses"] if x["name"] == "app")
    assert container["ready"] and container["imageID"].endswith(identity["image"].split("@")[1])
    for phase in [
        "isolation",
        "disable",
        "update",
        "rollback",
        "unsafe",
        "smoke",
        "persist",
        "old-image-rollback",
        "old-image-gui",
        "guard",
    ]:
        proof = json.loads((out / (phase + "-acceptance.json")).read_text())
        assert proof["status"] == "PASS", phase
    rollback = json.loads((out / "old-image-rollback-acceptance.json").read_text())
    assert rollback["steps"][-1]["image"] == identity["image"]
    journal = json.loads((out / "final-real-session-admission.json").read_text())
    gui = pathlib.Path(journal["gui"])
    assert json.loads((gui / "skills-browser.json").read_text())["status"] == "PASS"
    session = json.loads((gui / "runtime-session.json").read_text())["session"]
    messages = m.request("/api/session/" + session + "/message")
    calls = [x for x in walk(messages) if x.get("type") == "tool" and x.get("name") == "skill"]
    assert (
        len(calls) == 1
        and calls[0]["state"]["status"] == "completed"
        and "SKILLS_MANAGER_ACCEPTANCE_V1" in json.dumps(messages)
    )
    (out / "final-real-agent-acceptance.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "image": identity["image"],
                "session": session,
                "native_skill_calls": 1,
                "gui": str(gui),
            },
            indent=2,
        )
    )
    try:
        m.request("/api/config", authenticated=False)
    except urllib.error.HTTPError as error:
        assert error.code == 401
    else:
        raise AssertionError("Anonymous access allowed")
    production = Maintenance("watoom-code", "watoom-code", out, True, True)

    def native(client):
        return {
            item["id"]: hashlib.sha256(
                re.sub(r"^- (opencode version|install/channel):.*$", "", item["content"], flags=re.M).encode()
            ).hexdigest()
            for item in client.request("/api/skill")["data"]
        }

    expected = native(production)
    deadline = time.monotonic() + 60
    while native(m) != expected:
        if time.monotonic() > deadline:
            raise AssertionError("Native skill preservation mismatch")
        time.sleep(2)
    models = lambda client: {
        (x["providerID"], x["id"])
        for x in client.request("/api/model")["data"]
        if x["enabled"] and x["providerID"] in ("watoom", "opencode")
    }
    assert models(production) <= models(m)
    deadline = time.monotonic() + 60
    while True:
        status = m.request("/api/mcp")["data"]
        if {"watoom-kali", "watoom-llama-mesh"} <= {x["name"] for x in status if x["status"]["status"] == "connected"}:
            break
        if time.monotonic() > deadline:
            raise AssertionError("MCP connection recovery failed")
        time.sleep(2)
    creative = json.loads((out / "creative-messages.private.json").read_text())
    calls = [x for x in walk(creative) if x.get("type") == "tool" and x.get("name") == "watoom_specialist_run"]
    assert len(calls) == 1 and calls[0]["state"]["status"] == "completed"
    job = json.loads((out / "creative-prompt.json").read_text())["operation"]["job"]
    with sqlite3.connect("file:" + str(out / "state/application.sqlite") + "?mode=ro", uri=True) as db:
        assert db.execute("SELECT phase FROM _watoom_specialist_job WHERE job=?", (job,)).fetchone() == ("completed",)
    report = {
        key: "PASS"
        for key in [
            "guard_boot",
            "guard_race",
            "rollback",
            "authenticated_api",
            "authenticated_gui",
            "memory",
            "skills",
            "skill_security",
            "skill_versions",
            "skill_persistence",
            "skill_browser",
            "skill_runtime",
            "skill_old_image_rollback",
        ]
    }
    report.update(
        status="PASS",
        image=identity["image"],
        acceptance_root=str(out),
        skill_collection_sha256=hashlib.sha256((root / "snapshot/discovery.sqlite").read_bytes()).hexdigest(),
        skill_collection_root="/data/ai/skill-registry/wp-sk1-20261014/repositories",
        native_skills_preserved=expected,
        existing_creative_job=job,
        creative_replayed=False,
        guard_race_evidence=str(out / "guard-acceptance.json"),
        real_agent_evidence=str(out / "final-real-agent-acceptance.json"),
        cold_start_negative_evidence="Retained in gui/persist* failure files; fixed via native registry events",
        cloud_credentials="Not copied to isolated candidate; full production provider catalog checked during guarded promotion",
        reddit_records="NONE VERIFIED in retained collection; no rescrape",
    )
    (out / "candidate-acceptance.json").write_text(json.dumps(report, indent=2))
    print("PASS exact-image candidate browser/runtime/persistence/rollback/security and preserved native integrations")


if __name__ == "__main__":
    main()
