#!/usr/bin/env python3
"""Bounded, serial acceptance orchestration; preserves all evidence and honest test scope."""
import argparse,pathlib,json,subprocess,time,os,sys
from recover import atomic
p=argparse.ArgumentParser();p.add_argument('--evidence',required=True,type=pathlib.Path);p.add_argument('--namespace',default='watoom-code-learning-20261023');p.add_argument('--resume',action='store_true');a=p.parse_args()
r=pathlib.Path(__file__).resolve().parent;root=a.evidence;out=root/'validation';out.mkdir(exist_ok=True,mode=0o700);checks=[]
(root/'native-tests').mkdir(exist_ok=True,mode=0o700)
if a.resume:
 import hashlib
 prepared=json.loads((root/'staging/prepared.json').read_text())
 identity=hashlib.sha256(''.join(hashlib.sha256((r/n).read_bytes()).hexdigest() for n in ['engine.mjs','index.mjs','package.json','mock_provider.py','worker_verifier.mjs','optimisation.mjs']).encode()).hexdigest()
 if prepared['source_digest']!=identity:raise ValueError('Cannot reuse tests for changed immutable package')
 previous=json.loads((root/'validation-progress.json').read_text())
 atomic(root/'validation-before-resume.json',previous)
 checks=[x for x in previous['checks'] if x['status']=='PASS']
 lifecycle=json.loads((root/'lifecycle-contract-tests.json').read_text())
 if any(lifecycle.get('sources',{}).get(n)!=hashlib.sha256((r/n).read_bytes()).hexdigest() for n in lifecycle.get('sources',{})):
  checks=[x for x in checks if x['id']!='recovery_contracts']
 for report,check,source in [('idle-stream-drain.json','native_idle_sse_transport_drain','idle_streams.py'),('native-readiness.json','native_cold_location_skill_readiness','native_readiness.py')]:
  proof=json.loads((root/'native-tests'/report).read_text()) if (root/'native-tests'/report).exists() else {}
  if proof.get('source_sha256')!=hashlib.sha256((r/source).read_bytes()).hexdigest():checks=[x for x in checks if x['id']!=check]
base=['--evidence',str(root),'--namespace',a.namespace]
def run(name,argv,timeout=300):
 if a.resume and any(x['id']==name for x in checks):print(json.dumps({'id':name,'status':'REUSED_VERIFIED_SAME_PACKAGE'}),flush=True);return
 start=time.monotonic();log=out/(name+'-'+str(time.time_ns())+'.log')
 with log.open('w') as f:
  try:result=subprocess.run(argv,stdout=f,stderr=subprocess.STDOUT,timeout=timeout);code=result.returncode
  except subprocess.TimeoutExpired:code=124
 os.chmod(log,0o600);record={'id':name,'status':'PASS' if code==0 else 'FAIL','exit':code,'seconds':time.monotonic()-start,'log':str(log)};checks.append(record);atomic(root/'validation-progress.json',{'checks':checks});print(json.dumps(record),flush=True)
 if code:atomic(root/'test-results.json',{'status':'FAIL','checks':checks});raise SystemExit(1)
run('engine_worker_optimisation_contracts',['node','--test',str(r/'engine.test.mjs'),str(r/'worker_verifier.test.mjs'),str(r/'optimisation.test.mjs'),str(r/'index.test.mjs')])
run('recovery_contracts',['python3','-m','unittest','discover','-s',str(r),'-p','test_*.py'])
atomic(root/'lifecycle-contract-tests.json',{'status':'PASS','time':time.time(),'unit_test_log':checks[-1]['log'],'sources':{n:__import__('hashlib').sha256((r/n).read_bytes()).hexdigest() for n in ['mcp_quiescence.py','idle_streams.py','recover.py','deploy.py','optimise.py','test_mcp_quiescence.py','test_idle_streams.py','native_readiness.py','test_native_readiness.py','deployment_model.py','test_deployment_model.py']}})
run('existing_coordinator_regression',['node','--test',str(r.parent/'test-coordinator-guard.mjs')])
run('existing_skill_inventory',['python3',str(r/'existing_baseline.py'),'--evidence',str(root)])
run('all_existing_skill_native_parser_regression',['/data/ai/projects/llm/watoom-code/prompt-builder-20261020/toolchain/bun',str(r/'corpus_validation.mjs'),str(root)])
run('all_existing_skill_native_loads',['python3',str(r/'native_existing.py'),*base],600)
run('native_closed_loop',['python3',str(r/'runtime_validation.py'),*base,'--agent','learning-fixture','--model','fixture/cpu-fixture','--database',str(root/'staging/state/application.sqlite'),'--learning-root',str(root/'staging/state'),'--evaluations',str(root/'staging/evaluations')])
run('native_controls_and_process_restart',['python3',str(r/'native_controls.py'),*base],180)
run('native_memory_outage',['python3',str(r/'memory_outage.py'),*base],150)
run('independent_failed_startup_recovery',['python3',str(r/'recovery_exercise.py'),*base],240)
run('native_existing_revision_idle_overlay_and_rollback',['python3',str(r/'native_overlay.py'),*base],300)
run('native_idle_sse_transport_drain',['python3',str(r/'idle_stream_exercise.py'),'--evidence',str(root)],180)
run('native_cold_location_skill_readiness',['python3',str(r/'readiness_exercise.py'),'--evidence',str(root)],60)
run('production_preservation_and_isolation',['python3',str(r/'audit.py'),*base])
prepared=json.loads((root/'staging/prepared.json').read_text())
report={'status':'PASS','source_digest':prepared['source_digest'],'checks':checks,'recovery_controller_sha256':__import__('hashlib').sha256((r/'recover.py').read_bytes()).hexdigest(),'existing_skill_workflow_baselines':'PENDING registered representative task suites; no existing revisions promoted','scope_limits':['Corrupt candidates, partial writes and interrupted generation/curation are deterministic contract tests; process termination, memory outage, startup failure and restart are actual native runtime exercises.','Mock provider token counters are unavailable, not evidence of zero inference cost.','All existing Skills have native parser/instruction retention baselines; workflow benefits require independent paired task replay.'],'time':time.time()}
atomic(root/'test-results.json',report);atomic(root/'state.json',{'phase':'STAGING_TESTED','staging_validation':'PASS','source_digest':prepared['source_digest'],'production_cutover':False});print(json.dumps({'status':'PASS','checks':len(checks),'source_digest':prepared['source_digest']}))
