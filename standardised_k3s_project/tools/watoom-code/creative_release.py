"""Creative release hooks for the existing native-fenced promotion coordinator."""
import copy,hashlib,json,pathlib,re,urllib.request,os,tempfile
from release_guard import UnsafeRelease
CAPABILITIES=['asset.index','asset.search','asset.inspect','asset.optimize','world.compose','character.prepare','material.derive']
NATIVE_GATES=["dungeon","dungeon_builder","dungeon_forge","dungeon_mixed","dungeon_api","dungeon_gui","dungeon_restart","dungeon_cancel","dungeon_rollback"]
def native_profile(accepted):
 if accepted.get("dungeon")!="PASS":return None
 if any(accepted.get(key)!="PASS" for key in NATIVE_GATES):raise UnsafeRelease("Native dungeon candidate gates incomplete")
 root=accepted.get("native_engine_root","");sha=accepted.get("native_editor_sha256","")
 if not (re.fullmatch(r"/data/ai/builds/unreal-recovery-[A-Za-z0-9TZ-]+/source",root) or re.fullmatch(r"/data/ai/toolchains/unreal/[0-9]+\.[0-9]+\.[0-9]+/runtime-"+re.escape(sha[:12]),root)) or not re.fullmatch("[a-f0-9]{64}",sha):raise UnsafeRelease("Accepted native engine identity required")
 return {"root":root,"editor_sha256":sha}
def desired_deployment(baseline,image,*,native=None):
 if not re.fullmatch(r'127\.0\.0\.1:5000/watoom-toolkit@sha256:[a-f0-9]{64}',image):raise UnsafeRelease('Immutable Toolkit image required')
 if baseline['spec'].get('replicas')!=1 or baseline['spec'].get('strategy',{}).get('type')!='Recreate':raise UnsafeRelease('Toolkit must remain one Recreate process')
 result=copy.deepcopy(baseline);result.pop('status',None)
 for key in ['resourceVersion','uid','creationTimestamp','generation','managedFields']:result['metadata'].pop(key,None)
 result['metadata'].get('annotations',{}).pop('kubectl.kubernetes.io/last-applied-configuration',None)
 container=next(c for c in result['spec']['template']['spec']['containers'] if c['name']=='toolkit')
 worker=[e for e in container['env'] if e['name']=='WATOOM_WORKER_IMAGE']
 if len(worker)!=1 or worker[0].get('value')!=container['image']:raise UnsafeRelease('Existing Toolkit/worker identity differs')
 mounts=[m for m in container['volumeMounts'] if m['name']=='assets']
 volumes=[v for v in result['spec']['template']['spec']['volumes'] if v['name']=='assets']
 if len(mounts)!=1 or mounts[0].get('mountPath')!='/assets' or mounts[0].get('readOnly') is not True or len(volumes)!=1 or volumes[0].get('hostPath',{}).get('path')!='/data/ai/assets':raise UnsafeRelease('Verified read-only library mount required')
 container['image']=image;worker[0]['value']=image
 if native:
  mounts=[m for m in container['volumeMounts'] if m.get('mountPath')=='/unreal-engine']
  if len(mounts)!=1 or mounts[0].get('readOnly') is not True:raise UnsafeRelease('Read-only native engine mount required')
  volumes=[v for v in result['spec']['template']['spec']['volumes'] if v['name']==mounts[0]['name']]
  if len(volumes)!=1 or volumes[0].get('hostPath',{}).get('type')!='Directory':raise UnsafeRelease('Existing native engine host directory required')
  volumes[0]['hostPath']['path']=native['root']
  values={'WATOOM_DUNGEON_ENABLED':'1','WATOOM_UNREAL_EDITOR_SHA256':native['editor_sha256'],'WATOOM_HOST_UNREAL_ENGINE':native['root']}
  for name,value in values.items():
   entries=[e for e in container['env'] if e['name']==name]
   if len(entries)>1:raise UnsafeRelease('Duplicate native engine configuration')
   if entries:entries[0].clear();entries[0].update(name=name,value=value)
   else:container['env'].append({'name':name,'value':value})
 return result
