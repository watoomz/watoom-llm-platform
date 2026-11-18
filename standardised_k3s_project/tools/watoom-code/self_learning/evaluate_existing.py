#!/usr/bin/env python3
"""Run one protected registered CPU task suite against original and candidate data.
Unknown Skills remain explicitly untested. Suites are operator-reviewed code;
models cannot register, modify or execute evaluator programs.
"""
import pathlib,json,hashlib,secrets,subprocess,os,time,sqlite3,statistics
from recover import atomic

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def protected(path):
 path=pathlib.Path(path);st=path.lstat()
 if path.is_symlink() or st.st_uid!=0 or st.st_mode&0o022:raise PermissionError('Root-owned evaluator input required')
 return path

def validate_report(report,suite,baseline_hash,candidate_hash):
 baseline=report['baseline'];comparison=report['comparison']
 if baseline['hash']!=baseline_hash or comparison['baselineHash']!=baseline_hash or comparison['candidateHash']!=candidate_hash:raise ValueError('Replay version identity mismatch')
 expected=sorted(suite['caseIDs'])
 if not expected or len(expected)!=len(set(expected)) or sorted(c['id'] for c in baseline['cases'])!=expected or sorted(c['id'] for c in comparison['cases'])!=expected:raise ValueError('Registered representative/regression cases not covered')
 receipts=[]
 for case in comparison['cases']:
  for name in ['original','candidate']:
   arm=case[name];runs=arm.get('runs',[])
   if len(runs)<3:raise ValueError('Three paired repetitions required')
   for run in runs:
    if run.get('correctness') is not arm.get('correctness') or run.get('safety') is not arm.get('safety') or (name=='candidate' and (run.get('correctness') is not True or run.get('safety') is not True)) or not run.get('receipt') or not set(arm['coverage'])<=set(run.get('coverage',[])):raise ValueError('A replay failed correctness, safety or coverage')
    receipts.append(run['receipt'])
   for metric in ['tokens','latencyMs','repeatedCommands','failedAttempts']:
    if arm.get(metric) is None:continue
    values=[run.get(metric) for run in runs]
    if any(not isinstance(v,(int,float)) or isinstance(v,bool) or v<0 for v in values):raise ValueError('Missing or invalid replay measurement')
    if statistics.median(values)!=arm[metric]:raise ValueError('Aggregate measurement does not match replay median')
 if len(set(receipts))!=len(receipts):raise ValueError('Duplicate independent replay receipts')
 for case in comparison['cases']:
  for name in ['original','candidate']:case[name]['receipt']=hashlib.sha256(json.dumps([run['receipt'] for run in case[name]['runs']]).encode()).hexdigest()
 comparison['measurementOrigin']='observed'
 comparison['measurementProtocol']={'registeredSuite':suite['id'],'registeredSuiteSHA256':suite['sha256'],'pairedRepetitions':3,'sameEnvironment':True,'regressionChecks':True,'verifierReceipts':receipts,'domainRepresentative':suite.get('domainRepresentative',False)}
 return baseline,comparison

