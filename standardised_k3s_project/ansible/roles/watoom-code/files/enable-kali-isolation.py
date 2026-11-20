#!/usr/bin/env python3
"""Deny Kali MCP tools to the built-in agents (build, plan, general, compaction, ...).

The WatooM agents carry their own Kali denies in their generated prompt files; the
built-in agents have no file, so their deny lives in the configuration's `agents`
overrides. Only watoom-kali may use Kali. Prints CHANGED or UNCHANGED.
Usage: enable-kali-isolation.py <opencode.json> <agent> [<agent> ...]
"""
import json, os, pathlib, sys, tempfile

DENY = [{"action": a, "resource": "*", "effect": "deny"} for a in ("watoom-kali_*", "watoom_kali_*")]
p = pathlib.Path(sys.argv[1])
names = sys.argv[2:]
if not names or "watoom-kali" in names:
    raise SystemExit("usage: enable-kali-isolation.py <opencode.json> <agent>... (never watoom-kali)")
before = p.read_bytes()
data = json.loads(before)
agents = data.setdefault("agents", {})
for name in names:
    entry = agents.setdefault(name, {})
    rules = [r for r in entry.get("permissions", []) if r not in DENY]
    entry["permissions"] = rules + DENY  # last match wins, so the denies go last
after = json.dumps(data, indent=2) + "\n"
if after.encode() == before:
    print("UNCHANGED")
    sys.exit(0)
st = p.stat()
fd, tmp = tempfile.mkstemp(prefix=".kali-isolation-", dir=p.parent)
try:
    with os.fdopen(fd, "w") as f:
        os.fchmod(f.fileno(), st.st_mode & 0o777)
        os.fchown(f.fileno(), st.st_uid, st.st_gid)
        f.write(after)
        f.flush()
        os.fsync(f.fileno())
    assert p.read_bytes() == before, "Concurrent configuration edit"
    os.replace(tmp, p)
finally:
    if os.path.exists(tmp):
        os.unlink(tmp)
print("CHANGED")
