#!/usr/bin/env python3
"""Targeted read-only release capability and execution status audit. No secret output."""
import subprocess,json,base64,urllib.request,urllib.error
ns="watoom-code"
def kub(*args):return json.loads(subprocess.check_output(["kubectl","-n",ns,*args,"-o","json"],timeout=30))
secret=kub("get","secret","watoom-code-auth")["data"]
auth="Basic "+base64.b64encode(b"opencode:"+base64.b64decode(secret["OPENCODE_PASSWORD"])).decode()
ip=kub("get","svc","watoom-code")["spec"]["clusterIP"]
result={}
for name,path in [("active","/api/session/active"),("guard","/api/session/deployment-guard"),("commands","/api/command"),("info","/api/info")]:
    try:
        with urllib.request.urlopen(urllib.request.Request("http://"+ip+":4096"+path,headers={"Authorization":auth}),timeout=15) as response:result[name]=json.load(response)
    except urllib.error.HTTPError as error:result[name]={"http_status":error.code}
result["image"]=kub("get","deploy","watoom-code")["spec"]["template"]["spec"]["containers"][0]["image"]
print(json.dumps(result,indent=2))
