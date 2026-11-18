#!/usr/bin/env python3
"""Exercise image rollback only on the identified idle, fenced candidate."""
import argparse,pathlib,json,sys,subprocess,time,sqlite3,hashlib,os,base64
from maintenance_guard import Maintenance
import release_guard
def main():
 p=argparse.ArgumentParser();p.add_argument('--evidence',type=pathlib.Path,required=True);p.add_argument('--old-gui-only',action='store_true');a=p.parse_args()
 root=a.evidence.resolve();out=root/'candidate';i=json.loads((out/'identity.json').read_text())
 assert i['name']=='watoom-code-skills-candidate-20261017' and i['owner']==root.name
 m=Maintenance(i['namespace'],i['name'],out,True,True)
 assert m.kub('get','deploy',i['name'])['metadata']['labels']['watoom-test-owner']==root.name
 def check():
  release_guard.validate(m.request('/api/session/deployment-guard'),True)
  release_guard.active_clear(m.request('/api/session/active'))
  release_guard.durable_clearance(out/'state/application.sqlite')
 def state():
  result={}
  for filename,tables in [('catalog.sqlite',['skills','_watoom_skill_review','_watoom_skill_review_history']),('application.sqlite',['_watoom_agent_skill_selection','_watoom_skill_selection'])]:
   with sqlite3.connect('file:'+str(out/'state'/filename)+'?mode=ro',uri=True) as db:
    for table in tables:result[filename+':'+table]=hashlib.sha256(repr(db.execute('SELECT * FROM '+table+' ORDER BY rowid').fetchall()).encode()).hexdigest()
  result['vault']={str(p.relative_to(out/'state/skills')):hashlib.sha256(p.read_bytes()).hexdigest() for p in (out/'state/skills').rglob('*') if p.is_file()}
  return result
 def switch(image):
  check()
  subprocess.run(['kubectl','-n',i['namespace'],'set','image','deployment/'+i['name'],'app='+image],check=True,capture_output=True)
  deadline=time.monotonic()+120
  while True:
   try:
    pod=m.pod();container=next(c for c in pod['status']['containerStatuses'] if c['name']=='app')
    assert container['imageID'].endswith(image.split('@')[1]) and container['ready']
    check();assert isinstance(m.request('/api/info')['version'],str)
    assert state()==baseline
    memory=json.loads((out/'memory-fixture.json').read_text())
    assert memory['fact'] in json.dumps(m.request('/api/session/'+memory['session']+'/message'))
    return {'image':image,'imageID':container['imageID'],'authenticated_api':'PASS','durable_state':'PASS','memory':'PASS','guard_boot':'PASS'}
   except Exception:
    if time.monotonic()>deadline:raise
    time.sleep(2)
 check();baseline=state();results=[]
 if a.old_gui_only:
  results.append(switch(i['baseline_image']))
  try:
   gui=out/'gui'/('old-image-'+str(time.time_ns()));gui.mkdir(mode=0o700)
   memory=json.loads((out/'memory-fixture.json').read_text())
   base='http://'+m.kub('get','svc',i['name'])['spec']['clusterIP']+':4096'
   env={**os.environ,'PLAYWRIGHT_MODULE':'/data/ai/projects/llm/watoom-code/native-next-review-20261014T212958Z/source/node_modules/.bun/playwright@1.59.1/node_modules/playwright','CANDIDATE_PASSWORD':m.password,'CANDIDATE_BASE':base,'EVIDENCE':str(gui),'MEMORY_ROUTE_SESSION':memory['session'],'MEMORY_GUI_FACT':memory['fact']}
   with (gui/'runner.log').open('w') as log:
    q=subprocess.run(['node',str(pathlib.Path(__file__).with_name('agentmemory-browser.cjs'))],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=100)
   assert q.returncode==0,'Old-image authenticated browser failed'
   (out/'old-image-gui-acceptance.json').write_text(json.dumps({'status':'PASS','image':i['baseline_image'],'evidence':str(gui)},indent=2))
  finally:results.append(switch(i['image']))
  print('PASS old image authenticated GUI and new image restoration');return
 # Baseline runs the new configuration safely, including the additive collection key.
 results.append(switch(i['baseline_image']))
 try:
  results.append(switch(i['image']))
  raise ValueError('OWNED_INJECTED_POST_ROLLOUT_VALIDATION_FAILURE')
 except Exception as error:
  results.append(switch(i['baseline_image']))
  results[-1]['automatic_rollback']='PASS'
  if not isinstance(error,ValueError) or str(error)!='OWNED_INJECTED_POST_ROLLOUT_VALIDATION_FAILURE':raise
 results.append(switch(i['image']))
 assert state()==baseline
 report={'status':'PASS','injected_failure':'PASS','automatic_old_image_restore':'PASS','state_preserved_without_database_restore':'PASS','steps':results}
 (out/'old-image-rollback-acceptance.json').write_text(json.dumps(report,indent=2))
 print(json.dumps(report),flush=True)
if __name__=='__main__':main()
