#!/usr/bin/env python3
"""Apply only proven existing-Skill revisions at idle; never edit an active Skill file."""
import argparse,pathlib,json,sqlite3,sys,time,os,secrets,hashlib,fcntl,subprocess
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
from maintenance_guard import Maintenance
from release_guard import acquire,release,active_clear,durable_clearance,snapshot_database
from recover import atomic,published_health
from mcp_quiescence import quiesce,restore
from idle_streams import drain as drain_idle_streams
from native_readiness import wait as wait_native_skills

def qualified(state,revision):
 r=state['revisions'][revision];k=state['skills'][r['skill']];report=state.get('comparisons',{}).get(revision,{})
 if report.get('measurementOrigin')!='observed':return False
 if r.get('state')!='evaluated' or not k.get('baselineTests') or k.get('sourceChanged') or r.get('previous')!=(k.get('active') or k.get('baseline')):return False
 # Repeated paired measurements must come from an independent registered suite,
 # not one noisy latency sample or a byte count masquerading as token savings.
 protocol=report.get('measurementProtocol',{})
 receipts=protocol.get('verifierReceipts',[])
 if not isinstance(receipts,list) or len(receipts)<3 or len(set(receipts))!=len(receipts):return False
 material=False
 for case in report.get('cases',[]):
  original=case.get('original',{});candidate=case.get('candidate',{})
  if original.get('correctness') is False and candidate.get('correctness') is True:material=True
  if original.get('safety') is False and candidate.get('safety') is True:material=True
  for metric,fraction in [('tokens',0.95),('latencyMs',0.9),('repeatedCommands',None),('failedAttempts',None)]:
   before=original.get(metric);after=candidate.get(metric)
   if isinstance(before,(int,float)) and isinstance(after,(int,float)) and before>0 and (after<before if fraction is None else after<=before*fraction):material=True
 return bool(material and protocol.get('domainRepresentative') is True and protocol.get('registeredSuite') and protocol.get('pairedRepetitions',0)>=3 and protocol.get('sameEnvironment') is True and protocol.get('regressionChecks') is True)

def verified_comparison(root,state,revision):
 # App-owned KV is telemetry, never independent promotion authority.
 try:
  from evaluate_existing import protected,sha
  journal=json.loads(protected(root/'existing-skills/evaluator-journal.json').read_text());scope_hash=hashlib.sha256(json.dumps(state['scope'],separators=(',',':')).encode()).hexdigest()
  row=next(v for v in journal.values() if v.get('status')=='PASS' and v.get('revision')==revision and v.get('scope_hash')==scope_hash)
  report=protected(row['verified_report'])
  if not report.resolve().is_relative_to((root/'existing-skills/evaluations').resolve()) or sha(report)!=row['verified_report_sha256']:return False
  value=json.loads(report.read_text());r=state['revisions'][revision]
  if value.get('scope')!=state['scope'] or value.get('revision')!=revision or value.get('comparison')!=state.get('comparisons',{}).get(revision):return False
  if value['comparison']['candidateHash']!=r['sha256'] or value['comparison']['baselineHash']!=state['revisions'][r['previous']]['sha256']:return False
  registry=json.loads(protected(root/'existing-skills/evaluator-registry.json').read_text())['suites'][r['skill']]
  return registry['sha256']==value['comparison']['measurementProtocol']['registeredSuiteSHA256'] and registry.get('domainRepresentative') is True
 except (OSError,ValueError,KeyError,StopIteration,TypeError):return False