def bind(config,image,uid,revision,*,dungeon=False,native=None):
 value=copy.deepcopy(config)
 entries=[e for e in value.get('watoom_specialists',{}).get('entries',[]) if e['descriptor']['id']=='local-toolkit']
 if len(entries)!=1:raise UnsafeRelease('Exactly one existing local-toolkit registration required')
 entry=entries[0];descriptor=entry['descriptor']
 if entry['backend']!='toolkit-3d' or entry['artifactRoot']!='/generated':raise UnsafeRelease('Existing Toolkit route changed')
 descriptor['capabilities']=list(dict.fromkeys(descriptor['capabilities']+CAPABILITIES));descriptor['timeoutMs']=900000 if dungeon else 210000
 # Preserve the caller/controller envelope accepted by the native registry; the
 # independently bounded Kubernetes worker is sealed separately below.
 model=descriptor['model'];model['modelSha256']=image.split('@sha256:')[1];model['deploymentUID']=uid
 model['configurationSha256']=hashlib.sha256(json.dumps({'image':image,'backend':entry['backend'],'url':entry['url'],'capabilities':descriptor['capabilities'],'resources':descriptor['resources'],**({'native_engine':native,'native_worker':{'cpuCores':2,'ramMiB':6144,'ephemeralMiB':512,'timeoutSeconds':840}} if native else {})},sort_keys=True,separators=(',',':')).encode()).hexdigest()
 descriptor['sourceCommit']=revision
 return value
def registry(image,out):
 digest=image.split('@')[1]
 request=urllib.request.Request('http://127.0.0.1:5000/v2/watoom-toolkit/manifests/'+digest,headers={'Accept':'application/vnd.oci.image.manifest.v1+json'})
 with urllib.request.urlopen(request,timeout=10) as response:raw=response.read()
 if 'sha256:'+hashlib.sha256(raw).hexdigest()!=digest:raise UnsafeRelease('Toolkit manifest digest mismatch')
 manifest=json.loads(raw)
 if 'manifests' in manifest:raise UnsafeRelease('Toolkit architecture-specific manifest required')
 out.write_bytes(raw)
 for blob in [manifest['config'],*manifest['layers']]:
  with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:5000/v2/watoom-toolkit/blobs/'+blob['digest'],method='HEAD'),timeout=10) as response:
   if response.status!=200:raise UnsafeRelease('Toolkit rollback blob missing')
 with urllib.request.urlopen('http://127.0.0.1:5000/v2/watoom-toolkit/blobs/'+manifest['config']['digest'],timeout=10) as response:metadata=json.load(response)
 return metadata.get('config',{}).get('Labels',{}).get('org.opencontainers.image.revision','')
def verify_catalog_snapshot(accepted,before):
 expected=accepted.get("catalog_base_sha256")
 if not re.fullmatch("[a-f0-9]{64}",str(expected or "")) or hashlib.sha256(before or b"").hexdigest()!=expected:
  raise UnsafeRelease("Live Catalog changed after candidate preparation; preserve it and regenerate the bounded merge before promotion")
