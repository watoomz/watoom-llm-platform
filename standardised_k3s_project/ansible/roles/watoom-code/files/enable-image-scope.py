#!/usr/bin/env python3
import json, os, pathlib, re, sys, tempfile

p = pathlib.Path(sys.argv[1])
target = sys.argv[2]
pattern = r"/config/watoom-tools/image-scope(?:-[a-f0-9]{64})?"
if not re.fullmatch(pattern, target):
    raise SystemExit("Invalid maintained image-scope package path")
if p.is_symlink():
    raise SystemExit("Real native configuration required")
before = p.read_bytes()
data = json.loads(before)
plugins = data.setdefault("plugins", [])
updated = [
    x
    for x in plugins
    if not (
        isinstance(x if isinstance(x, str) else x.get("package"), str)
        and re.fullmatch(pattern, x if isinstance(x, str) else x.get("package"))
    )
]
updated.append(target)
data["plugins"] = updated
if data == json.loads(before):
    print("UNCHANGED")
    sys.exit(0)
st = p.stat()
fd, tmp = tempfile.mkstemp(prefix=".image-scope-", dir=p.parent)
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