def evaluate_pending(root,states,plan,database):
 registry=root/'existing-skills/evaluator-registry.json'
 if not registry.exists():return {'status':'NO_REGISTERED_TASK_SUITES','existingSkillsUntested':sum(not k.get('baselineTests') for s in states for k in s['skills'].values())}
 historyfile=root/'existing-skills/baseline.json';historical={k['id']:k.get('priority',0) for k in json.loads(historyfile.read_text()).get('skills',[])} if historyfile.exists() else {}
 suites=json.loads(protected(registry).read_text())['suites'];journalfile=root/'existing-skills/evaluator-journal.json';journal=json.loads(journalfile.read_text()) if journalfile.exists() else {}
 skipped=[];pending_domain=set();pending_replays=set()
 for state in states:
  if plan.get('learning_agent') and state.get('scope',{}).get('agent')!=plan['learning_agent']:continue
  for revision in sorted(state['revisions'].values(),key=lambda r:-(historical.get(r['skill'],0)+state['skills'][r['skill']].get('measuredSessionTokens',0)/1000)):
   suite=suites.get(revision['skill'])
   skill=state['skills'][revision['skill']]
   if suite and suite.get('domainRepresentative') is not True:
    pending_domain.add(revision['skill']);continue
   if revision['state']!='candidate' or not suite or revision.get('previous')!=(skill.get('active') or skill.get('baseline')):continue
   if suite.get('evaluationMode')=='observed-model-planning':
    expected=suite.get('replayHashes',{})
    previous=state['revisions'].get(revision.get('previous'),{})
    if expected.get('baseline')!=previous.get('sha256') or expected.get('candidate')!=revision.get('sha256'):
     pending_replays.add(revision['skill']);continue
   # Project plugin instances are lazy. Warm this exact native scope before
   # delivering evaluator files; an inactive project has no running watcher.
   from maintenance_guard import Maintenance
   import urllib.parse
   if not plan.get('namespace') or not plan.get('deployment'):return {'status':'SCOPE_ENDPOINT_REQUIRED'}
   maintenance=Maintenance(plan['namespace'],plan['deployment'],root,True,True)
   registered=maintenance.request('/api/skill?'+urllib.parse.urlencode({'directory':state['scope']['repository']}))['data']
   visible=next((k for k in registered if k['id']==revision['skill']),None)
   if not visible:
    skipped.append({'status':'SKIPPED_STALE_SCOPE','revision':revision['id']});continue
   visible_hash=hashlib.sha256(visible['content'].encode()).hexdigest();scope_hash=hashlib.sha256(json.dumps(state['scope'],separators=(',',':')).encode()).hexdigest();deadline=time.monotonic()+30
   while True:
    with sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True) as db:row=db.execute('select value from kv where key like ?',('%optimisation/v1/'+scope_hash,)).fetchone()
    fresh=json.loads(row[0]) if row else None;current=fresh.get('skills',{}).get(revision['skill']) if fresh else None
    hashes=[current.get('sha256')] if current else []
    if current and current.get('active') in fresh['revisions']:hashes.append(fresh['revisions'][current['active']]['sha256'])
    if visible_hash in hashes:break
    if time.monotonic()>deadline:
     skipped.append({'status':'SKIPPED_STALE_SCOPE','revision':revision['id']});break
    time.sleep(.2)
   if visible_hash not in hashes:continue
   state=fresh;revision=state['revisions'].get(revision['id']);skill=state['skills'][revision['skill']]
   if revision.get('previous')!=(skill.get('active') or skill.get('baseline')):
    skipped.append({'status':'SKIPPED_STALE_SOURCE','revision':revision['id']});continue
   script=protected(suite['script']);registered_root=(root/'existing-skills/suites').resolve()
   if not script.resolve().is_relative_to(registered_root) or sha(script)!=suite['sha256']:raise ValueError('Registered evaluator source changed')
   identity=hashlib.sha256(json.dumps([revision['id'],suite,sha(pathlib.Path(__file__))],sort_keys=True).encode()).hexdigest()
   if identity in journal:continue
   parent=root/'existing-skills/evaluations';parent.mkdir(exist_ok=True,mode=0o755);os.chmod(parent,0o755)
   out=parent/identity;out.mkdir(mode=0o755);inputs=out/'inputs';inputs.mkdir(mode=0o755);work=out/'output';work.mkdir(mode=0o700);os.chown(work,1001,1001)
   old=state['revisions'][revision['previous']];data_root=pathlib.Path(plan['data_root'])/'skills'
   for name,record in [('baseline',old),('candidate',revision)]:
    source=data_root/pathlib.Path(record['path']).name
    if source.is_symlink() or sha(source)!=record['sha256']:raise ValueError('Immutable Skill artifact identity failed')
    (inputs/(name+'.md')).write_bytes(source.read_bytes());os.chmod(inputs/(name+'.md'),0o644)
   request={'baseline':'/tmp/watoom-skill-evaluation-input/baseline.md','candidate':'/tmp/watoom-skill-evaluation-input/candidate.md','output':'/tmp/watoom-skill-evaluation-output/report.json','caseIDs':suite['caseIDs'],'nonce':secrets.token_hex(16),'scope':state['scope']};atomic(inputs/'request.json',request);os.chmod(inputs/'request.json',0o644)
   # Copy reviewed executable into the immutable input area; it is never learned
   # or generated tool code. The task is unprivileged, offline and read-only.
   executable=inputs/'suite.py';executable.write_bytes(script.read_bytes());os.chmod(executable,0o644)
   # Reviewed auxiliary evidence/code is copied, hash-pinned and mounted read-only.
   import re
   for resource in suite.get('resources',[]):
    name=resource['name'];source=protected(resource['path'])
    if not re.fullmatch(r'[a-z0-9_.-]{1,64}',name) or name in ['suite.py','request.json','baseline.md','candidate.md'] or not source.resolve().is_relative_to(registered_root) or source.stat().st_size>2097152 or sha(source)!=resource['sha256']:raise ValueError('Invalid pinned evaluator resource')
    (inputs/name).write_bytes(source.read_bytes());os.chmod(inputs/name,0o644)
   argv=['systemd-run','--wait','--collect','--quiet','--unit=watoom-skill-evaluation-'+identity[:16]]
   properties={'StandardOutput':'journal','StandardError':'journal','User':'1001','Group':'1001','NoNewPrivileges':'yes','PrivateNetwork':'yes','PrivateDevices':'yes','PrivateTmp':'yes','BindReadOnlyPaths':str(inputs)+':/tmp/watoom-skill-evaluation-input','BindPaths':str(work)+':/tmp/watoom-skill-evaluation-output','ProtectSystem':'strict','ProtectHome':'yes','ReadWritePaths':'/tmp/watoom-skill-evaluation-output','InaccessiblePaths':'-/data/ai/watoom-code','MemoryMax':'1G','CPUQuota':'100%','RuntimeMaxSec':'180','WorkingDirectory':'/tmp/watoom-skill-evaluation-output','UMask':'0077'}
   for key,value in properties.items():argv.extend(['--property',key+'='+value])
   argv.extend(['/usr/bin/python3','-I','/tmp/watoom-skill-evaluation-input/suite.py','/tmp/watoom-skill-evaluation-input/request.json']);result=subprocess.run(argv,capture_output=True,timeout=210)
   logs=subprocess.run(['journalctl','--no-pager','-o','cat','-u','watoom-skill-evaluation-'+identity[:16],'-n','200'],capture_output=True,timeout=10)
   (out/'worker.log').write_bytes((result.stdout+result.stderr+logs.stdout+logs.stderr)[:262144]);os.chmod(out/'worker.log',0o600)
   try:
    if result.returncode:raise ValueError('Registered CPU task suite failed')
    report=json.loads((work/'report.json').read_text());baseline,comparison=validate_report(report,suite,old['sha256'],revision['sha256'])
    for kind,value in [('baseline',baseline),('compare',comparison)]:
     request_id=secrets.token_hex(16);command={'kind':'existing-skill-'+kind,'id':revision['skill'] if kind=='baseline' else revision['id'],'scope':state['scope'],'request':request_id,'report':value};file=pathlib.Path(plan['evaluations'])/('existing-'+request_id+'.json');atomic(file,command);os.chmod(file,0o644)
     deadline=time.monotonic()+90
     while True:
      with sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True) as db:values=[json.loads(v) for v, in db.execute('select value from kv where key like ?',('%learning/v1/%',))]
      op=next((s.get('operations',{}).get(request_id) for s in values if request_id in s.get('operations',{})),None)
      if op:
       if op['result']!='PASS':raise ValueError('Native evaluator rejected '+kind+': '+op.get('reason',''))
       break
      if time.monotonic()>deadline:raise ValueError('Native evaluator acknowledgement timed out')
      time.sleep(1)
    verified=out/'verified-report.json';atomic(verified,{'scope':state['scope'],'revision':revision['id'],'baseline':baseline,'comparison':comparison})
    journal[identity]={'status':'PASS','revision':revision['id'],'suite':suite['id'],'report_sha256':sha(work/'report.json'),'verified_report':str(verified),'verified_report_sha256':sha(verified),'scope_hash':hashlib.sha256(json.dumps(state['scope'],separators=(',',':')).encode()).hexdigest(),'time':time.time()}
   except Exception as error:journal[identity]={'status':'NO_MEASURED_BENEFIT' if 'No measured task benefit' in str(error) else 'FAIL','revision':revision['id'],'suite':suite['id'],'reason':str(error)[:300],'time':time.time()}
   atomic(journalfile,journal);return journal[identity]
 return {'status':'NO_UNEVALUATED_REGISTERED_CANDIDATE','staleSkipped':skipped,'domainSuitesPending':sorted(pending_domain),'pairedReplaysPending':sorted(pending_replays)}
