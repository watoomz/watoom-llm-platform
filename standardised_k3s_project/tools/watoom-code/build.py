#!/usr/bin/env python3
"""Build WatooM Code from maintained source and a pinned IaC toolchain.
No deployment or network changes. All mutable build paths are explicit.
"""
import argparse,hashlib,json,os,pathlib,shutil,subprocess,urllib.request
import bounded_process
def source_environment(source,base):
    """Carry exact-repository trust into Bun's own Git subprocesses."""
    result=dict(base)
    count=int(result.get("GIT_CONFIG_COUNT","0"))
    if not 0<=count<=32:raise ValueError("Build Git environment count exceeds budget")
    result.update({"GIT_CONFIG_COUNT":str(count+1),"GIT_CONFIG_KEY_"+str(count):"safe.directory","GIT_CONFIG_VALUE_"+str(count):str(source)})
    return result
def main():
    p=argparse.ArgumentParser()
    for name in ("source","bun","godot","output"):p.add_argument("--"+name,required=True,type=pathlib.Path)
    p.add_argument("--tag",required=True)
    p.add_argument("--engine",choices=["docker","buildah"],default="docker")
    p.add_argument("--buildah",type=pathlib.Path)
    a=p.parse_args()
    source=a.source.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    # OpenCode v2.2.5+ selects the build target from OPENCODE_TARGET and ignores --target; older sources ignore it.
    env=source_environment(source,dict(os.environ,TMPDIR=str(out/"tmp"),BUN_INSTALL_CACHE_DIR=str(out/"bun-cache"),OPENCODE_TARGET="linux-x64-baseline"))
    pathlib.Path(env["TMPDIR"]).mkdir();pathlib.Path(env["BUN_INSTALL_CACHE_DIR"]).mkdir()
    def run(name,args,cwd=None,timeout=3600):
        with (out/(name+".log")).open("w") as log:
            r=bounded_process.run([str(x) for x in args],cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
        if r.returncode:raise RuntimeError(name+" failed; see private build log")
    def digest(path):
        with path.open("rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()
    if digest(a.godot)!="8d106cbe6144c2dc7e881d61d2429c1a8a76e6b22ef48bd5e48dcf934953f71e":
        raise ValueError("Godot 4.7.2 input does not match verified release")
    def git(*args):return subprocess.check_output(["git","-c","safe.directory="+str(source),"-C",str(source),*args])
    source_commit=git("rev-parse","HEAD").decode().strip()
    (out/"source-head.txt").write_text(source_commit+"\n")
    (out/"source-status.txt").write_bytes(git("status","--porcelain=v1","-uall"))
    (out/"source.patch").write_bytes(git("diff","--binary","HEAD"))
    untracked=git("ls-files","--others","--exclude-standard","-z").decode().split("\0")
    import tarfile
    with tarfile.open(out/"source-untracked.tar.gz","w:gz") as archive:
        for path in filter(None,untracked):archive.add(source/path,arcname=path)
    if (out/"source-status.txt").read_bytes().strip():raise ValueError("Commit reviewed application source before building an immutable release")
    run("router-tests",[a.bun,"test","test/plugin/watoom-router.test.ts"],source/"packages/core",240)
    run("selector-tests",[a.bun,"test","src/providers/models/agent.test.ts","src/providers/models/visibility.test.ts"],source/"packages/app",240)
    run("application-build",[a.bun,"script/build.ts","--target=opencode-linux-x64-baseline","--skip-install","--outdir="+str(out/"dist")],source/"packages/cli")
    context=out/"context";context.mkdir()
    binary=out/"dist/cli-linux-x64-baseline/bin/opencode"
    for path,name in [(binary,"opencode"),(a.bun,"bun"),(a.godot,"godot")]:shutil.copy2(path,context/name)
    shutil.copy2(pathlib.Path(__file__).with_name("Containerfile"),context/"Containerfile")
    manifest={name:digest(context/name) for name in ("opencode","bun","godot","Containerfile")}
    (out/"inputs.json").write_text(json.dumps(manifest,indent=2))
    if a.engine=="buildah":
        if not a.buildah:raise ValueError("--buildah is required for the buildah engine")
        run("image-build",[a.buildah,"bud","--tls-verify=false","--arch","amd64","--build-arg","WATOOM_SOURCE_COMMIT="+source_commit,"-t",a.tag,"-f",context/"Containerfile",context])
        run("image-push",[a.buildah,"push","--tls-verify=false","--digestfile="+str(out/"push.digest"),a.tag,"docker://"+a.tag])
    else:
        if shutil.disk_usage("/").free<8*1024**3:raise RuntimeError("Root imagefs headroom below 8 GiB")
        base=next(line.split()[1] for line in (context/"Containerfile").read_text().splitlines() if line.startswith("FROM "))
        if "@sha256:" not in base:raise ValueError("Pinned toolchain required")
        if subprocess.run(["docker","image","inspect",base],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
            run("base-pull",["docker","pull",base])
        run("base-image",["docker","image","inspect",base])
        run("image-build",["docker","build","--pull=false","--network=none","--build-arg","WATOOM_SOURCE_COMMIT="+source_commit,"-t",a.tag,"-f",context/"Containerfile",context])
        run("image-push",["docker","push",a.tag])
        metadata=json.loads(subprocess.check_output(["docker","image","inspect",a.tag]))
        digests=[x.split("@")[1] for x in metadata[0]["RepoDigests"] if x.startswith(a.tag.rsplit(":",1)[0]+"@")]
        if len(digests)!=1:raise RuntimeError("Pushed app digest is ambiguous")
        index=digests[0]
        request=urllib.request.Request("http://127.0.0.1:5000/v2/watoom-code/manifests/"+index,headers={"Accept":"application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.manifest.v1+json"})
        with urllib.request.urlopen(request,timeout=10) as response:metadata=json.load(response)
        if "manifests" in metadata:
            candidates=[x["digest"] for x in metadata["manifests"] if x.get("platform")=={"architecture":"amd64","os":"linux"}]
            if len(candidates)!=1:raise RuntimeError("Linux amd64 manifest is ambiguous")
            (out/"index.digest").write_text(index+"\n")
            index=candidates[0]
        (out/"push.digest").write_text(index+"\n")
    print("PASS digest="+(out/"push.digest").read_text().strip())
if __name__=="__main__":main()
