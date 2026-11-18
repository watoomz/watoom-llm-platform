#!/usr/bin/env python3
"""Prepare isolated native learning manifests; apply through the dedicated Ansible playbook."""
import argparse,pathlib,json,subprocess,hashlib,shutil,secrets,os
from recover import atomic
p=argparse.ArgumentParser();p.add_argument('--evidence',type=pathlib.Path,required=True);p.add_argument('--namespace',required=True);a=p.parse_args()
root=a.evidence.resolve();ns=a.namespace
if not str(root).startswith('/data/ai/helper-scripts/watoom-self-learning-') or not ns.startswith('watoom-code-learning-'):raise ValueError('Dedicated owned staging paths required')
source=pathlib.Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
identity=hashlib.sha256(''.join(sha(source/x) for x in ['engine.mjs','index.mjs','package.json','mock_provider.py','worker_verifier.mjs','optimisation.mjs']).encode()).hexdigest()
stage=root/'staging';stage.mkdir(exist_ok=True)
for n in ['state','memory','config','home','workspace','evaluations','source']:
 d=stage/n;d.mkdir(exist_ok=True);os.chown(d,0 if n=='evaluations' else 1000 if n=='memory' else 1001,0 if n=='evaluations' else 1000 if n=='memory' else 1001);os.chmod(d,0o700 if n not in ('source','evaluations') else 0o755)
# Immutable source copy; preserve previous candidates across reruns.
version=stage/'source'/identity;version.mkdir(exist_ok=True);os.chmod(version,0o755)
for n in ['engine.mjs','index.mjs','package.json','mock_provider.py','worker_verifier.mjs','optimisation.mjs']:
 dst=version/n
 if dst.exists():
  if sha(dst)!=sha(source/n):raise ValueError('Immutable source changed')
 else:shutil.copy2(source/n,dst);os.chmod(dst,0o644)
credentials=stage/'credentials.json'
if not credentials.exists():credentials.write_text(json.dumps({'app':secrets.token_hex(32),'memory':secrets.token_hex(32)}));os.chmod(credentials,0o600)
creds=json.loads(credentials.read_text())
policy={'id':'sort-fixture','description':'Sort fixture development data','tool':'watoom_learning_fixture','input':{},'expectedHash':hashlib.sha256(b'Sorted fixture [1,2,3] verified').hexdigest(),'steps':['Run the native fixture tool.','Check persisted sorted data equals [1,2,3].'],'validation':'Compare persisted output to the independent expected fixed array.','recovery':'Preserve failed data, report mismatch and never alter infrastructure.'}
agent='learning-fixture'
config={'model':'fixture/cpu-fixture','default_agent':agent,'update':'disable','share':'disabled','snapshots':False,'compaction':{'auto':False},'agents':{agent:{'mode':'primary','steps':6,'system':'Perform only the requested deterministic CPU fixture. Preserve user preferences.','permissions':[{'action':'*','resource':'*','effect':'deny'},{'action':'skill','resource':'learned-*','effect':'allow'},{'action':'watoom_learning_*','resource':'*','effect':'allow'}]}},'providers':{'fixture':{'name':'Isolated CPU fixture','package':'@opencode/ai/providers/openai-compatible','settings':{'baseURL':'http://127.0.0.1:18080/v1','apiKey':'fixture-only'},'models':{'cpu-fixture':{'modelID':'cpu-fixture','name':'CPU fixture','capabilities':{'tools':True,'input':['text'],'output':['text']},'limit':{'context':100000,'output':1024}}}}},'plugins':[{'package':'/learning/source','options':{'root':'/learning/state','agent':agent,'fixture':True,'policies':[policy],'metadataBytes':1024,'curatorMs':30000,'evaluations':'/learning/evaluations','autoPromote':True}}]}
# Snapshot every existing native Skill into isolated read-only config for load
# baselines. Referenced scripts/assets are not mounted or executed by this suite.
corpus=root/'existing-skills/native-inventory.json'
if corpus.exists():
 directory=stage/'config/baseline-skills';directory.mkdir(exist_ok=True);os.chown(directory,0,0);os.chmod(directory,0o755)
 for skill in json.loads(corpus.read_text())['data']:
  if not __import__('re').fullmatch('[a-z0-9-]+',skill['id']):raise ValueError('Unsafe baseline Skill identity')
  body='---\nname: '+json.dumps(skill['id'])+'\ndescription: '+json.dumps(skill.get('description') or skill['name'])+'\n---\n'+skill['content']
  target=directory/(skill['id']+'.md')
  if not target.exists() or target.read_text()!=body:target.write_text(body)
  os.chown(target,0,0);os.chmod(target,0o644)
 config['plugins'][0]['options']['existingSkillIDs']=[k['id'] for k in json.loads(corpus.read_text())['data']]
 config['plugins'][0]['options']['baselineCorpusDigest']=sha(corpus)
 config['skills']=['/config/baseline-skills']
 config['agents'][agent]['permissions'].append({'action':'skill','resource':'*','effect':'allow'})
# The live smoke uses the existing primary router only after idle/admission checks.
production_config=json.loads(pathlib.Path('/data/ai/watoom-code/config/opencode.json').read_text())
provider=production_config.get('providers',{}).get('watoom')
if provider and 'swift-qwen38-coder' in provider.get('models',{}):
 config['providers']['watoom']={**provider,'models':{'swift-qwen38-coder':{**provider['models']['swift-qwen38-coder'],'limit':{**provider['models']['swift-qwen38-coder'].get('limit',{}),'output':512}}}}
