#!/usr/bin/env python3
"""Snapshot-first reconcile of the Grafana route that forwards Prometheus alerts to Discord.

Owns only the platform folder, rule, contact point and one policy route; every other
contact point and route is preserved. The webhook URL is read from a root-only file
and never printed.
"""
import argparse, copy, datetime, json, pathlib, sys, urllib.parse

p = argparse.ArgumentParser()
p.add_argument("--spec", type=pathlib.Path, required=True)
p.add_argument("--webhook-file", type=pathlib.Path, required=True)
p.add_argument("--helpers", type=pathlib.Path, default=pathlib.Path("/data/ai/helper-scripts"))
p.add_argument("--evidence", type=pathlib.Path, required=True)
p.add_argument("--dry-run", action="store_true")
a = p.parse_args()
sys.path.insert(0, str(a.helpers))
from grafana_access import api  # noqa: E402

spec = json.loads(a.spec.read_text())
a.evidence.mkdir(parents=True, exist_ok=True, mode=0o700)
policy = api("/api/v1/provisioning/policies")
contacts = api("/api/v1/provisioning/contact-points")
rules = api("/api/v1/provisioning/alert-rules")
stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
(a.evidence / f"grafana-before-{stamp}.json").write_text(json.dumps(
    {"policy": policy, "contacts": [{k: v for k, v in c.items() if k != "settings"} for c in contacts],
     "rules": [r["uid"] for r in rules]}, indent=2))

want_route = spec["route"]
routes = [r for r in policy.get("routes", []) if r.get("receiver") != want_route["receiver"]]
desired_policy = copy.deepcopy(policy)
desired_policy["routes"] = routes + [want_route]
have_contact = any(c.get("uid") == spec["contact"]["uid"] for c in contacts)
have_rule = any(r["uid"] == spec["rule"]["uid"] for r in rules)
print(f"contact={'update' if have_contact else 'create'} rule={'update' if have_rule else 'create'} "
      f"routes_preserved={len(routes)}")
if a.dry_run:
    print("PASS DRY RUN")
    sys.exit(0)

folders = api("/api/folders")
if not any(f["uid"] == spec["folder"]["uid"] for f in folders):
    api("/api/folders", "POST", spec["folder"])
contact = copy.deepcopy(spec["contact"])
contact["settings"]["url"] = a.webhook_file.read_text().strip()
if have_contact:
    api("/api/v1/provisioning/contact-points/" + contact["uid"], "PUT", contact)
else:
    api("/api/v1/provisioning/contact-points", "POST", contact)
try:
    api("/api/v1/provisioning/policies", "PUT", desired_policy)
    if have_rule:
        api("/api/v1/provisioning/alert-rules/" + spec["rule"]["uid"], "PUT", spec["rule"])
    else:
        api("/api/v1/provisioning/alert-rules", "POST", spec["rule"])
    group_path = f"/api/v1/provisioning/folder/{spec['folder']['uid']}/rule-groups/" + urllib.parse.quote(spec["group"]["name"])
    group = api(group_path)
    group["interval"] = spec["group"]["interval"]
    api(group_path, "PUT", group)
except Exception:
    api("/api/v1/provisioning/policies", "PUT", policy)
    raise

live = api("/api/v1/provisioning/policies")
receivers = [r.get("receiver") for r in live.get("routes", [])]
assert want_route["receiver"] in receivers, "platform route missing after reconcile"
assert all(r.get("receiver") in receivers for r in routes), "an existing route was lost"
print(f"PASS routes={receivers}")