class Release:
 def __init__(self,kub,cmd,root,out,image,accepted,config,catalog_seed=None,*,native_guard=None):
  self.kub=kub;self.cmd=cmd;self.out=out;self.image=image;self.changed=False;self.atomic=None
  if native_guard is None:raise UnsafeRelease("Native application guard callback required for Toolkit rollout")
  from toolkit_release_fence import ToolkitFence
  self.fence=ToolkitFence(kub,cmd,root,out,native_guard,state_cwd=True)
  if accepted.get('toolkit_image')!=image or any(accepted.get(key)!='PASS' for key in ['creative','creative_rollback','creative_api','creative_gui','creative_durability']):raise UnsafeRelease('Creative candidate release gates incomplete')
  self.native=native_profile(accepted)
  if self.native:
   editor=pathlib.Path(self.native['root'])/'Engine/Binaries/Linux/UnrealEditor'
   with editor.open('rb') as stream:
    if hashlib.file_digest(stream,'sha256').hexdigest()!=self.native['editor_sha256']:raise UnsafeRelease('Accepted editor changed before promotion')
  self.before=kub('get','deploy','watoom-toolkit');self.desired=desired_deployment(self.before,image,native=self.native)
  self.old=next(c['image'] for c in self.before['spec']['template']['spec']['containers'] if c['name']=='toolkit')
  (out/'toolkit-before.json').write_text(json.dumps(self.before,indent=2));(out/'toolkit-desired.json').write_text(json.dumps(self.desired,indent=2))
  registry(self.old,out/'toolkit-rollback-manifest.json');revision=registry(image,out/'toolkit-new-manifest.json')
  if not re.fullmatch('[a-f0-9]{40}',revision):raise UnsafeRelease('Toolkit source provenance missing')
  self.revision=revision;self.config=bind(config,image,self.before['metadata']['uid'],revision,dungeon=bool(self.native),native=self.native)
  source=root/'ansible/roles/opencode-agent/files/v2-native/agents';target=pathlib.Path('/data/ai/watoom-code/config/agents')
  self.agents=[]
  for path in sorted(source.glob('*.md')):
   live=target/path.name
   if not live.is_file() or live.is_symlink():raise UnsafeRelease('Existing managed agent required: '+path.name)
   old=live.read_bytes();new=path.read_text().replace('  model: active-model','  model: swift-qwen38-coder').encode()
   (out/(path.name+'.before')).write_bytes(old);self.agents.append((live,old,new))
  if len(self.agents)!=len(list(source.glob('*.md'))) or len(self.agents)<7:raise UnsafeRelease('All managed agents must be preserved')
  if not catalog_seed or catalog_seed.stat().st_size>128*1024**2:raise UnsafeRelease('Completed verified catalog seed required')
  self.catalog_seed=catalog_seed.read_bytes();data=json.loads(self.catalog_seed)
  if data.get('schema')!=1 or data.get('root')!='/assets' or data.get('cursor')!='' or not 1<=len(data.get('records',{}))<=100000:raise UnsafeRelease('Completed authoritative library catalog required')
  state=next(v['hostPath']['path'] for v in self.before['spec']['template']['spec']['volumes'] if v['name']=='state')
  if state!='/data/ai/watoom-code/toolkit-state':raise UnsafeRelease('Existing Toolkit persistent state root differs')
  self.catalog_path=pathlib.Path(state)/'asset-catalog/catalog.json'
  if self.catalog_path.is_symlink() or self.catalog_path.parent.is_symlink():raise UnsafeRelease('Unsafe catalog state path')
  self.catalog_before=self.catalog_path.read_bytes() if self.catalog_path.exists() else None
  self.catalog_parent_before=self.catalog_path.parent.exists();self.catalog_installed=False
  if self.native:verify_catalog_snapshot(accepted,self.catalog_before)
  if self.catalog_before is not None:(out/'catalog-before.private.json').write_bytes(self.catalog_before)
  (out/'catalog-seed-validation.json').write_text(json.dumps({'status':'PASS','root':'/assets','records':len(data['records']),'sha256':hashlib.sha256(self.catalog_seed).hexdigest(),'bytes':len(self.catalog_seed)},indent=2))
 def install_catalog(self):
  current=self.catalog_path.read_bytes() if self.catalog_path.exists() else None
  if current!=self.catalog_before:raise UnsafeRelease('Catalog changed concurrently')
  if not self.catalog_parent_before:
   self.catalog_path.parent.mkdir(mode=0o700);os.chown(self.catalog_path.parent,1009,1009)
  if self.catalog_before is not None:
   self.atomic(self.catalog_path,self.catalog_seed);self.catalog_installed=True
  else:
   fd,temporary=tempfile.mkstemp(prefix='.catalog-release-',dir=self.catalog_path.parent)
   try:
    with os.fdopen(fd,'wb') as stream:os.fchmod(stream.fileno(),0o600);os.fchown(stream.fileno(),1009,1009);stream.write(self.catalog_seed);stream.flush();os.fsync(stream.fileno())
    os.link(temporary,self.catalog_path,follow_symlinks=False);self.catalog_installed=True
   finally:os.unlink(temporary)
  fd=os.open(self.catalog_path.parent,os.O_RDONLY)
  try:os.fsync(fd)
  finally:os.close(fd)
 def restore_catalog(self):
  if not getattr(self,'catalog_installed',False):return
  current=self.catalog_path.read_bytes() if self.catalog_path.exists() else None
  if current not in (self.catalog_seed,self.catalog_before):raise UnsafeRelease('Catalog changed during fenced rollback')
  if self.catalog_before is not None:self.atomic(self.catalog_path,self.catalog_before)
  elif self.catalog_path.exists():self.catalog_path.unlink()
  if not self.catalog_parent_before and not list(self.catalog_path.parent.iterdir()):self.catalog_path.parent.rmdir()

 def verify(self,image):
  pods=self.kub('get','pods','-l','app=watoom-toolkit')['items']
  live=[p for p in pods if p.get('status',{}).get('phase')=='Running' and not p['metadata'].get('deletionTimestamp')]
  if len(live)!=1:raise UnsafeRelease('Toolkit pod identity ambiguous')
  container=next(c for c in live[0]['status']['containerStatuses'] if c['name']=='toolkit')
  if container['imageID'].split('@')[-1]!=image.split('@')[-1]:raise UnsafeRelease('Toolkit runtime digest mismatch')
  code="import os,json,urllib.request; r=urllib.request.Request('http://127.0.0.1:'+os.environ.get('WATOOM_PORT','8879')+'/api/catalog',headers={'Authorization':'Bearer '+os.environ['WATOOM_TOKEN']}); d=json.load(urllib.request.urlopen(r,timeout=10)); assert isinstance(d['generators'],list); print(json.dumps(d.get('capabilities',[])))"
  caps=json.loads(self.cmd(['kubectl','-n','watoom-code','exec',live[0]['metadata']['name'],'-c','toolkit','--','python3','-c',code]))
  if image==self.image and not set(CAPABILITIES).issubset(caps):raise UnsafeRelease('Toolkit application contract unavailable')
 def verify_route(self,require_creative=True):
  if hasattr(self,"fence"):self.fence.open_route()
  pods=self.kub('get','pods','-l','app=watoom-code')['items']
  live=[p for p in pods if p.get('status',{}).get('phase')=='Running' and not p['metadata'].get('deletionTimestamp')]
  if len(live)!=1:raise UnsafeRelease('Application pod identity ambiguous for Toolkit route')
  entry=next(e for e in self.config['watoom_specialists']['entries'] if e['descriptor']['id']=='local-toolkit')
  target={'url':entry['url'],'tokenEnv':entry.get('tokenEnv')}
  code="import os,json,sys,urllib.request; e=json.loads(sys.argv[1]); token=os.environ[e['tokenEnv']] if e.get('tokenEnv') else ''; r=urllib.request.Request(e['url'].rstrip('/')+'/api/catalog',headers={'Authorization':'Bearer '+token} if token else {}); d=json.load(urllib.request.urlopen(r,timeout=10)); assert isinstance(d['generators'],list); print(json.dumps(d.get('capabilities',[])))"
  caps=json.loads(self.cmd(['kubectl','-n','watoom-code','exec',live[0]['metadata']['name'],'-c','app','--','python3','-c',code,json.dumps(target)]))
  if require_creative and not set(CAPABILITIES).issubset(caps):raise UnsafeRelease('Authenticated application-to-Toolkit creative route unavailable')
  (self.out/('backend-route-new.json' if require_creative else 'backend-route-rollback.json')).write_text(json.dumps({'status':'PASS','authenticated_from_application':True,'capabilities':caps},indent=2))
 def apply(self,atomic):
  self.atomic=atomic
  if self.kub('get','deploy','watoom-toolkit')['spec']!=self.before['spec']:raise UnsafeRelease('Toolkit changed concurrently')
  if any(p.read_bytes()!=old for p,old,new in self.agents):raise UnsafeRelease('Managed agent changed concurrently')
  if hasattr(self,"fence"):self.fence.acquire()
  self.changed=True
  self.cmd(['kubectl','apply','-f','-'],input=json.dumps(self.desired).encode())
  self.cmd(['kubectl','-n','watoom-code','rollout','status','deploy/watoom-toolkit','--timeout=180s'],timeout=190)
  self.verify(self.image)
  if hasattr(self,'catalog_path'):self.install_catalog()
  for path,old,new in self.agents:atomic(path,new)
 def rollback(self):
  if not self.changed:return
  if hasattr(self,"fence"):self.fence.ensure_closed()
  if self.kub('get','deploy','watoom-toolkit')['spec'] not in (self.before['spec'],self.desired['spec']):raise UnsafeRelease('Toolkit changed during fenced rollback; refusing overwrite')
  restore=desired_deployment(self.before,self.old)
  self.cmd(['kubectl','apply','-f','-'],input=json.dumps(restore).encode())
  self.cmd(['kubectl','-n','watoom-code','rollout','status','deploy/watoom-toolkit','--timeout=180s'],timeout=190)
  self.verify(self.old)
  self.restore_catalog()
  for path,old,new in self.agents:
   if path.read_bytes() not in (old,new):raise UnsafeRelease('Managed agent changed during rollback')
   self.atomic(path,old)
  (self.out/'toolkit-rollback.json').write_text(json.dumps({'status':'PASS','image':self.old,'all_six_agents_restored':True},indent=2))

 def release_admission(self):
  if hasattr(self,"fence"):self.fence.release()