def main():
 p=argparse.ArgumentParser();p.add_argument('--evidence',required=True,type=pathlib.Path);p.add_argument('--dry-run',action='store_true');a=p.parse_args();root=a.evidence.resolve();source=pathlib.Path(__file__).resolve().parent;repo=source.parents[2]
 if not str(root).startswith('/data/ai/helper-scripts/watoom-self-learning-'):raise ValueError('Dedicated evidence root required')
 mainstate=root/'production/recovery-state.json'
 if not mainstate.exists() or json.loads(mainstate.read_text()).get('phase')!='COMPLETE':print('NO_ACTION: verified production release not complete');return
 with (root/'runner.lock').open('a') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:print('NO_ACTION: deployment runner busy');return
  pointer=root/'production/optimisation-current.json'
  if pointer.exists():
   prior_checkpoint=pathlib.Path(json.loads(pointer.read_text())['checkpoint']);prior_state=json.loads(prior_checkpoint.read_text())
   if prior_state['phase'] not in ['COMPLETE','ROLLED_BACK']:print('NO_ACTION: independent restoration must settle '+prior_state['phase']);return
  plan=json.loads((root/'production/plan.json').read_text());database=pathlib.Path('/data/ai/watoom-code/application.sqlite')
  with sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True) as db:states=[json.loads(v) for v, in db.execute('select value from kv where key like ?',('%optimisation/v1/%',))]
  from evaluate_existing import evaluate_pending
  if not a.dry_run and not any(k.get('pendingRollback') for s in states for k in s['skills'].values()):
   evaluation=evaluate_pending(root,states,plan,database)
   if evaluation['status'] not in ['NO_UNEVALUATED_REGISTERED_CANDIDATE','NO_REGISTERED_TASK_SUITES']:print(json.dumps({'evaluation':evaluation}));return
  historyfile=root/'production/optimisation-releases.json';history=json.loads(historyfile.read_text()) if historyfile.exists() else {}
  history_source=root/'existing-skills/baseline.json';historical={k['id']:k.get('priority',0) for k in json.loads(history_source.read_text()).get('skills',[])} if history_source.exists() else {}
  choices=[]
  for s in states:
   for k in s['skills'].values():
    if k.get('pendingRollback') and k.get('active') in history:choices.append((float('inf'),s,k['active'],'rollback'))
   for rid,r in s['revisions'].items():
    if qualified(s,rid) and verified_comparison(root,s,rid):
     k=s['skills'][r['skill']];m=k.get('metrics',{});priority=historical.get(k['id'],0)+m.get('loads',0)+5*m.get('failures',0)+2*m.get('repeats',0)+k.get('measuredSessionTokens',0)/1000;choices.append((priority,s,rid,'select'))
  if not choices:print('NO_ACTION: no independently proven existing-Skill revision or verified regression');return
  _,state,rid,action=sorted(choices,key=lambda x:(-x[0],x[2]))[0];r=state['revisions'][rid];scope=state['scope']
  if a.dry_run:print(json.dumps({'action':action,'revision':rid,'skill':r['skill'],'requires':'idle maintenance fence, native gate, immutable configuration rollout, endpoint verification','mutations':False}));return
  if os.geteuid()!=0:raise PermissionError('Reviewed deployment controller requires root')
  out=root/'production'/('optimisation-'+str(time.time_ns()));out.mkdir(mode=0o700)
  m=Maintenance(plan['namespace'],plan['deployment'],out,True,True);active_clear(m.request('/api/session/active'));durable_clearance(database)
  live=m.kub('get','deploy',plan['deployment'])
  if live['metadata']['uid']!=plan['deployment_uid'] or live['spec']['template']['spec']['containers'][0]['image']!=plan['pinned_image']:raise RuntimeError('Verified deployment identity changed')
  config=pathlib.Path(plan['config']);original=json.loads(config.read_text());new=json.loads(config.read_text());plugin=next(x for x in new['plugins'] if isinstance(x,dict) and x.get('package')=='/config/watoom-tools/'+pathlib.Path(plan['installed_package']).name)
  current=plugin['options'].get('optimisationRevisions',[])
  previous={x for x in current if state['revisions'].get(x,{}).get('skill')==r['skill']}
  if action=='select':plugin['options']['optimisationRevisions']=[x for x in current if x not in previous]+[rid]
  else:
   known=history[rid];new=json.loads(pathlib.Path(known['baseline_config']).read_text())
  baseline={'apiVersion':'apps/v1','kind':'Deployment','metadata':{'name':plan['deployment'],'namespace':plan['namespace'],'labels':live['metadata'].get('labels',{})},'spec':live['spec']}
  prior=out/'original-config.json';atomic(prior,original);manifest=out/'original-deployment.json';atomic(manifest,baseline)
  candidate=out/'candidate-config.json';atomic(candidate,new);sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
  target=json.loads(json.dumps(baseline));target['spec']['template']['metadata'].setdefault('annotations',{})['watoom-existing-skill-revision']=rid+'-'+action;target['spec']['template']['metadata']['annotations']['watoom-self-learning-config-sha256']=sha(candidate);targetfile=out/'candidate-deployment.json';atomic(targetfile,target)
  recovery_baseline=manifest;recovery_config=prior
  if action=='rollback':recovery_baseline=pathlib.Path(history[rid]['baseline_deployment']);recovery_config=pathlib.Path(history[rid]['baseline_config'])
  checkpoint=out/'recovery-state.json';s={**plan,'phase':'CUTOVER_READY','production_approved':True,'baseline_deployment':str(recovery_baseline),'baseline_deployment_sha256':sha(recovery_baseline),'baseline_config':str(recovery_config),'baseline_config_sha256':sha(recovery_config),'candidate_config_sha256':sha(candidate),'validation_config_sha256':sha(config),'external_fence':False,'grace_until':time.time()+600,'health_failures':0,'owned_sessions':[],'recovery_nonce':secrets.token_hex(16),'optimisation':{'revision':rid,'action':action}};atomic(checkpoint,s);atomic(pointer,{'checkpoint':str(checkpoint)})
  if action=='select':history[rid]={'baseline_config':str(prior),'baseline_deployment':str(manifest),'checkpoint':str(checkpoint),'time':time.time()};atomic(historyfile,history)
  def update(**values):
   with checkpoint.with_suffix('.lock').open('a') as guard:fcntl.flock(guard,fcntl.LOCK_EX);v=json.loads(checkpoint.read_text());v.update(values);atomic(checkpoint,v)
  def ansible(play,values):
   env={**os.environ,'ANSIBLE_CONFIG':str(repo/'ansible/ansible.cfg'),'ANSIBLE_ROLES_PATH':str(repo/'ansible/roles')};log=out/(play+'.log')
   with log.open('w') as stream:result=subprocess.run(['ansible-playbook','-i','inventories/homelab/hosts.yml','playbooks/'+play+'.yml','-c','local','-e',json.dumps(values)],cwd=repo/'ansible',env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=900)
   os.chmod(log,0o600)
   if result.returncode:raise RuntimeError('Deployment failed; inspect '+str(log))
  ansible('watoom-code-self-learning-controller',{'watoom_learning_root':str(root/'production'),'watoom_learning_controller_script':plan['controller_script'],'watoom_learning_recovery_checkpoint':str(checkpoint)})
  try:
   update(phase='CUTOVER_STARTED',external_fence=True,drain_started=time.time(),draining_until=time.time()+90);m.begin()
   acquire(lambda p:m.request(p),lambda p,b:m.request(p,b),lambda owner:update(owner=owner),lambda:durable_clearance(database))
   current_state=json.loads(checkpoint.read_text());quiesce(m,current_state,lambda value:update(**{k:v for k,v in value.items() if k.startswith('mcp_')}));m.pause_access();drain_idle_streams(m,lambda:durable_clearance(database),lambda value:atomic(out/'idle-stream-drain.json',value));update(draining_until=0)
   snapshot_database(database,out/'application.sqlite')
   request=secrets.token_hex(16);command={'kind':'existing-skill-'+action,'id':rid if action=='select' else r['skill'],'scope':scope,'request':request};file=pathlib.Path(plan['evaluations'])/('existing-'+request+'.json');atomic(file,command);os.chmod(file,0o644)
   deadline=time.monotonic()+120
   while True:
    with sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True) as db:values=[json.loads(v) for v, in db.execute('select value from kv where key like ?',('%learning/v1/%',))]
    operation=next((v.get('operations',{}).get(request) for v in values if request in v.get('operations',{})),None)
    if operation:
     if operation['result']!='PASS':raise RuntimeError('Native revision operation rejected: '+operation.get('reason',''))
     break
    if time.monotonic()>deadline:raise RuntimeError('Native revision operation did not settle')
    time.sleep(1)
   ansible('watoom-code-self-learning-cutover',{'watoom_learning_production_approved':True,'watoom_learning_evidence':str(root),'watoom_learning_source_package':plan['source_package'],'watoom_learning_installed_package':plan['installed_package'],'watoom_learning_candidate_config':str(candidate),'watoom_learning_candidate_deployment':str(targetfile)})
   import urllib.parse
   _,registered,_=wait_native_skills(m,plan['baseline_skills'],scope['repository']);actual=next(k for k in registered if k['id']==r['skill'])
   expected=r['sha256'] if action=='select' else state['revisions'][state['skills'][r['skill']]['pendingRollback']]['sha256']
   if hashlib.sha256(actual['content'].encode()).hexdigest()!=expected:raise RuntimeError('Native Skill revision activation failed')
   if not set(plan['baseline_skills'])<={k['id'] for k in registered}:raise RuntimeError('Native Skill coverage reduced')
   restore(m,json.loads(checkpoint.read_text()),lambda value:update(**{k:v for k,v in value.items() if k.startswith('mcp_')}))
   update(phase='PRODUCTION_VALIDATED');owner=json.loads(checkpoint.read_text())['owner'];release(lambda p:m.request(p),lambda p,b:m.request(p,b),owner);m.release();update(external_fence=False)
   health=published_health(m);update(phase='COMPLETE',production_validated=True,published_service=health)
   if action=='select':history[rid]={'baseline_config':str(prior),'baseline_deployment':str(manifest),'checkpoint':str(checkpoint),'time':time.time()};atomic(historyfile,history)
   print(json.dumps({'status':'PASS','action':action,'revision':rid,'idle_rollout':True,'checkpoint':str(checkpoint)}))
  except Exception as error:update(phase='CUTOVER_FAILED',critical_failure=str(error)[:400],grace_until=0);raise
if __name__=='__main__':main()
