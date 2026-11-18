#!/usr/bin/python3 -I
"""Initialize only fresh dev objects after the two authenticated remote refs match."""
import argparse,json,os,pathlib,pwd,subprocess,hashlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from runtime import atomic
WORK=pathlib.Path('/data/github/watoom-homelab-dev')
BARE=pathlib.Path('/data/ai/git/watoom-homelab-dev.git')
HOME=pathlib.Path('/data/ai/helper-scripts/dev-workspace')
def git(*args,cwd=None,check=True):
 p=subprocess.run(['/usr/bin/git',*args],cwd=cwd,capture_output=True,text=True,env={**os.environ,'GIT_TERMINAL_PROMPT':'0'},timeout=120)
 if check and p.returncode:raise RuntimeError('Git preparation failed: '+p.stderr[-1000:])
 return p.stdout.strip()
def initialize(baseline,remote,host):
 if os.geteuid()!=0:raise PermissionError('Administrative preparation required')
 if len(baseline)!=40 or any(x not in '0123456789abcdef' for x in baseline):raise ValueError('Exact production SHA required')
 receipt=HOME/'initial-baseline.json'
 if not receipt.exists():
  result=git('ls-remote',remote,'refs/heads/main','refs/heads/dev')
  refs={line.split()[1]:line.split()[0] for line in result.splitlines()}
  if refs!={'refs/heads/main':baseline,'refs/heads/dev':baseline}:raise RuntimeError('Remote production/dev refs must first match the exact verified baseline')
 runner=pwd.getpwnam('watoom-dev-run');server=pwd.getpwnam('watoom-dev-git')
 receipt=HOME/'initial-baseline.json'
 marker=HOME/'preparation.json'
 if not marker.exists():atomic(marker,{'baseline':baseline,'remote':remote,'bare_was_absent':not BARE.exists(),'workspace_was_absent':not WORK.exists()})
 ownership=json.loads(marker.read_text())
 if ownership['baseline']!=baseline or ownership['remote']!=remote:raise RuntimeError('Preparation marker belongs to a different baseline')
 if receipt.exists():
  old=json.loads(receipt.read_text())
  if old['baseline']!=baseline or old['production_remote']!=remote:raise RuntimeError('Existing development baseline differs; preserve its history')
 if BARE.is_symlink() or WORK.is_symlink():raise PermissionError('Development roots cannot be symlinks')
 if not BARE.exists():
  BARE.parent.mkdir(parents=True,exist_ok=True)
  git('init','--bare','--initial-branch=dev',str(BARE))
  git('--git-dir='+str(BARE),'fetch','--no-tags',remote,'refs/heads/main')
  if git('--git-dir='+str(BARE),'rev-parse','FETCH_HEAD')!=baseline:raise RuntimeError('Production changed during fetch; no branch was installed')
  git('--git-dir='+str(BARE),'update-ref','refs/heads/dev',baseline,'0'*40)
  for key,value in [('receive.denyDeletes','true'),('receive.denyNonFastForwards','true'),('gc.auto','0'),('receive.updateServerInfo','false')]:git('--git-dir='+str(BARE),'config',key,value)
 else:
  if not receipt.exists() and not ownership['bare_was_absent']:raise RuntimeError('Unowned existing development Git server; inspect before reuse')
  current=git('--git-dir='+str(BARE),'rev-parse','--verify','refs/heads/dev',check=False)
  if not current and ownership['bare_was_absent']:
   git('--git-dir='+str(BARE),'fetch','--no-tags',remote,'refs/heads/main')
   if git('--git-dir='+str(BARE),'rev-parse','FETCH_HEAD')!=baseline:raise RuntimeError('Production changed during recovery')
   git('--git-dir='+str(BARE),'update-ref','refs/heads/dev',baseline,'0'*40)
  elif not receipt.exists() and current!=baseline:raise RuntimeError('Unconfirmed dev work differs; preserve it')
  if subprocess.run(['/usr/bin/git','--git-dir='+str(BARE),'merge-base','--is-ancestor',baseline,'refs/heads/dev'],capture_output=True).returncode:raise RuntimeError('Development ancestry differs')
 os.chown(BARE,0,server.pw_gid);os.chmod(BARE,0o750)
 for name in ['objects','refs','logs']:
  root=BARE/name
  if not root.exists():continue
  for file in [root,*root.rglob('*')]:
   if file.is_symlink():raise PermissionError('Unexpected Git server symlink')
   os.chown(file,server.pw_uid,server.pw_gid)
 hooks=BARE/'hooks';hooks.mkdir(exist_ok=True);os.chown(hooks,0,0);os.chmod(hooks,0o755)
 policy=hooks/'pre-receive';policy.write_text('#!/bin/sh\nexec /usr/bin/python3 -I /data/ai/helper-scripts/dev-workspace/runtime.py --receive-policy\n');os.chown(policy,0,0);os.chmod(policy,0o755)
 for name in ['config','HEAD']:
  file=BARE/name;os.chown(file,0,server.pw_gid);os.chmod(file,0o440)
 destination='ssh://watoom-dev-git@127.0.0.1'+str(BARE)
 if not WORK.exists():
  git('clone','--no-local','--branch','dev',str(BARE),str(WORK))
  if git('-C',str(WORK),'rev-parse','HEAD')!=baseline:raise RuntimeError('Fresh clone baseline mismatch')
  git('-C',str(WORK),'remote','set-url','origin',destination)
  for file in [WORK,*WORK.rglob('*')]:
   if not file.is_symlink():os.chown(file,runner.pw_uid,runner.pw_gid)
 else:
  if not receipt.exists() and not ownership['workspace_was_absent']:raise RuntimeError('Unowned existing target; preserve it and inspect manually')
  if not receipt.exists() and (git('-c','safe.directory='+str(WORK),'-C',str(WORK),'rev-parse','HEAD')!=baseline or git('-c','safe.directory='+str(WORK),'-C',str(WORK),'status','--porcelain')):raise RuntimeError('Interrupted clone contains work; preserve it for review')
  if git('-c','safe.directory='+str(WORK),'-C',str(WORK),'branch','--show-current')!='dev':raise RuntimeError('Existing workspace is not on dev')
  if subprocess.run(['/usr/bin/git','-c','safe.directory='+str(WORK),'-C',str(WORK),'merge-base','--is-ancestor',baseline,'HEAD'],capture_output=True).returncode:raise RuntimeError('Existing clone has unrelated ancestry; preserve it')
  origin=git('-c','safe.directory='+str(WORK),'-C',str(WORK),'remote','get-url','origin')
  if origin==str(BARE) and not receipt.exists():git('-c','safe.directory='+str(WORK),'-C',str(WORK),'remote','set-url','origin',destination)
  elif origin!=destination:raise RuntimeError('Existing workspace remote differs')
 os.chmod(WORK,0o755)
 config=WORK/'.git/config';os.chown(config,0,runner.pw_gid);os.chmod(config,0o440)
 for file in [WORK/'.git/hooks',*(WORK/'.git/hooks').glob('*')]:
  os.chown(file,0,0);os.chmod(file,0o755 if file.is_dir() else 0o644)
 # UI/project discovery may read this code; it never receives direct write access.
 subprocess.run(['/usr/bin/setfacl','-R','-P','-m','u:1001:rX',str(WORK)],check=True)
 for directory,_,_ in os.walk(WORK):subprocess.run(['/usr/bin/setfacl','-m','d:u:1001:r-x',directory],check=True,capture_output=True)
 atomic(HOME/'transport.json',{'bare':str(BARE)})
 os.chmod(HOME/'transport.json',0o644)
 runtime={'workspace':str(WORK),'state':str(HOME/'state'),'uid':runner.pw_uid,'gid':runner.pw_gid,'baseline':baseline,'enabled':False,'memory':'2G','git_key':str(HOME/'keys/git/key'),'known_hosts':str(HOME/'known_hosts'),'dev_remote':destination,'program':str(HOME/'runtime.py')}
 if (HOME/'config.json').exists():
  previous=json.loads((HOME/'config.json').read_text());runtime['enabled']=previous.get('enabled',False)
 atomic(HOME/'config.json',runtime)
 public_key=pathlib.Path('/etc/ssh/ssh_host_ed25519_key.pub').read_text().split()
 (HOME/'known_hosts').write_text('127.0.0.1,'+host+' '+public_key[0]+' '+public_key[1]+'\n');os.chmod(HOME/'known_hosts',0o644)
 if not receipt.exists():atomic(receipt,{'baseline':baseline,'production_remote':remote,'github_main':baseline,'github_dev':baseline,'initial_clone_head':baseline,'BASELINE_MATCH':'PASS'})
 print(json.dumps({'status':'PASS','baseline':baseline,'workspace':str(WORK),'dev_remote':destination,'enabled':runtime['enabled']}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--i-approve',action='store_true');p.add_argument('--baseline',required=True);p.add_argument('--remote',required=True);p.add_argument('--host',required=True);a=p.parse_args()
 print('RISK: initializes only the dedicated development clone and Git server; existing work is preserved and production GitHub credentials remain outside the workspace.',flush=True)
 if not a.i_approve:raise PermissionError('--i-approve required')
 initialize(a.baseline,a.remote,a.host)