class BlenderRelease(Release):
 """Engine inspection image-only release: preserve agents, catalogue and application image."""
 def __init__(self,kub,cmd,root,out,image,config,acceptance,native_guard):
  from toolkit_release_fence import ToolkitFence
  self.kub=kub;self.cmd=cmd;self.out=out;self.image=image;self.changed=False;self.atomic=None;self.agents=[]
  data=json.loads(acceptance.read_text())
  if data.get('candidate_image')!=image or len(data.get('fixtures',[]))!=3:raise UnsafeRelease('Three-fixture exact-image acceptance required')
  for fixture in data['fixtures']:
   path=pathlib.Path(fixture['manifest']);manifest=json.loads(path.read_text());engine=manifest['engine_validation']
   if manifest.get('status')!='PASS' or manifest.get('export_reimport') is not True or engine.get('status')!='PASS' or engine['godot']['status']!='PASS' or engine['unreal']['status']!='PASS' or engine['unreal']['playback_and_lods']['status']!='PASS':raise UnsafeRelease('Real candidate engine gates incomplete')
   if manifest['geometry_validation']['input_sha256']!=hashlib.sha256(pathlib.Path(fixture['source']).read_bytes()).hexdigest():raise UnsafeRelease('Candidate source changed')
   for item in manifest['outputs']:
    file=path.parent/item['path']
    if file.parent!=path.parent or file.is_symlink() or len(file.read_bytes())!=item['bytes'] or hashlib.sha256(file.read_bytes()).hexdigest()!=item['sha256']:raise UnsafeRelease('Candidate artifact hash mismatch')
   visual=json.loads(pathlib.Path(fixture['visual_review']).read_text())
   if visual['status']!='PASS' or not visual.get('reviewer') or not visual.get('notes') or len(visual.get('images',{}))<2:raise UnsafeRelease('Actual image assessment required for each fixture')
   for image_path,digest in visual['images'].items():
    file=pathlib.Path(image_path)
    if not file.is_absolute():file=pathlib.Path(fixture['source']).parent.parent/file
    if hashlib.sha256(file.read_bytes()).hexdigest()!=digest:raise UnsafeRelease('Reviewed image changed')
  for key in ('native_release','native_agent','recovery','memory','rollback'):
   report=json.loads(pathlib.Path(data[key]).read_text())
   if report.get('status')!='PASS':raise UnsafeRelease('Required independent acceptance failed: '+key)
  engine=data['engine'];self.native={'root':engine['root'],'editor_sha256':engine['sha256']}
  binary=pathlib.Path(self.native['root'])/'Engine/Binaries/Linux/UnrealEditor'
  with binary.open('rb') as stream:
   if hashlib.file_digest(stream,'sha256').hexdigest()!=self.native['editor_sha256']:raise UnsafeRelease('Pinned editor changed')
  self.fence=ToolkitFence(kub,cmd,root,out,native_guard,state_cwd=True)
  self.before=kub('get','deploy','watoom-toolkit');self.desired=desired_deployment(self.before,image)
  self.old=next(c['image'] for c in self.before['spec']['template']['spec']['containers'] if c['name']=='toolkit')
  (out/'toolkit-before.json').write_text(json.dumps(self.before,indent=2));(out/'toolkit-desired.json').write_text(json.dumps(self.desired,indent=2))
  registry(self.old,out/'toolkit-rollback-manifest.json');self.revision=registry(image,out/'toolkit-new-manifest.json')
  if not re.fullmatch('[a-f0-9]{40}',self.revision):raise UnsafeRelease('Candidate source commit missing')
  self.config=bind(config,image,self.before['metadata']['uid'],self.revision,dungeon=True,native=self.native)
  if set(self.config)!=set(config):raise UnsafeRelease('Engine-only release must preserve application configuration keys')
  (out/'acceptance-before.json').write_bytes(acceptance.read_bytes())

