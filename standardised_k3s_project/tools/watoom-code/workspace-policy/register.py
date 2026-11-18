#!/usr/bin/env python3
"""Register/name the native project through supported APIs; no session creation or model call."""
import argparse,pathlib,sys,json,urllib.parse
p=argparse.ArgumentParser();p.add_argument('--iac-root',required=True,type=pathlib.Path);a=p.parse_args();trusted=pathlib.Path(__file__).parent/'native';assert trusted.stat().st_uid==0 and not trusted.stat().st_mode&0o022;sys.path.insert(0,str(trusted));from maintenance_guard import Maintenance
root='/data/ai/projects/homelab/homelab-llm';out=pathlib.Path('/data/ai/artifacts/homelab-llm-20261028');out.mkdir(exist_ok=True,mode=0o700);m=Maintenance('watoom-code','watoom-code',out,True,True)
info=m.request('/api/location?location%5Bdirectory%5D='+urllib.parse.quote(root,safe=''));identity=info['project']['id'];assert info['project']['canonical']==root
projects=m.request('/api/project');project=next(x for x in projects if x['id']==identity);changed=project.get('name')!='Agent Export & LLM'
if changed:
 code="""import sys,json,urllib.request,base64
headers={'Content-Type':'application/json','Authorization':'Basic '+base64.b64encode(('opencode:'+sys.stdin.read()).encode()).decode()}
req=urllib.request.Request('http://127.0.0.1:4096/api/project/'+sys.argv[1],data=json.dumps({'name':'Agent Export & LLM'}).encode(),headers=headers,method='PATCH')
with urllib.request.urlopen(req,timeout=12) as response:print(response.status)
"""
 assert int(m.exec(code,identity,input=m.password.encode()).strip())==200
plugins=m.request('/api/plugin?location%5Bdirectory%5D='+urllib.parse.quote(root,safe=''))['data'];guard=next(x for x in plugins if x['id']=='watoom.homelab-workspace');assert guard['state']['status']=='active';result={'status':'PASS','changed':changed,'id':identity,'name':'Agent Export & LLM','directory':root,'guard':guard['state']['status']};(out/'project-registration.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
