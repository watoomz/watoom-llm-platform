#!/usr/bin/env python3
"""Enable managed native router discovery without replacing user configuration."""
import argparse,json,os,pathlib,tempfile
def migrate(path):
    path=pathlib.Path(path)
    data=json.loads(path.read_text())
    settings=data["providers"]["watoom"].setdefault("settings",{})
    if settings.get("watoomRouterDiscovery") is True:
        return False
    settings["watoomRouterDiscovery"]=True
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
    p=argparse.ArgumentParser();p.add_argument("path");a=p.parse_args()
    print("CHANGED" if migrate(a.path) else "UNCHANGED")
