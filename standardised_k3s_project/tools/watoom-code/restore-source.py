#!/usr/bin/env python3
"""Restore exact maintained application commits onto the pinned public release, into a new checkout."""
import argparse,hashlib,json,pathlib,subprocess
p=argparse.ArgumentParser();p.add_argument("--destination",required=True,type=pathlib.Path);p.add_argument("--metadata",type=pathlib.Path);a=p.parse_args()
root=pathlib.Path(__file__).with_name("source");metadata_path=a.metadata.resolve() if a.metadata else root/"source.json";metadata=json.loads(metadata_path.read_text());bundle_name=metadata.get("bundle","watoom-code.bundle");assert pathlib.Path(bundle_name).name==bundle_name;bundle=metadata_path.parent/bundle_name
assert hashlib.sha256(bundle.read_bytes()).hexdigest()==metadata["bundle_sha256"]
if a.destination.exists():raise RuntimeError("Destination must not exist; existing checkouts are never reset")
a.destination.mkdir(parents=True)
def git(*args):return subprocess.check_output(["git","-C",str(a.destination),*args],stderr=subprocess.PIPE,text=True).strip()
git("init");git("remote","add","origin",metadata["repository"])
git("fetch","--depth=1","origin","refs/tags/"+metadata["base_tag"])
assert git("rev-parse","FETCH_HEAD")==metadata["base_commit"],"Public base tag changed; stop for review"
git("bundle","verify",str(bundle.resolve()))
branch=metadata.get("application_branch","main")
assert branch=="main" or branch.startswith("codex/")
git("fetch",str(bundle.resolve()),"refs/heads/"+branch+":refs/heads/"+branch)
git("checkout",branch)
assert git("rev-parse","HEAD")==metadata["application_commit"]
assert git("rev-parse","HEAD^{tree}")==metadata["tree"]
assert git("status","--porcelain")==""
print("PASS exact committed application source restored: "+metadata["application_commit"])
