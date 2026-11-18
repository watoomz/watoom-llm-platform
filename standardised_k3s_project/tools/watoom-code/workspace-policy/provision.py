#!/usr/bin/env python3
"""Idempotent host-side Homelab/LLM checkout and native policy installer. No reload, model call or session mutation."""
import argparse,pathlib,subprocess,json,os,tempfile,hashlib,time,shutil
ROOT=pathlib.Path('/data/ai/projects/homelab/homelab-llm');CANON=pathlib.Path('/data/github/watoom-standardised-homelab');CONFIG=pathlib.Path('/data/ai/watoom-code/config')
def git(root,*args):return subprocess.check_output(['git','-c','safe.directory='+str(root),'-C',str(root),*args],text=True).strip()
def atomic(file,raw,uid=1001,gid=1001,mode=0o600):
 if file.is_symlink():raise RuntimeError('Symlink destination refused')
 if file.exists() and file.read_bytes()==raw:
  os.chown(file,uid,gid);os.chmod(file,mode);return False
 fd,tmp=tempfile.mkstemp(prefix='.'+file.name+'-',dir=file.parent)
 try:
  with os.fdopen(fd,'wb') as f:
   os.fchmod(f.fileno(),mode);os.fchown(f.fileno(),uid,gid);f.write(raw);f.flush();os.fsync(f.fileno())
  os.replace(tmp,file)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
 return True

def main():
 before_config=(CONFIG/'opencode.json').read_bytes()
 before_agents=(ROOT/'AGENTS.md').read_bytes() if (ROOT/'AGENTS.md').exists() else b''
 before_policy=(CONFIG/'homelab-workspace-policy.json').read_bytes() if (CONFIG/'homelab-workspace-policy.json').exists() else b''
 p=argparse.ArgumentParser();p.add_argument('--source',type=pathlib.Path,default=pathlib.Path(__file__).parent);p.add_argument('--apply',action='store_true');a=p.parse_args();source=a.source.resolve()
 assert os.geteuid()==0
 if not ROOT.exists():
  assert a.apply,'Checkout absent; use --apply'
  subprocess.run(['git','clone','--no-hardlinks','--branch','dev',str(CANON),str(ROOT)],check=True)
  subprocess.run(['git','-C',str(ROOT),'switch','-c','agent/homelab-llm'],check=True)
  marker={'task':'homelab-llm','baseline':git(ROOT,'rev-parse','HEAD'),'canonical':str(CANON),'integration_target':'dev','layout':'independent-clone'}
  (ROOT/'.watoom-workspace.json').write_text(json.dumps(marker,indent=2)+'\n')
  for base,dirs,files in os.walk(ROOT):
   os.chown(base,1001,1001)
   for name in files:os.chown(os.path.join(base,name),1001,1001,follow_symlinks=False)
 assert ROOT.resolve()==ROOT and (ROOT/'.git').is_dir() and (ROOT/'.git').resolve()==ROOT/'.git'
 marker=json.loads((ROOT/'.watoom-workspace.json').read_text());assert marker['canonical']==str(CANON) and marker['task']=='homelab-llm' and marker['integration_target']=='dev'
 assert git(ROOT,'branch','--show-current')=='agent/homelab-llm' and git(ROOT,'remote','get-url','origin')==str(CANON)
 if not a.apply:print('PASS audit: independent clone and task branch');return
 identity=hashlib.sha1(('watoom-homelab-llm:'+str(ROOT)).encode()).hexdigest();atomic(ROOT/'.git/opencode',(identity+'\n').encode(),mode=0o644)
 agents=ROOT/'AGENTS.md';text=agents.read_text();start='<!-- WATOOM HOMELAB LLM PROJECT v2 -->';end='<!-- END WATOOM HOMELAB LLM PROJECT -->'
 if start in text:
  before,tail=text.split(start,1);_,after=tail.split(end,1);text=before.rstrip()+'\n\n'+(source/'project-AGENTS.md').read_text()+after.lstrip('\n')
 else:text=text.rstrip()+'\n\n'+(source/'project-AGENTS.md').read_text()
 atomic(agents,text.encode(),mode=0o644)
 for rel in ['.opencode','.opencode/work','.opencode/artifacts']:
  folder=ROOT/rel;folder.mkdir(exist_ok=True);assert not folder.is_symlink();os.chown(folder,1001,1001)
 prepush='#!/bin/sh\ncase "$1" in origin) ;; *) echo "Only reviewed origin integration is allowed" >&2; exit 1;; esac\nwhile read local_ref local_sha remote_ref remote_sha; do\n case "$remote_ref" in refs/heads/dev|refs/heads/agent/homelab-llm) ;; *) echo "Protected destination" >&2; exit 1;; esac\n if [ "$local_sha" = "0000000000000000000000000000000000000000" ]; then exit 1; fi\n if [ "$remote_sha" != "0000000000000000000000000000000000000000" ]; then git merge-base --is-ancestor "$remote_sha" "$local_sha" || exit 1; fi\ndone\n'
 atomic(ROOT/'.git/hooks/pre-push',prepush.encode(),mode=0o755)
 digest=hashlib.sha256((source/'guard.mjs').read_bytes()).hexdigest();package=CONFIG/'watoom-tools'/('homelab-workspace-'+digest);package.mkdir(exist_ok=True);os.chown(package,1001,1001);os.chmod(package,0o750);atomic(package/'index.mjs',(source/'guard.mjs').read_bytes(),mode=0o640)
 policy=CONFIG/'homelab-workspace-policy.json';value=json.loads(policy.read_text()) if policy.exists() else {'version':2,'root':str(ROOT),'enrollAfter':int(time.time()*1000),'integrationTarget':'dev'};assert value['root']==str(ROOT) and value['version']==2;atomic(policy,(json.dumps(value,indent=2)+'\n').encode(),mode=0o640)
 config=CONFIG/'opencode.json';before=config.read_bytes();data=json.loads(before);old=data.get('plugins',[]);updated=[]
 for item in old:
  name=item if isinstance(item,str) else item.get('package','')
  if name.endswith('/homelab-task-checkout-guard') or '/homelab-workspace-' in name:continue
  updated.append(item)
 updated.append({'package':'/config/watoom-tools/'+package.name,'options':{'policy':'/config/homelab-workspace-policy.json'}});data['plugins']=updated
 if data!=json.loads(before):
  backup=CONFIG/'backups';backup.mkdir(exist_ok=True,mode=0o700);atomic(backup/('before-homelab-'+hashlib.sha256(before).hexdigest()+'.json'),before,uid=0,gid=0)
 assert config.read_bytes()==before,'Concurrent config edit'
 atomic(config,(json.dumps(data,indent=2)+'\n').encode())
 print(json.dumps({'status':'PASS','changed':before_config!=config.read_bytes() or before_agents!=agents.read_bytes() or before_policy!=policy.read_bytes(),'projectID':identity,'directory':str(ROOT),'package':package.name,'configReadableUID':config.stat().st_uid,'reload':'not requested; new locations boot fresh','isolation':'tool mediation; unqualified execution denied'}))
if __name__=='__main__':main()
