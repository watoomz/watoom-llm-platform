import pathlib,json,subprocess,hashlib,shutil,os,urllib.parse
os.umask(0o077)
BASE=pathlib.Path(__file__).parent;ROOT=pathlib.Path('/data/ai/watoom-code-rig-jobs');NS='watoom-code-rig-jobs';ORIG='watoom-code';APP='watoom-code';FIX='/data/ai/projects/games/rig-async-qualification-20261026'
def get(ns,kind,name):return json.loads(subprocess.check_output(['kubectl','-n',ns,'get',kind,name,'-o','json'],text=True))
def apply(d):
 p=subprocess.run(['kubectl','apply','-f','-'],input=json.dumps(d),capture_output=True,text=True)
 if p.returncode:raise RuntimeError('Stage object apply failed: '+d['kind']+'/'+d['metadata']['name'])
 if d['kind'] not in ('Secret',):print(d['kind']+'/'+d['metadata']['name'],flush=True)
assert not ROOT.exists(),'Existing isolated stage must be reconciled, never replaced'
for name in ('home','config','workspace','generated'):p=ROOT/name;p.mkdir(parents=True,exist_ok=True);os.chown(p,1001,1001)
os.chown(ROOT,1001,1001)
for name in ('agents','skills'):shutil.copytree(pathlib.Path('/data/ai/watoom-code/config')/name,ROOT/'config'/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
hash=hashlib.sha256((BASE/'guard-source/index.js').read_bytes()).hexdigest();guard=ROOT/'config/watoom-tools'/('coordinator-guard-'+hash);shutil.copytree(BASE/'guard-source',guard)
d=json.loads(pathlib.Path('/data/ai/watoom-code/config/opencode.json').read_text());d['plugins']=[{'package':'/config/watoom-tools/coordinator-guard-'+hash,'options':{'rigAsyncStage':True,'rigGameProjects':[FIX],'verifiedVisionModels':['watoom/tiel-coder-35b-a3b-mtp']}}];d['model']='watoom/tiel-coder-35b-a3b-mtp';d.pop('watoom_specialists',None);d.pop('mcp',None);(ROOT/'config/opencode.json').write_text(json.dumps(d,indent=2)+'\n')
for root,dirs,files in os.walk(ROOT):
 os.chown(root,1001,1001)
 for name in files:os.chown(pathlib.Path(root)/name,1001,1001)
apply({'apiVersion':'v1','kind':'Namespace','metadata':{'name':NS,'labels':{'watoom.io/purpose':'rig-async-isolated-stage'}}})
apply({'apiVersion':'v1','kind':'ServiceAccount','metadata':{'name':APP,'namespace':NS},'automountServiceAccountToken':False})
baseline=get(ORIG,'deployment',APP);d={'apiVersion':'apps/v1','kind':'Deployment','metadata':{'name':APP,'namespace':NS,'labels':{'watoom.io/purpose':'rig-async-isolated-stage'}},'spec':baseline['spec']};s=d['spec']['template']['spec'];s['automountServiceAccountToken']=False;s['volumes']=[v for v in s['volumes'] if v['name'] in ('ownership-observations','home','config','workspace','state','generated','ai-library')]
for v in s['volumes']:
 if v.get('hostPath',{}).get('path','').startswith('/data/ai/watoom-code'):v['hostPath']['path']=v['hostPath']['path'].replace('/data/ai/watoom-code',str(ROOT),1)
s['volumes'].append({'name':'stage-fixture','hostPath':{'path':FIX,'type':'Directory'}})
for c in s['containers']:
 c['volumeMounts']=[v for v in c.get('volumeMounts',[]) if v['name'] in {v['name'] for v in s['volumes']}];c['volumeMounts'].append({'name':'stage-fixture','mountPath':FIX})
 for e in c.get('env',[]):
  if e['name']=='AGENTMEMORY_URL' and 'value' in e:
   u=urllib.parse.urlsplit(e['value']);host=u.hostname
   if '.' not in host:e['value']=urllib.parse.urlunsplit((u.scheme,host+'.'+ORIG+'.svc.cluster.local'+(':'+str(u.port) if u.port else ''),u.path,u.query,u.fragment))
  if e.get('valueFrom',{}).get('secretKeyRef'):
   ref=e['valueFrom']['secretKeyRef'];secret=get(ORIG,'secret',ref['name']);apply({'apiVersion':'v1','kind':'Secret','metadata':{'name':ref['name'],'namespace':NS},'type':secret.get('type','Opaque'),'data':secret['data']})
apply(d);apply({'apiVersion':'v1','kind':'Service','metadata':{'name':APP,'namespace':NS},'spec':{'selector':{'app':APP},'ports':[{'port':4096,'targetPort':4096}]}})
subprocess.run(['kubectl','-n',NS,'rollout','status','deployment/'+APP,'--timeout=180s'],check=True)
print('Isolated app created with fresh DB, original projects read-only, fixture-only writable mount, same pinned model/image.')
