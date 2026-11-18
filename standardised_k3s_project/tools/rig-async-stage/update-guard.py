"""Scoped isolated application guard update, with native idle fence and rollback."""
from pathlib import Path
import sys,json,hashlib,shutil,subprocess,os
BASE=Path(__file__).parent;sys.path.insert(0,str(BASE.parent/'watoom-code'))
from maintenance_guard import Maintenance
import release_guard
ROOT=Path('/data/ai/watoom-code-rig-jobs');DB=ROOT/'application.sqlite';CONFIG=ROOT/'config/opencode.json'
sha=hashlib.sha256((BASE/'guard-source/index.js').read_bytes()).hexdigest()
OUT=Path('/data/ai/helper-scripts/reports/rig-async-stage-guard')/sha;OUT.mkdir(parents=True,exist_ok=True,mode=0o700)
m=Maintenance('watoom-code-rig-jobs','watoom-code',OUT,True,True);before=CONFIG.read_bytes()
def clear():release_guard.durable_clearance(DB)
def save(v):p=OUT/'owner.private';p.write_text(v);p.chmod(0o600)
def rollout():
 subprocess.run(['kubectl','-n','watoom-code-rig-jobs','rollout','restart','deployment/watoom-code'],check=True,capture_output=True)
 subprocess.run(['kubectl','-n','watoom-code-rig-jobs','rollout','status','deployment/watoom-code','--timeout=120s'],check=True,capture_output=True,timeout=130)
agent_source=BASE.parent.parent/'ansible/roles/opencode-agent/files/v2-native/agents'
agent_names=['watoom-workflow.md','watoom-investigator.md','watoom-critic.md','watoom-builder.md','watoom-reviewer.md']
agent_before={name:(ROOT/'config/agents'/name).read_bytes() for name in agent_names}
owner=release_guard.acquire(m.request,lambda p,b:m.request(p,b),save,clear)
try:
 release_guard.snapshot_database(DB,OUT/'application-before.private.sqlite');(OUT/'config-before.private.json').write_bytes(before)
 target=ROOT/'config/watoom-tools'/('coordinator-guard-'+sha)
 if not target.exists():shutil.copytree(BASE/'guard-source',target)
 assert hashlib.sha256((target/'index.js').read_bytes()).hexdigest()==sha
 for directory,dirs,files in os.walk(target):
  os.chmod(directory,0o750);os.chown(directory,1001,1001)
  for name in files:os.chmod(Path(directory)/name,0o640);os.chown(Path(directory)/name,1001,1001)
 cfg=json.loads(before);entries=[x for x in cfg['plugins'] if isinstance(x,dict) and '/coordinator-guard-' in x.get('package','')];assert len(entries)==1
 entries[0]['package']='/config/watoom-tools/'+target.name
 for name in agent_names:
  path=ROOT/'config/agents'/name;path.write_bytes((agent_source/name).read_bytes());os.chown(path,1001,1001);os.chmod(path,0o644)
 CONFIG.write_text(json.dumps(cfg,indent=2)+'\n');rollout();clear()
 release_guard.release(m.request,lambda p,b:m.request(p,b),owner)
 (OUT/'result.json').write_text(json.dumps({'status':'PASS','guardSha256':sha,'stageOnly':True}));print('STAGE_GUARD_DEPLOYED '+sha)
except BaseException:
 for name,data in agent_before.items():(ROOT/'config/agents'/name).write_bytes(data)
 CONFIG.write_bytes(before);rollout();release_guard.release(m.request,lambda p,b:m.request(p,b),owner);raise
