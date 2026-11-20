#!/usr/bin/env python3
"""Enable managed native router discovery without replacing user configuration.

  enable-router-discovery.py opencode.json [--header-timeout-ms N --timeout-ms N]

With the timeouts it also maintains providers.watoom.settings.headerTimeout/timeout (2026-11-19: the router holds a
request while a model switch runs, up to its SWITCH_WAIT_SECONDS, so the client must wait longer than that)."""
import argparse,json,os,pathlib,tempfile
def migrate(path,header_timeout_ms=None,timeout_ms=None):
    path=pathlib.Path(path)
    data=json.loads(path.read_text())
    settings=data["providers"]["watoom"].setdefault("settings",{})
    want={"watoomRouterDiscovery":True}
    if header_timeout_ms:want["headerTimeout"]=int(header_timeout_ms)
    if timeout_ms:want["timeout"]=int(timeout_ms)
    if all(settings.get(k)==v for k,v in want.items()):
        return False
    settings.update(want)
    mode=path.stat().st_mode & 0o777
    owner=path.stat()
    fd,name=tempfile.mkstemp(dir=path.parent,prefix=".router-config-")
    try:
        with os.fdopen(fd,"w") as stream:
            json.dump(data,stream,indent=2);stream.write("\n");stream.flush();os.fsync(stream.fileno())
        os.chmod(name,mode);os.chown(name,owner.st_uid,owner.st_gid)
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)
    return True
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("path");p.add_argument("--header-timeout-ms",type=int);p.add_argument("--timeout-ms",type=int);a=p.parse_args()
    print("CHANGED" if migrate(a.path,a.header_timeout_ms,a.timeout_ms) else "UNCHANGED")
