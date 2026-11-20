#!/usr/bin/env python3
"""Exercise the actual isolated WatooM runtime via its authenticated native API."""

import pathlib, subprocess, json, time, os, argparse

p = argparse.ArgumentParser()
p.add_argument("--evidence", required=True, type=pathlib.Path)
p.add_argument("--namespace", required=True)
p.add_argument("--sessions", type=int, default=3)
a = p.parse_args()
if not a.namespace.startswith("watoom-code-learning-"):
    raise ValueError("Isolated namespace required")
root = a.evidence
out = root / "native-tests"
out.mkdir(exist_ok=True)
code = """import os,urllib.request,base64,json,sys
v=json.load(sys.stdin);h={'Authorization':'Basic '+base64.b64encode(('opencode:'+os.environ['OPENCODE_PASSWORD']).encode()).decode(),'Content-Type':'application/json'}
r=urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:4096'+v['path'],headers=h,data=json.dumps(v['body']).encode() if v.get('body') is not None else None),timeout=15)
sys.stdout.buffer.write(r.read())
"""


def api(path, body=None):
    r = subprocess.run(
        ["kubectl", "-n", a.namespace, "exec", "-i", "deploy/learning-app", "--", "python3", "-c", code],
        input=json.dumps({"path": path, "body": body}).encode(),
        capture_output=True,
        timeout=30,
    )
    if r.returncode:
        raise RuntimeError(r.stderr.decode()[-1500:])
    return json.loads(r.stdout)


results = []
for i in range(a.sessions):
    start = time.monotonic()
    session = api(
        "/api/session",
        {
            "title": "Native learning fixture " + str(time.time_ns()),
            "agent": "learning-fixture",
            "location": {"directory": "/workspace"},
        },
    )["data"]
    sid = session["id"]
    api(
        "/api/session/" + sid + "/prompt",
        {"text": "Sort fixture development data and verify persisted output.", "delivery": "steer"},
    )
    deadline = time.monotonic() + 40
    while True:
        active = api("/api/session/active")["data"]
        if sid not in active:
            break
        if time.monotonic() > deadline:
            raise RuntimeError("Fixture session did not settle: " + sid)
        time.sleep(0.5)
    info = api("/api/session/" + sid)
    results.append({"session": sid, "seconds": time.monotonic() - start, "info": info})
    (out / "sessions.json").write_text(json.dumps(results, indent=2))
    print(json.dumps({"session": sid, "seconds": results[-1]["seconds"]}), flush=True)
print("NATIVE_SESSIONS_COMPLETED=" + str(len(results)))