def promote_blender_toolkit():
 import argparse,subprocess,sys,time,tarfile
 import release_guard
 from maintenance_guard import Maintenance
 from bounded_process import run
 p=argparse.ArgumentParser();p.add_argument('--blender-toolkit-only',action='store_true');p.add_argument('--iac-root',required=True,type=pathlib.Path);p.add_argument('--evidence',required=True,type=pathlib.Path);p.add_argument('--image',required=True);p.add_argument('--blender-acceptance',required=True,type=pathlib.Path);p.add_argument('--i-approve',action='store_true')
 a=p.parse_args()
 print('RISK: rolls only the idle production Toolkit controller and worker image to the accepted immutable engine-validation build, updates its native binding and IaC pin. Existing native and Toolkit admission fences, snapshots and automatic rollback are required. Application and inference images remain unchanged.',flush=True)
 if not a.i_approve:raise UnsafeRelease('--i-approve required')
 root=a.iac_root.resolve();out=a.evidence.resolve();out.mkdir(parents=True,exist_ok=False,mode=0o700)
 m=Maintenance('watoom-code','watoom-code',out,True,True);get=m.request
 def cmd(args,timeout=60,input=None,cwd=None):
  result=run(args,input=input,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,cwd=cwd)
  if result.returncode:raise UnsafeRelease('Bounded release command failed: '+result.stderr.decode(errors='replace')[-400:])
  return result.stdout
 def kub(*args):return json.loads(cmd(['kubectl','-n','watoom-code',*args,'-o','json']))
 def clearance():
  release_guard.active_clear(get('/api/session/active'));release_guard.durable_clearance(pathlib.Path('/data/ai/watoom-code/application.sqlite'))
  if any(x.get('status',{}).get('active') for x in kub('get','jobs')['items']):raise UnsafeRelease('Active worker Jobs; no rollout allowed')
 def guard():release_guard.validate(get('/api/session/deployment-guard'),True);release_guard.active_clear(get('/api/session/active'))
 clearance()
 before={d['metadata']['namespace']+'/'+d['metadata']['name']:d['spec'] for d in json.loads(cmd(['kubectl','get','deployments','-A','-o','json']))['items']}
 (out/'protected-deployments-before.json').write_text(json.dumps(before,indent=2))
 config=pathlib.Path('/data/ai/watoom-code/config/opencode.json');old=config.read_bytes();defaults=root/'ansible/vars/watoom-code.yml';old_defaults=defaults.read_bytes()  # production pins (Option A)
 release=BlenderRelease(kub,cmd,root,out,a.image,json.loads(old),a.blender_acceptance,guard)
 desired=json.dumps(release.config,indent=2).encode();desired_defaults=old_defaults.decode()
 for name,value in [('watoom_code_toolkit_image',"'"+a.image+"'"),('watoom_code_toolkit_source_commit',release.revision)]:
  pattern=r'^'+name+r':.*$'
  if len(re.findall(pattern,desired_defaults,re.M))!=1:raise UnsafeRelease('Unique IaC pin required')
  desired_defaults=re.sub(pattern,name+': '+value,desired_defaults,flags=re.M)
 desired_defaults=desired_defaults.encode()
 for filename,data in [('config-before.private.json',old),('defaults-before.yml',old_defaults),('config-desired.private.json',desired),('defaults-desired.yml',desired_defaults)]:
  (out/filename).write_bytes(data)
 cmd(['kubectl','apply','--dry-run=server','-f','-'],input=json.dumps(release.desired).encode())
 def atomic(path,data):
  metadata=path.stat();fd,tmp=tempfile.mkstemp(prefix='.'+path.name+'.release-',dir=path.parent)
  try:
   with os.fdopen(fd,'wb') as stream:os.fchmod(stream.fileno(),metadata.st_mode&0o777);os.fchown(stream.fileno(),metadata.st_uid,metadata.st_gid);stream.write(data);stream.flush();os.fsync(stream.fileno())
   os.replace(tmp,path)
  finally:
   if os.path.exists(tmp):os.unlink(tmp)
 def save(owner):
  with (out/'guard-owner.private').open('x') as stream:stream.write(owner);stream.flush();os.fsync(stream.fileno())
 owner=release_guard.acquire(get,lambda path,body:m.request(path,body),save,clearance)
 safe_release=True
 try:
  release_guard.snapshot_database(pathlib.Path('/data/ai/watoom-code/application.sqlite'),out/'application-before.private.sqlite')
  with tarfile.open(out/'config-before.private.tar.gz','w:gz') as archive:archive.add(config.parent,arcname='config')
  if config.read_bytes()!=old or defaults.read_bytes()!=old_defaults:raise UnsafeRelease('Configuration changed concurrently')
  safe_release=False
  release.apply(atomic)
  atomic(config,desired);atomic(defaults,desired_defaults)
  release.verify(a.image);release.verify_route()
  after={d['metadata']['namespace']+'/'+d['metadata']['name']:d['spec'] for d in json.loads(cmd(['kubectl','get','deployments','-A','-o','json']))['items']}
  changed=[key for key in before if before[key]!=after.get(key)]
  if changed!=['watoom-code/watoom-toolkit']:raise UnsafeRelease('Unexpected Deployment changes: '+str(changed))
  release_guard.validate(get('/api/session/deployment-guard'),True)
  if config.read_bytes()!=desired or defaults.read_bytes()!=desired_defaults:raise UnsafeRelease('Desired binding bytes changed')
  safe_release=True
  (out/'release.json').write_text(json.dumps({'status':'PASS','image':a.image,'previous_image':release.old,'application_and_inference_specs':'UNCHANGED','scope':'Toolkit image/worker image, native binding and IaC provenance only','production_agent_engine_validation':'PENDING'},indent=2))
 except BaseException:
  if config.read_bytes() not in (old,desired) or defaults.read_bytes() not in (old_defaults,desired_defaults):raise UnsafeRelease('Concurrent config change; preserve fenced recovery evidence')
  atomic(config,old);atomic(defaults,old_defaults)
  release.rollback()
  safe_release=True
  (out/'automatic-rollback.json').write_text(json.dumps({'status':'PASS','restored_image':release.old},indent=2))
  raise
 finally:
  if safe_release:
   if getattr(release.fence,'owner',None):release.release_admission()
   elif release.fence.route_closed:release.fence.service.release();release.fence.route_closed=False
   release_guard.release(get,lambda path,body:m.request(path,body),owner)
 print((out/'release.json').read_text(),flush=True)


