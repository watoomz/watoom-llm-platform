"""Request-driven production checkpoints. Native tools perform engine validation separately."""
from contextlib import closing
import argparse,ctypes,datetime,fcntl,hashlib,json,os,pathlib,re,signal,sqlite3,subprocess,time,sys
SOURCE_QA_SCRIPT = r'''
# Mandatory packed runtime-source audit; authored by the maintained runner.
import bpy,sys,json,pathlib,hashlib
sys.path.insert(0,'/config/skills/blender-asset-qa/scripts')
import qa_check
args=sys.argv[sys.argv.index('--')+1:]
request=pathlib.Path(args[0]);root=request.parent;req=json.loads(request.read_text())
assert bpy.app.version[:3]==(5,2,1),'Use the pinned production Blender 5.2.1 runtime'
expected={}
for stage in req['stages']:
 if stage['name']!='QA':continue
 for name in stage['outputs']:
  try:doc=json.loads((root/name).read_text())
  except (ValueError,UnicodeError):continue
  if not isinstance(doc,dict):continue
  report=doc.get('upstream',doc)
  if isinstance(report,dict) and report.get('pass') is True and isinstance(report.get('objects'),dict):
   expected.update(report['objects'])
assert expected,'QA must emit an actual passed upstream geometry report with object metrics'
limit=sum(int(m['tris']) for m in expected.values());assert limit>0,'Validated geometry has no triangles'
names=sorted(o.name for o in bpy.context.scene.objects if o.type=='MESH')
result=qa_check.run(objects=names,profile='game',max_tris=limit)
extra=sorted(set(names)-set(expected));missing=sorted(set(expected)-set(names))
if extra:result['errors'].append('Unvalidated runtime meshes added after QA: '+', '.join(extra))
if missing:result['errors'].append('Validated runtime meshes missing after export: '+', '.join(missing))
result['pass']=result['pass'] and not extra and not missing
result.update(blender=bpy.app.version_string,validated_qa_triangles=limit,source_objects=names,unexpected_objects=extra,missing_objects=missing,engine_source_sha256=hashlib.sha256((root/req['engine_source']).read_bytes()).hexdigest())
pathlib.Path(args[1]).write_text(json.dumps(result,indent=2))
print('@@JSON@@'+json.dumps({'ok':True,'pass':result['pass'],'unexpected_objects':extra,'missing_objects':missing,'errors':result['errors']}),flush=True)
if not result['pass']:raise RuntimeError('Packed runtime source failed mandatory final geometry validation')
'''
ROOT=pathlib.Path('/data/ai/projects/llm/pipelines/blender-asset-builder')
SKILLS=pathlib.Path('/config/skills')
BLENDER=pathlib.Path('/data/ai/toolchains/blender/5.2.1/blender-5.2.1-linux-x64/blender')
BLENDER_SHA256='c2fd82553c979a7f6ba85202c487aa1173c90db588a67d74d70cc7b0c2bea01c'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def atomic(p,data):
 temp=p.with_name('.'+p.name+'.tmp')
 with temp.open('w') as f:json.dump(data,f,indent=2);f.flush();os.fsync(f.fileno())
 temp.replace(p)
def scoped(root,value,exists=False):
 p=root/pathlib.Path(value)
 if pathlib.Path(value).is_absolute() or '..' in pathlib.Path(value).parts or p.resolve()!=p or not p.is_relative_to(root):raise ValueError('Unsafe task-relative path: '+value)
 if exists and not p.is_file():raise ValueError('Missing input: '+value)
 return p