configfile=stage/'config/opencode.json';configtext=json.dumps(config,indent=2)
if not configfile.exists() or configfile.read_text()!=configtext:configfile.write_text(configtext)
os.chown(configfile,1001,1001);os.chmod(configfile,0o600)
deps=json.loads((root/'baseline/deployments.json').read_text())['items']
appimage=next(x for x in deps if x['metadata']['name']=='watoom-code')['spec']['template']['spec']['containers'][0]['image']
memimage=next(x for x in deps if x['metadata']['name']=='agentmemory')['spec']['template']['spec']['containers'][0]['image']
def volume(name,host,mount,readonly=False):return ({'name':name,'hostPath':{'path':str(host),'type':'Directory'}},{'name':name,'mountPath':mount,'readOnly':readonly})
appvols=[volume('home',stage/'home','/home/opencode'),volume('config',stage/'config','/config',True),volume('state',stage/'state','/learning/state'),volume('source',version,'/learning/source',True),volume('workspace',stage/'workspace','/workspace'),volume('evaluations',stage/'evaluations','/learning/evaluations',True)]
app={'name':'app','image':appimage,'imagePullPolicy':'IfNotPresent','command':['/bin/sh','-c'],'args':['python3 /learning/source/mock_provider.py & exec /usr/local/bin/opencode serve --hostname 0.0.0.0 --port 4096'],'env':[{'name':k,'value':v} for k,v in {'HOME':'/home/opencode','OPENCODE_CONFIG_DIR':'/config','OPENCODE_DISABLE_MODELS_FETCH':'1','AGENTMEMORY_URL':'http://learning-memory:3111','AGENTMEMORY_SECRET':creds['memory'],'OPENCODE_PASSWORD':creds['app'],'OPENCODE_DB':'/learning/state/application.sqlite','WATOOM_DEPLOYMENT_GATE_FILE':'/learning/state/deployment-gate.json'}.items()],'volumeMounts':[x[1] for x in appvols],'resources':{'requests':{'cpu':'50m','memory':'256Mi'},'limits':{'cpu':'1','memory':'1Gi'}},'securityContext':{'allowPrivilegeEscalation':False,'capabilities':{'drop':['ALL']}},'readinessProbe':{'tcpSocket':{'port':4096},'initialDelaySeconds':5,'periodSeconds':3}}
memvol=volume('memory',stage/'memory','/data')
mem={'name':'memory','image':memimage,'imagePullPolicy':'IfNotPresent','env':[{'name':k,'value':v} for k,v in {'AGENTMEMORY_DATA_DIR':'/data','AGENTMEMORY_SECRET':creds['memory'],'AGENTMEMORY_INJECT_CONTEXT':'false','AGENTMEMORY_AUTO_COMPRESS':'false'}.items()],'volumeMounts':[memvol[1]],'resources':{'requests':{'cpu':'25m','memory':'128Mi'},'limits':{'cpu':'1','memory':'1Gi'}},'securityContext':{'allowPrivilegeEscalation':False,'capabilities':{'drop':['ALL']}},'readinessProbe':{'httpGet':{'path':'/agentmemory/livez','port':3111},'initialDelaySeconds':5,'periodSeconds':3}}
def deploy(name,c,vols):return {'apiVersion':'apps/v1','kind':'Deployment','metadata':{'name':name,'namespace':ns,'labels':{'watoom-owner':'self-learning'}},'spec':{'replicas':1,'strategy':{'type':'Recreate'},'selector':{'matchLabels':{'app':name}},'template':{'metadata':{'labels':{'app':name,'watoom-owner':'self-learning'}},'spec':{'automountServiceAccountToken':False,'securityContext':{'runAsUser':1001,'runAsGroup':1001,'fsGroup':1001},'containers':[c],'volumes':vols}}}}
# AgentMemory's installed engine image requires its existing root entrypoint; never grant a token.
memory=deploy('learning-memory',mem,[memvol[0]]);memory['spec']['template']['spec']['securityContext']={'runAsUser':1000,'runAsGroup':1000,'fsGroup':1000,'seccompProfile':{'type':'RuntimeDefault'}}
objects=[deploy('learning-app',app,[x[0] for x in appvols]),memory,{'apiVersion':'v1','kind':'Service','metadata':{'name':'learning-memory','namespace':ns},'spec':{'selector':{'app':'learning-memory'},'ports':[{'port':3111,'targetPort':3111}]}}]
objects[0]['spec']['template']['metadata']['annotations']={'watoom-learning-source-sha256':identity,'watoom-learning-config-sha256':sha(configfile)}
manifest=stage/'manifests.json';manifest.write_text(json.dumps({'apiVersion':'v1','kind':'List','items':objects},indent=2));os.chmod(manifest,0o600)
(stage/'prepared.json').write_text(json.dumps({'namespace':ns,'source_digest':identity,'appimage':appimage,'memoryimage':memimage,'manifest':str(manifest),'policy_digest':hashlib.sha256(json.dumps(policy,separators=(',',':')).encode()).hexdigest()},indent=2))
atomic(root/'state.json',{'phase':'STAGING_BUILT','staging_namespace':ns,'source_digest':identity,'production_cutover':False})
print(json.dumps({'namespace':ns,'staging':str(stage),'source_digest':identity,'manifest':str(manifest)}))
