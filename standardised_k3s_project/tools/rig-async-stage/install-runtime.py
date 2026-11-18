"""Install only the opt-in staged runtime after an operator-held idle queue fence."""
import pathlib,sqlite3,json,hashlib,shutil,os,subprocess,time
os.umask(0o077)
BASE=pathlib.Path(__file__).parent;HOME=pathlib.Path('/data/ai/helper-scripts/workstation-render-stage');STATE=pathlib.Path('/data/ai/helper-scripts/state/workstation-render-stage');EVID=pathlib.Path('/data/ai/helper-scripts/reports/rig-async-stage-20261026');EVID.mkdir(parents=True,exist_ok=True,mode=0o700)
assert (EVID/'idle-fence-held').exists(),'Operator must hold the idle queue transaction before installation'
manifest=json.loads((BASE/'source-manifest.json').read_text())
for name,sha in manifest['files'].items():
 if hashlib.sha256((BASE/name).read_bytes()).hexdigest()!=sha:raise RuntimeError('Stage source hash changed: '+name)
version=hashlib.sha256((BASE/'source-manifest.json').read_bytes()).hexdigest();release=pathlib.Path('/data/ai/helper-scripts/rig-async-stage/releases')/version
assert not release.exists(),'Existing version must be reconciled rather than overwritten'
shutil.copytree(BASE,release,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
for root,dirs,files in os.walk(release):
 os.chmod(root,0o755)
 for name in files:os.chmod(pathlib.Path(root)/name,0o644)
source=HOME/'source';before=HOME/('source.before-async-update-'+version[:12]);assert not before.exists()
with sqlite3.connect('file:'+str(STATE/'queue.sqlite')+'?mode=ro',uri=True) as db,sqlite3.connect(EVID/'queue-before.private.sqlite') as backup:db.backup(backup)
new=HOME/('source.async-'+version);shutil.copytree(release/'worker-source',new)
for root,dirs,files in os.walk(new):
 os.chmod(root,0o755)
 for name in files:os.chmod(pathlib.Path(root)/name,0o644)
os.rename(source,before);os.rename(new,source)
cfg=pathlib.Path('/etc/watoom-rig-async-stage.json');
if cfg.exists():
 assert json.loads(cfg.read_text())==json.loads((release/'stage-config.json').read_text()),'Existing stage configuration differs; reconcile explicitly'
else:shutil.copy2(release/'stage-config.json',cfg);os.chmod(cfg,0o644)
service='[Unit]\nDescription=Isolated staged RIG background job dispatch and completion delivery\nAfter=k3s.service watoom-workstation-inputs.socket\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 {release}/bridge-source/dispatcher.py\nUser=root\nNice=15\nCPUQuota=100%\nMemoryMax=768M\nMemorySwapMax=0\nTimeoutStartSec=20min\nKillMode=control-group\n'.format(release=release)
timer='[Unit]\nDescription=Reconcile staged RIG queues and durable completion outbox\n[Timer]\nOnBootSec=10s\nOnUnitInactiveSec=5s\nUnit=watoom-rig-async-stage.service\n[Install]\nWantedBy=timers.target\n'
pathlib.Path('/etc/systemd/system/watoom-rig-async-stage.service').write_text(service);pathlib.Path('/etc/systemd/system/watoom-rig-async-stage.timer').write_text(timer)
subprocess.run(['systemctl','daemon-reload'],check=True)
(EVID/'installed.json').write_text(json.dumps({'release':str(release),'version':version,'previousSource':str(before),'stageOnly':True},indent=2));print('STAGED_RUNTIME_INSTALLED '+version)