def rollback_blender_toolkit():
 import argparse,subprocess,time,importlib.util
 from maintenance_guard import Maintenance
 from toolkit_release_fence import ToolkitFence
 import release_guard
 p=argparse.ArgumentParser();p.add_argument('--rollback-blender-evidence',required=True,type=pathlib.Path);p.add_argument('--iac-root',required=True,type=pathlib.Path);p.add_argument('--evidence',required=True,type=pathlib.Path);p.add_argument('--i-approve',action='store_true');a=p.parse_args()
 print('RISK: restores only the exact recorded production Toolkit image, native binding and IaC pins while idle. User databases, assets, skills and inference are preserved. Concurrent configuration changes refuse rollback.',flush=True)
 if not a.i_approve:raise UnsafeRelease('--i-approve required')
 saved=a.rollback_blender_evidence.resolve();report=json.loads((saved/'release.json').read_text())
 if report.get('status')!='PASS':raise UnsafeRelease('A successful scoped release receipt is required')
 out=a.evidence.resolve();out.mkdir(parents=True,exist_ok=False,mode=0o700);m=Maintenance('watoom-code','watoom-code',out,True,True);get=m.request
 def cmd(args,timeout=60,input=None,cwd=None):return subprocess.check_output(args,input=input,timeout=timeout,cwd=cwd,stderr=subprocess.PIPE)
 def clearance():
  release_guard.active_clear(get('/api/session/active'));release_guard.durable_clearance(pathlib.Path('/data/ai/watoom-code/application.sqlite'))
  if any(x.get('status',{}).get('active') for x in m.kub('get','jobs')['items']):raise UnsafeRelease('Active worker Jobs; rollback refused')
 def guard():release_guard.validate(get('/api/session/deployment-guard'),True);release_guard.active_clear(get('/api/session/active'))
 config=pathlib.Path('/data/ai/watoom-code/config/opencode.json');defaults=a.iac_root/'ansible/vars/watoom-code.yml'
 desired=(saved/'config-desired.private.json').read_bytes();desired_defaults=(saved/'defaults-desired.yml').read_bytes()
 if config.read_bytes()!=desired or defaults.read_bytes()!=desired_defaults:raise UnsafeRelease('Current binding/IaC differs from recorded release; no changes made')
 x=BlenderRelease.__new__(BlenderRelease);x.kub=m.kub;x.cmd=cmd;x.out=out;x.image=report['image'];x.old=report['previous_image'];x.before=json.loads((saved/'toolkit-before.json').read_text());x.desired=json.loads((saved/'toolkit-desired.json').read_text());x.agents=[];x.changed=True
 if m.kub('get','deploy','watoom-toolkit')['spec']!=x.desired['spec']:raise UnsafeRelease('Current Toolkit differs from recorded release')
 registry(x.old,out/'rollback-image-manifest.json')
 spec=importlib.util.spec_from_file_location('_watoom_deployment_coordinator',a.iac_root/'tools/watoom-code/deploy-platform.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);x.atomic=module.atomic_write
 x.fence=ToolkitFence(m.kub,cmd,a.iac_root,out,guard,state_cwd=True)
 def save(owner):
  with (out/'guard-owner.private').open('x') as stream:stream.write(owner);stream.flush();os.fsync(stream.fileno())
 owner=release_guard.acquire(get,lambda path,body:m.request(path,body),save,clearance);safe=False
 try:
  release_guard.snapshot_database(pathlib.Path('/data/ai/watoom-code/application.sqlite'),out/'application-current.private.sqlite')
  x.fence.acquire();x.rollback()
  module.atomic_write(config,(saved/'config-before.private.json').read_bytes());module.atomic_write(defaults,(saved/'defaults-before.yml').read_bytes())
  (out/'result.json').write_text(json.dumps({'status':'PASS','restored_image':x.old,'source_release':str(saved),'user_data_preserved':True},indent=2));safe=True
 finally:
  if safe:x.release_admission();release_guard.release(get,lambda path,body:m.request(path,body),owner)
 print((out/'result.json').read_text(),flush=True)