def engine(root,req,job):
 dbpath=pathlib.Path('/state/application.sqlite')
 with closing(sqlite3.connect('file:'+str(dbpath)+'?mode=ro',uri=True)) as db:
  rows=db.execute('SELECT phase,body,outcome FROM _watoom_specialist_job WHERE job=? AND capability=? AND specialist=?',(job,'3d.inspect','local-toolkit')).fetchall()
 if len(rows)!=1 or rows[0][0]!='completed':raise ValueError('Exactly one completed native engine job required')
 body=json.loads(rows[0][1]);outcome=json.loads(rows[0][2])
 source=scoped(root,req['engine_source'],True)
 expected='pipelines/'+str(source.relative_to(ROOT.parent))
 if body.get('path')!=expected or body.get('parameters')!={'engine_validation':1}:raise ValueError('Engine job does not match this request')
 artifacts=outcome['artifacts'];entry=next((a for a in artifacts if a['reference'].endswith('/manifest.json')),None)
 if entry is None:raise ValueError('Native engine job has no manifest artifact')
 reference=entry['reference'].removeprefix('artifact:')
 path=pathlib.Path('/generated')/reference
 if not reference.startswith('generated/watoom-toolkit-3d/v1/') or '..' in pathlib.Path(reference).parts or path.resolve()!=path:raise ValueError('Invalid native artifact')
 if sha(path)!=entry['sha256']:raise ValueError('Native manifest hash mismatch')
 manifest=json.loads(path.read_text());accept=manifest['engine_validation']
 if manifest['geometry_validation']['input_sha256']!=sha(source):raise ValueError('Engine input hash differs')
 if accept['status']!='PASS' or accept['godot']['status']!='PASS' or accept['unreal']['status']!='PASS' or accept['unreal']['playback_and_lods']['status']!='PASS':raise ValueError('Engine acceptance incomplete')
 for a in artifacts:
  p=pathlib.Path('/generated')/a['reference'].removeprefix('artifact:')
  if p.parent!=path.parent or sha(p)!=a['sha256'] or p.stat().st_size!=a['bytes']:raise ValueError('Native artifact changed')
 return {'status':'PASS','job':job,'manifest':str(path),'sha256':sha(path),'source_sha256':sha(source),'godot':'PASS','unreal':'PASS'}
def policy_scripts():
 base=pathlib.Path(__file__).resolve().parents[2]
 for policy in (SKILLS/'blender-core/scripts',base/'blender-core/scripts',base/'ansible/roles/watoom-code/files/skills/blender-core/scripts'):
  if (policy/'worker_profile.py').is_file():return policy
 raise ValueError('Maintained Blender worker policy is missing')
