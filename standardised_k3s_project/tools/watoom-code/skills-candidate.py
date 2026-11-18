#!/usr/bin/env python3
"""Prepare a separate Skills acceptance deployment; never copy live resumable session state."""
import argparse,copy,hashlib,json,os,pathlib,secrets,shutil,sqlite3,subprocess
NS='watoom-code';NAME='watoom-code-skills-candidate-20261017'
def command(args,data=None):return subprocess.check_output(args,input=data,timeout=60)
def clean(value):
 value=copy.deepcopy(value);value.pop('status',None)
 for key in ['uid','resourceVersion','creationTimestamp','generation','managedFields']:value['metadata'].pop(key,None)
 value['metadata'].get('annotations',{}).pop('kubectl.kubernetes.io/last-applied-configuration',None)
 return value
def prepare(root):
 out=root/'candidate';out.mkdir(mode=0o750,exist_ok=False)
 for name in ['home','workspace','state','config','collection']:
  p=out/name;p.mkdir(mode=0o750);os.chown(p,1001,1009)
 shutil.copytree(root/'snapshot/skills',out/'state/skills')
 os.chown(out/'state/skills',1001,1009)
 for p in (out/'state/skills').rglob('*'):
  os.chown(p,1001,1009)
 shutil.copyfile(root/'import-test.sqlite',out/'state/catalog.sqlite');os.chown(out/'state/catalog.sqlite',1001,1009)
 # A new native application database boots independently. Never replay user recovery claims.
 config=json.loads(pathlib.Path('/data/ai/watoom-code/config/opencode.json').read_text())
 config['skill_catalog']['collection']='/collection'
 (out/'config/opencode.json').write_text(json.dumps(config,indent=2));os.chown(out/'config/opencode.json',1001,1009)
 overlay=pathlib.Path('/data/ai/watoom-code/config/opencode.jsonc')
 if overlay.is_file():
  shutil.copyfile(overlay,out/'config/opencode.jsonc');os.chown(out/'config/opencode.jsonc',1001,1009)
 agents=out/'config/agents';agents.mkdir(mode=0o750);os.chown(agents,1001,1009)
 source=pathlib.Path('/data/github/watoom-standardised-homelab/standardised_k3s_project/ansible/roles/opencode-agent/files/v2-native/agents')
 for p in source.glob('*.md'):
  q=agents/p.name;q.write_text(p.read_text());os.chown(q,1001,1009)
 fixture='''---
description: Owned isolated skills manager acceptance
mode: primary
model:
  providerID: watoom
  model: swift-qwen38-coder
steps: 3
permissions:
  - action: "*"
    resource: "*"
    effect: deny
  - action: skill
    resource: "*"
    effect: allow
---
Use the directly exposed native skill FUNCTION tool for a matching assigned skill in your available-skills guidance. It is intentionally absent from Code Mode. Do not use execute, search, shell or MCP. Load a matching assigned skill once, then return its requested marker. This is an isolated read-only acceptance session.
'''
 (agents/'skills-fixture.md').write_text(fixture);os.chown(agents/'skills-fixture.md',1001,1009)
 folder=out/'collection/github__owned__manager/control';folder.mkdir(parents=True)
 text='---\nname: skill-manager-control\ndescription: A read-only skills manager acceptance check\n---\nReturn SKILLS_MANAGER_ACCEPTANCE_V1 after loading this skill. Do not run commands or access files or secrets.\n'
 (folder/'SKILL.md').write_text(text)
 for p in [out/'collection/github__owned__manager',folder,folder/'SKILL.md']:os.chown(p,1001,1009)
 db=sqlite3.connect(out/'state/catalog.sqlite')
 with db:
  db.execute("INSERT INTO sources(repo,commit_sha) VALUES(?,?)",('owned/manager','a'*40))
  db.execute("INSERT INTO skills(id,repo,path,name,description,sha256,license,risk,validation) VALUES(?,?,?,?,?,?,?,?,?)",('github:owned/manager:control','owned/manager','control','skill-manager-control','A read-only skills manager acceptance check',hashlib.sha256(text.encode()).hexdigest(),'MIT','[]','valid'))
  db.execute("INSERT INTO skills_fts(id,name,description) VALUES(?,?,?)",('github:owned/manager:control','skill-manager-control','A read-only skills manager acceptance check'))
 db.close()
 project=out/'workspace/skills-project';project.mkdir();os.chown(project,1001,1009)
 for args in [['git','init','-q',str(project)],['git','-C',str(project),'-c','user.name=OwnedAcceptance','-c','user.email=fixture@invalid','commit','--allow-empty','-qm','owned-skills-fixture']]:
  command(args)
 for p in project.rglob('*'):os.chown(p,1001,1009)
 baseline=json.loads(command(['kubectl','-n',NS,'get','deploy','watoom-code','-o','json']))
 deployment=clean(baseline);deployment['metadata']['name']=NAME;deployment['metadata']['labels']={'app':NAME,'watoom-test-owner':root.name}
 deployment['spec']['selector']={'matchLabels':{'app':NAME}};deployment['spec']['replicas']=0
 deployment['spec']['template']['metadata']={'labels':{'app':NAME,'watoom-test-owner':root.name}}
 spec=deployment['spec']['template']['spec'];spec['automountServiceAccountToken']=False
 container=next(c for c in spec['containers'] if c['name']=='app')
 container['resources']={'requests':{'cpu':'100m','memory':'256Mi'},'limits':{'cpu':'1','memory':'2Gi'}}
 # Rewrite only the four candidate-owned roots; all remaining source mounts are read-only.
 spec['volumes']=[({'name':v['name'],'hostPath':{'path':str(out/v['name']),'type':'Directory'}} if v['name'] in ['home','workspace','state','config'] else v) for v in baseline['spec']['template']['spec']['volumes']]
 for mount in container['volumeMounts']:
  if mount['name'] not in ['home','workspace','state']:mount['readOnly']=True
 spec['volumes'].append({'name':'skill-collection','hostPath':{'path':str(out/'collection'),'type':'Directory'}})
 container['volumeMounts'].append({'name':'skill-collection','mountPath':'/collection'})
 for index,repo in enumerate(sorted(pathlib.Path('/data/ai/skill-registry/wp-sk1-20261014/repositories').iterdir())):
  if not repo.is_dir() or repo.is_symlink():raise ValueError('Unexpected retained repository path')
  name='skill-source-'+str(index)
  spec['volumes'].append({'name':name,'hostPath':{'path':str(repo),'type':'Directory'}})
  container['volumeMounts'].append({'name':name,'mountPath':'/collection/'+repo.name,'readOnly':True})
 service={'apiVersion':'v1','kind':'Service','metadata':{'name':NAME,'namespace':NS,'labels':{'watoom-test-owner':root.name}},'spec':{'selector':{'app':NAME},'ports':[{'name':'http','port':4096,'targetPort':4096}]}}
 for name,value in [('deployment.private.json',deployment),('service.json',service)]:
  (out/name).write_text(json.dumps(value,indent=2));(out/name).chmod(0o600)
 identity={'namespace':NS,'name':NAME,'owner':root.name,'baseline_image':container['image'],'fixture_id':'github:owned/manager:control','project':'/workspace/skills-project','agent':'skills-fixture'}
 (out/'identity.json').write_text(json.dumps(identity,indent=2))
 print(json.dumps({'status':'PREPARED','candidate':NAME,'fresh_session_database':True,'source_repositories_mounted_read_only':index+1}))
def main():
 p=argparse.ArgumentParser();p.add_argument('--evidence',required=True,type=pathlib.Path);p.add_argument('--prepare',action='store_true');a=p.parse_args()
 if not a.prepare:raise ValueError('Use explicit --prepare; activation is separately reviewed and guarded')
 prepare(a.evidence.resolve())
if __name__=='__main__':main()
