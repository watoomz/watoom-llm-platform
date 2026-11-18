import sys,json,pathlib,urllib.parse,time
sys.path.insert(0,'/workspace');from api_probe import api
r=pathlib.Path(sys.argv[1]);q='?'+urllib.parse.urlencode({'location[directory]':str(r)})
for attempt in range(3):
 s=api('/api/skill'+q);skill=next((x for x in s['data'] if x['id']=='watoom-blender-asset-builder'),None)
 if skill:break
 time.sleep(1)
assert skill,'skill initialization not complete after bounded retries'
(r/'reports/canary-skill.json').write_text(json.dumps({'status':'PASS','skill':skill},indent=2))
session=api('/api/session',{'title':'Blender isolated canary validation','location':{'directory':str(r)}},'POST');(r/'reports/canary-session.json').write_text(json.dumps(session,indent=2));sid=session.get('id') or session.get('data',{}).get('id');assert sid
# Execute through the existing OpenCode session shell route. No existing session is touched.
api('/api/session/'+sid+'/shell',{'command':'python3 scripts/pipeline.py --root '+str(r)+' --resume > reports/opencode-validation.json'},'POST')
for i in range(120):
 if (r/'reports/opencode-validation.json').exists() and (r/'reports/opencode-validation.json').stat().st_size:break
 time.sleep(1)
data=json.loads((r/'reports/opencode-validation.json').read_text());assert data['stages']['QA']=='PASS' and data['stages']['ENGINE_IMPORT']=='PASS';print(json.dumps({'status':'PASS','session':sid,'skill_discovered':True,'shell_dispatch':True,'pipeline':data['result']}))