def main():
 p=argparse.ArgumentParser();p.add_argument('--request',required=True);p.add_argument('--dry-run',action='store_true');p.add_argument('--resume',action='store_true');p.add_argument('--retry-failed',action='store_true');p.add_argument('--engine-job');a=p.parse_args()
 request=pathlib.Path(a.request).resolve(strict=True);root=request.parent
 if not root.is_relative_to(ROOT) or root==ROOT:raise ValueError('Use a new version directory under '+str(ROOT))
 req=json.loads(request.read_text())
 if req.get('schema')!=1 or not req.get('brief') or not req.get('stages') or not req.get('references') or not req.get('specification') or not req.get('engine_source'):raise ValueError('Request needs brief, references, specification and stages')
 if len(req['stages'])>16:raise ValueError('At most 16 serial local stages')
 if len({s['name'] for s in req['stages']})!=len(req['stages']) or not {'MODEL','MATERIALS','QA','EXPORT'}<={s['name'] for s in req['stages']}:raise ValueError('Unique MODEL, MATERIALS, QA and EXPORT stages required')
 if any(stage['name']=='SOURCE_QA' for stage in req['stages']):raise ValueError('SOURCE_QA is a mandatory reserved runner checkpoint')
 for key in ('references','specification'):scoped(root,req[key],True)
 if a.dry_run:print(json.dumps({'status':'PLANNED','root':str(root),'stages':[s['name'] for s in req['stages']]+['SOURCE_QA'],'cpu_threads':2,'engine_tool':'watoom_specialist_run / 3d.inspect','automatic_visual_acceptance':False}));return 0
 policy=policy_scripts()
 sys.path.insert(0,str(policy))
 from worker_profile import verify_external,verify_binary,PROFILES
 profile=verify_external();verify_binary(BLENDER)
 execution={'profile':{k:v for k,v in profile.items() if k!='boundary'},'policy_sha256':sha(policy/'worker_profile.py'),'profiles_sha256':sha(PROFILES),'binary_sha256':BLENDER_SHA256}
 if not BLENDER.is_file() or sha(BLENDER)!=BLENDER_SHA256:raise ValueError('Pinned Blender binary missing or changed')
 (root/'reports').mkdir(exist_ok=True)
 with (root/'reports/pipeline.lock').open('a') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:
   print('BLOCKED: task already running');return 2
  statepath=root/'state.json'
  state=json.loads(statepath.read_text()) if statepath.exists() else {'schema':2,'request_sha256':sha(request),'stages':{},'result':'PARTIAL'}
  if state['request_sha256']!=sha(request):raise ValueError('Request changed; use a new version')
  if state['stages'] and not a.resume:raise ValueError('Existing state requires --resume')
  checker=root/'reports/.pipeline-source-qa-v1.py'
  if checker.exists() and checker.read_text()!=SOURCE_QA_SCRIPT:raise ValueError('Reserved final-source inspector differs; preserve it and use a new revision')
  if not checker.exists():checker.write_text(SOURCE_QA_SCRIPT)
  qa_inputs=[name for stage in req['stages'] if stage['name']=='QA' for name in stage['outputs']]
  qa_impl=SKILLS/'blender-asset-qa/scripts/qa_check.py'
  qa_helper=SKILLS/'blender-asset-qa/scripts/_bpyx.py'
  source_stage={'name':'SOURCE_QA','script':str(checker.relative_to(root)),'blend':req['engine_source'],'inputs':[req['engine_source'],*qa_inputs],'outputs':['reports/source-qa.json'],'args':[str(request),str(root/'reports/source-qa.json')],'timeout':180,'qa_implementation_sha256':sha(qa_impl),'qa_helper_sha256':sha(qa_helper)}
  for stage in [*req['stages'],source_stage]:
   name=stage['name']
   if not re.fullmatch('[A-Z][A-Z0-9_]{0,31}',name):raise ValueError('Invalid stage name')
   script=pathlib.Path(stage['script'])
   if not script.is_absolute():script=scoped(root,stage['script'],True)
   elif not script.is_relative_to(SKILLS) or script.resolve()!=script or not script.is_file():raise ValueError('Only installed skills or task-local scripts may execute')
   outputs=[scoped(root,x) for x in stage['outputs']]
   if not outputs:raise ValueError('Stage must declare durable output files')
   fingerprint=hashlib.sha256(json.dumps({'execution':execution,'stage':stage,'script':sha(script),'inputs':{x:sha(scoped(root,x,True)) for x in stage.get('inputs',[])}},sort_keys=True).encode()).hexdigest()
   old=state['stages'].get(name)
   if old and old['status']=='PASS':
    if old['fingerprint']!=fingerprint or any(not f.is_file() or old['outputs'].get(str(f.relative_to(root)))!=sha(f) for f in outputs):raise ValueError('Validated stage changed; use a new version: '+name)
    continue
   attempts=old.get('attempts',0) if old else 0
   if old and (not a.retry_failed or attempts>=2):raise ValueError('Interrupted/failed stage retained; inspect logs then --retry-failed once: '+name)
   blend=scoped(root,stage['blend'],True) if stage.get('blend') else None
   argv=[str(BLENDER),'--factory-startup','--disable-autoexec','--background']+([str(blend)] if blend else [])+['--threads','2','--python-exit-code','1','--python',str(script),'--',*stage.get('args',[])]
   if any(not isinstance(x,str) for x in argv):raise ValueError('Stage arguments must be strings')
   timeout=stage.get('timeout',180)
   if type(timeout)!=int or not 1<=timeout<=300:raise ValueError('Local stage timeout outside 1..300 seconds')
   if any(f.exists() for f in outputs):
    if not old:raise ValueError('Fresh stage refuses existing output: '+name)
    archive=root/'reports'/('retained-'+name+'-'+str(attempts));archive.mkdir(exist_ok=False)
    for index,f in enumerate(outputs):
     if f.exists():f.rename(archive/(str(index)+'-'+f.name))
   for f in outputs:f.parent.mkdir(parents=True,exist_ok=True)
   rec={'status':'RUNNING','fingerprint':fingerprint,'attempts':attempts+1,'outputs':{},'started':datetime.datetime.now(datetime.timezone.utc).isoformat()};state['stages'][name]=rec;state['result']='PARTIAL';atomic(statepath,state)
   log=root/'reports'/(name+'-'+str(attempts+1)+'.log');code=1;error=None
   parent=os.getpid()
   def parent_death():
    # Linux: an abruptly killed runner must not leave Blender running unbounded.
    if ctypes.CDLL(None).prctl(1,signal.SIGTERM,0,0,0)!=0 or os.getppid()!=parent:os._exit(125)
   def interrupted(signum,frame):raise InterruptedError('runner interrupted')
   previous={signum:signal.signal(signum,interrupted) for signum in (signal.SIGTERM,signal.SIGINT)}
   with log.open('w') as stream:
    child=subprocess.Popen(argv,cwd=root,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=parent_death,env={k:v for k,v in {**os.environ,'OMP_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'1','CUDA_VISIBLE_DEVICES':'','PYTHONDONTWRITEBYTECODE':'1'}.items() if k in ('PATH','HOME','TMPDIR','OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','CUDA_VISIBLE_DEVICES','PYTHONDONTWRITEBYTECODE')})
    try:code=child.wait(timeout=timeout)
    except (subprocess.TimeoutExpired,InterruptedError) as exception:
     if child.poll() is None:os.killpg(child.pid,signal.SIGTERM)
     try:child.wait(timeout=5)
     except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
     error='INTERRUPTED' if isinstance(exception,InterruptedError) else 'TIMEOUT'
    finally:
     for signum,handler in previous.items():signal.signal(signum,handler)
   missing=[str(f.relative_to(root)) for f in outputs if not f.is_file() or not f.stat().st_size]
   if error is None and code!=0:error='PROCESS_EXIT'
   if error is None and missing:error='MISSING_OUTPUT'
   rec.update(status='PASS' if code==0 and not missing and error is None else 'FAIL',exit_code=code,error=error,missing_outputs=missing,log=str(log),outputs={str(f.relative_to(root)):sha(f) for f in outputs if f.is_file()})
   # Upstream CLI can return numeric QA failure with process exit zero; inspect its JSON too.
   marked=[json.loads(line[8:]) for line in log.read_text(errors='replace').splitlines() if line.startswith('@@JSON@@')]
   if any(x.get('ok') is False or x.get('pass') is False for x in marked):rec['status']='FAIL';rec['error']='VALIDATION'
   if rec['status']!='PASS':state['result']='FAIL'
   atomic(statepath,state)
   if rec['status']!='PASS':print(json.dumps({'result':'FAIL','stage':name,'error':rec['error'],'missing_outputs':missing,'state':str(statepath),'recovery':'inspect retained output, correct failed script, resume with --retry-failed; maximum two attempts'}));return 2
  # Separate trust boundary: native completed job + published hashes, never an agent-authored PASS flag.
  if a.engine_job:state['engine']=engine(root,req,a.engine_job)
  elif 'engine' in state:
   state['engine']=engine(root,req,state['engine']['job'])
  # Visual review is an explicit authored assessment of actual images, not inferred from numeric QA.
  reviewpath=scoped(root,req.get('visual_review','reports/visual-review.json'))
  visual=None
  if reviewpath.is_file():
   visual=json.loads(reviewpath.read_text())
   if not visual.get('reviewer') or not visual.get('notes') or len(visual.get('images',{}))<2:raise ValueError('Visual review needs reviewer, notes and at least two actual images')
   for f,digest in visual['images'].items():
    if sha(scoped(root,f,True))!=digest:raise ValueError('Reviewed image changed')
  state['visual']={'status':visual.get('status','FAIL'),'review':str(reviewpath),'sha256':sha(reviewpath)} if visual else {'status':'NOT_REVIEWED'}
  state['result']='PASS' if state.get('engine',{}).get('status')=='PASS' and state['visual']['status']=='PASS' else 'PARTIAL'
  state['next']='DELIVERY' if state['result']=='PASS' else 'Run native engine validation and inspect actual reference/preview images; preserve this revision'
  atomic(statepath,state);print(json.dumps({'result':state['result'],'state':str(statepath),'next':state['next']}));return 0 if state['result']=='PASS' else 2
