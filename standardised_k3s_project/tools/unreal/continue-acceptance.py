#!/usr/bin/env python3
"""Run the prepared isolated C++ fixture and runtime commandlet, without a full engine rebuild."""
import argparse,json,pathlib,subprocess,fcntl
ap=argparse.ArgumentParser()
ap.add_argument("--evidence",required=True,type=pathlib.Path)
a=ap.parse_args();r=a.evidence.resolve()
lock=(r/"acceptance.lock").open("a")
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
for phase in ["compile","commandlet"]:
 result=subprocess.run(["python3",str(pathlib.Path(__file__).with_name("recover-editor.py")),"--evidence",str(r),"--acceptance",phase,"--run"])
 detail=r/("acceptance-"+phase+"-status.json")
 status=json.loads(detail.read_text()) if detail.exists() else {}
 if result.returncode or status.get("status")!="PASS":
  (r/"acceptance-status.json").write_text(json.dumps({"status":"BLOCKED","phase":phase,"detail":str(detail)},indent=2))
  raise SystemExit(result.returncode or 2)
(r/"acceptance-status.json").write_text(json.dumps({"status":"CPP_COMMANDLET_PASS_RENDER_CONVERSION_PENDING"},indent=2))
