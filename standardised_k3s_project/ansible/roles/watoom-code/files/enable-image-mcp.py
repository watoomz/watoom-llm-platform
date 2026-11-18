#!/usr/bin/env python3
"""Maintain only the scoped image MCP entry without replacing user settings."""
import argparse,json,os,pathlib,tempfile
def migrate(path,url):
    path=pathlib.Path(path)
    data=json.loads(path.read_text())
    if not url.startswith('http://model-manager.') or not url.endswith(':8787/model-manager/mcp'):
        raise ValueError('Expected internal Model Manager service URL')
    servers=data.setdefault('mcp',{}).setdefault('servers',{})
    entry={"type":"remote","url":url,"headers":{"Authorization":"Bearer {file:/config/watoom-tools/image-credentials/token}"},"oauth":False,"protocol":"legacy","codemode":False,"timeout":{"catalog":30000,"execution":30000}}
    if servers.get('watoom-images')==entry:return False
    servers['watoom-images']=entry
    mode=path.stat().st_mode & 0o777
    owner=path.stat()
    fd,name=tempfile.mkstemp(dir=path.parent,prefix=".image-config-")
    try:
        with os.fdopen(fd,"w") as stream:
            json.dump(data,stream,indent=2);stream.write("\n");stream.flush();os.fsync(stream.fileno())
        os.chmod(name,mode);os.chown(name,owner.st_uid,owner.st_gid)
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)
    return True
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("path");p.add_argument("url");a=p.parse_args()
    print("CHANGED" if migrate(a.path,a.url) else "UNCHANGED")
