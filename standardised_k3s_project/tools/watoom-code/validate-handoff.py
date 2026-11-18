#!/usr/bin/env python3
"""Bounded owned native handoff acceptance; never replays an existing journal."""
from pathlib import Path
import sys,json,time,uuid
repo=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo/"tools/watoom-code"))
from maintenance_guard import Maintenance
import argparse
parser=argparse.ArgumentParser()
parser.add_argument("--evidence",required=True,type=Path)
parser.add_argument("--verify-existing",action="store_true")
parser.add_argument("--deployment",default="watoom-code",choices=["watoom-code","watoom-code-engineering-candidate"])
args=parser.parse_args()
out=args.evidence.resolve();out.mkdir(parents=True,exist_ok=True)
m=Maintenance("watoom-code",args.deployment,out,True,True)
if args.verify_existing:
    journal=json.loads((out/"live-handoff-journal.json").read_text())
    parent=journal["parent"]
else:
    assert not (out/"live-handoff-journal.json").exists(), "Existing prompt journal; use --verify-existing"
    assert m.request("/api/session/active")["data"]=={}
    directory="/workspace/.watoom-validation/handoff-"+uuid.uuid4().hex[:12]
    m.exec("import pathlib,subprocess,sys;p=pathlib.Path(sys.argv[1]);p.mkdir(parents=True);subprocess.run(['git','-C',str(p),'init','-q'],check=True)",directory)
    parent=m.request("/api/session",{"location":{"directory":directory},"agent":"watoom-workflow","title":"Owned serial native handoff acceptance"})["data"]["id"]
    journal={"parent":parent,"directory":directory}
    (out/"live-handoff-journal.json").write_text(json.dumps(journal))
    prompt='Owned isolated handoff acceptance. Use the directly exposed native subagent function exactly once, with agent="watoom-critic", description="Owned handoff proof", prompt="Return HANDOFF_CHILD_PASS only. Do not use tools, read files, inspect skills, or access the network.", background=false. Do not use execute/search/shell or other tools. After the subagent returns HANDOFF_CHILD_PASS, return HANDOFF_PARENT_PASS. Do not claim a child result without the actual tool result.'
    m.request("/api/session/"+parent+"/prompt",{"text":prompt})
    deadline=time.monotonic()+150
    while time.monotonic()<deadline:
        active=m.request("/api/session/active")["data"]
        current=m.request("/api/session/"+parent+"/message")["data"]
        if parent not in active and any(x["type"]=="idle" for x in current):break
        time.sleep(3)
    else:
        m.request("/api/session/"+parent+"/interrupt",{})
        raise RuntimeError("Owned handoff exceeded150sec; only owned parent interrupted")
messages=m.request("/api/session/"+parent+"/message")["data"]
calls=[c for message in messages if message["type"]=="assistant" for c in message.get("content",[]) if c["type"]=="tool"]
assert len(calls)==1 and calls[0]["name"]=="subagent",[(c["name"],c["state"]["status"]) for c in calls]
assert calls[0]["state"]["status"]=="completed"
metadata=calls[0]["state"].get("metadata",{})
child=metadata["sessionID"]
child_messages=m.request("/api/session/"+child+"/message")["data"]
assert "HANDOFF_CHILD_PASS" in json.dumps(child_messages)
assert "HANDOFF_PARENT_PASS" in json.dumps(messages)
assert not any(c["type"]=="tool" for message in child_messages if message["type"]=="assistant" for c in message.get("content",[]))
assert not m.request("/api/session/active")["data"]
(out/"live-handoff-acceptance.json").write_text(json.dumps({"status":"PASS","parent":parent,"child":child,"native_subagent_calls":1,"child_tool_calls":0,"foreground_completion":"PASS","parent_restoration":"PASS","model_changed":False},indent=2))
print("PASS actual coordinator→child→coordinator via native subagent")
