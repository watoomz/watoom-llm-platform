#!/usr/bin/env python3
"""Select (or with '-' remove) the versioned language-knowledge plugin in native opencode.json without touching other entries."""

import json, os, pathlib, re, sys, tempfile

p = pathlib.Path(sys.argv[1])
target = sys.argv[2]
options = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
pattern = r"/config/watoom-tools/language-knowledge-[a-f0-9]{64}"
if target != "-" and not re.fullmatch(pattern, target):
    raise SystemExit("Invalid maintained language-knowledge package path")
if p.is_symlink():
    raise SystemExit("Real native configuration required")
name = lambda x: x if isinstance(x, str) else x.get("package")
before = p.read_bytes()
data = json.loads(before)
plugins = data.setdefault("plugins", [])
updated = [x for x in plugins if not (isinstance(name(x), str) and re.fullmatch(pattern, name(x)))]
if target != "-":
    updated.append({"package": target, "options": options})
data["plugins"] = updated
if data == json.loads(before):
    print("UNCHANGED")
    sys.exit(0)
st = p.stat()
fd, tmp = tempfile.mkstemp(prefix=".language-knowledge-", dir=p.parent)
try:
    with os.fdopen(fd, "w") as f:
        os.fchmod(f.fileno(), st.st_mode & 0o777)
        os.fchown(f.fileno(), st.st_uid, st.st_gid)
        json.dump(data, f, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    if p.read_bytes() != before:
        raise RuntimeError("Concurrent native configuration edit")
    os.replace(tmp, p)
finally:
    if os.path.exists(tmp):
        os.unlink(tmp)
print("CHANGED")
