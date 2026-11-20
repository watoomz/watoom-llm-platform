#!/usr/bin/env python3
import json, os, pathlib, sys, tempfile

p = pathlib.Path(sys.argv[1])
before = p.read_bytes()
data = json.loads(before)
plugins = data.setdefault("plugins", [])
target = "/config/plugins/searxng-search"
if target not in [x if isinstance(x, str) else x.get("package") for x in plugins]:
    plugins.append(target)
data["websearch"] = {"provider": "searxng"}
if json.loads(before) == data:
    print("UNCHANGED")
    sys.exit(0)
st = p.stat()
fd, tmp = tempfile.mkstemp(prefix=".searxng-config-", dir=p.parent)
try:
    with os.fdopen(fd, "w") as f:
        os.fchmod(f.fileno(), st.st_mode & 0o777)
        os.fchown(f.fileno(), st.st_uid, st.st_gid)
        json.dump(data, f, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    assert p.read_bytes() == before, "Concurrent configuration edit"
    os.replace(tmp, p)
finally:
    if os.path.exists(tmp):
        os.unlink(tmp)
print("CHANGED")
