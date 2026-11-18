#!/usr/bin/env python3
"""Rebuild only the engineering toolchain; retain exact verified application binaries."""
import argparse, hashlib, json, pathlib, shutil, subprocess, urllib.request
p=argparse.ArgumentParser()
p.add_argument("--evidence",required=True,type=pathlib.Path)
p.add_argument("--runtime-image",required=True)
p.add_argument("--layer-tag",required=True)
p.add_argument("--tag",required=True)
a=p.parse_args()
out=a.evidence.resolve()
out.mkdir(exist_ok=True)
root=pathlib.Path(__file__).resolve().parent
def run(name,args):
    with (out/(name+".log")).open("w") as log:
        subprocess.run(args,stdout=log,stderr=subprocess.STDOUT,timeout=1200,check=True)
def pushed(tag):
    run(tag.split("/")[-1].split(":")[0]+"-push",["docker","push",tag])
    meta=json.loads(subprocess.check_output(["docker","image","inspect",tag]))[0]
    repo=tag.rsplit(":",1)[0]
    image=next(x for x in meta["RepoDigests"] if x.startswith(repo+"@"))
    req=urllib.request.Request("http://"+image.replace("@","/manifests/").replace(repo,repo.split("/")[0]+"/v2/"+repo.split("/",1)[1]),headers={"Accept":"application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json"})
    with urllib.request.urlopen(req,timeout=30) as response: manifest=json.load(response)
    if "manifests" in manifest:
        digest=next(x["digest"] for x in manifest["manifests"] if x.get("platform")=={"architecture":"amd64","os":"linux"})
        return repo+"@"+digest
    return image
if "@sha256:" not in a.runtime_image:raise ValueError("Immutable runtime required")
if shutil.disk_usage("/").free<8*1024**3:raise RuntimeError("Imagefs reserve below 8GiB")
run("layer-build",["docker","build","--pull=false","--memory=2g","--cpuset-cpus=0,1","-t",a.layer_tag,"-f",str(root/"Containerfile"),str(root)])
layer=pushed(a.layer_tag)
run("runtime-pull",["docker","pull",a.runtime_image])
metadata=json.loads(subprocess.check_output(["docker","image","inspect",a.runtime_image]))[0]
source=metadata["Config"]["Labels"]["org.opencontainers.image.revision"]
context=out/"context";context.mkdir(exist_ok=True)
cid=subprocess.check_output(["docker","create",a.runtime_image],text=True).strip()
try:
    for name in ["opencode","bun","godot"]:
        if (context/name).is_symlink():(context/name).unlink()
        subprocess.run(["docker","cp","-L",cid+":/usr/local/bin/"+name,str(context/name)],check=True,capture_output=True)
finally:subprocess.run(["docker","rm",cid],check=True,capture_output=True)
containerfile=root.parent/"Containerfile"
old=containerfile.read_text()
lines=old.splitlines()
lines=[("FROM "+layer if line.startswith("FROM ") else line) for line in lines]
candidate="\n".join(lines)+"\n"
(context/"Containerfile").write_text(candidate)
inputs={name:hashlib.sha256((context/name).read_bytes()).hexdigest() for name in ["opencode","bun","godot","Containerfile"]}
run("app-image-build",["docker","build","--pull=false","--network=none","--build-arg","WATOOM_SOURCE_COMMIT="+source,"-t",a.tag,"-f",str(context/"Containerfile"),str(context)])
image=pushed(a.tag)
containerfile.write_text(candidate)
result={"status":"BUILT_NOT_DEPLOYED","image":image,"layer":layer,"runtime_image":a.runtime_image,"source_commit":source,"inputs":inputs}
(out/"build.json").write_text(json.dumps(result,indent=2))
print(json.dumps(result),flush=True)
