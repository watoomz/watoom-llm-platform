#!/usr/bin/env python3
"""Unattended, reversible STAGING installer. Never changes deployments or active jobs."""
import argparse,datetime,hashlib,json,os,pathlib,shutil,subprocess,sys
P=argparse.ArgumentParser();P.add_argument('--action',choices=['install','rollback'],default='install');P.add_argument('--audit-report');P.add_argument('--snapshot');P.add_argument('--dry-run',action='store_true');P.add_argument('--i-approve',action='store_true');a=P.parse_args()
PACK=pathlib.Path(__file__).resolve().parent.parent
ROOT=pathlib.Path('/data/ai/helper-scripts');DEST=ROOT/'watoom-blender-asset-builder';SNAPROOT=ROOT/'blender-snapshots';LOG=[]
def log(s):print(s,flush=True);LOG.append(s)
def command(argv,timeout=90):
 try:r=subprocess.run(argv,capture_output=True,text=True,timeout=timeout);return r.returncode,(r.stdout+'\n'+r.stderr)[:1800]
 except Exception as e:return 99,str(e)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def copytree(src,dest):shutil.copytree(src,dest,ignore=shutil.ignore_patterns('.git','__pycache__','*.pyc'))
def fail(reason,snap=None):log('RESULT=FAIL REASON='+reason);log('SNAPSHOT='+str(snap));sys.exit(1)
if a.action=='rollback':
 if not a.snapshot:sys.exit('BLOCKED: --snapshot required')
 snap=pathlib.Path(a.snapshot).resolve();meta=snap/'manifest.json'
 if not meta.is_file():sys.exit('BLOCKED: invalid snapshot')
 info=json.loads(meta.read_text())
 if info['destination']!=str(DEST):sys.exit('BLOCKED: destination mismatch')
 if a.dry_run:log('DRY_RUN rollback '+str(DEST));sys.exit(0)
 if not a.i_approve:sys.exit('BLOCKED: rollback replaces staging files; add --i-approve')
 if not DEST.exists():sys.exit('BLOCKED: staging destination absent')
 current=sha(DEST/'manifest.json') if (DEST/'manifest.json').exists() else None
 if current!=info.get('installed_manifest_sha'):sys.exit('BLOCKED: staging changed since install; preserving it')
 moved=snap/'post-rollback-current';DEST.rename(moved)
 if info['prior_exists']: (snap/'prior').rename(DEST)
 log('RESULT=PASS rollback restored; displaced staging='+str(moved));sys.exit(0)
if not a.audit_report:sys.exit('BLOCKED: --audit-report path required')
rp=pathlib.Path(a.audit_report)
try: rep=json.loads(rp.read_text())
except Exception as e:sys.exit('BLOCKED: unreadable audit report '+str(e))
if not any(x['id']=='TOOLS-BLENDER-VERSION' and x['status']=='PASS' for x in rep['checks']):sys.exit('BLOCKED: Blender not verified; staging can be prepared but cannot be validated')
if not (PACK/'upstream'/'EL4CTEO__blender-skills'/'skills'/'blender-core'/'SKILL.md').is_file():sys.exit('BLOCKED: upstream EL4CTEO skills absent; vendor them first')
if a.dry_run:log('DRY_RUN: snapshot existing staging, copy vetted skills and scripts to '+str(DEST)+', validate, rollback on failure');sys.exit(0)
SNAPROOT.mkdir(parents=True,exist_ok=True);os.chmod(SNAPROOT,0o700)
snap=SNAPROOT/('install-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+str(os.getpid()));snap.mkdir(mode=0o700)
prior=DEST.exists();info={'destination':str(DEST),'prior_exists':prior,'source_package':str(PACK),'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':[]}
if prior:copytree(DEST,snap/'prior')
(snap/'manifest.json').write_text(json.dumps(info,indent=2))
stage=snap/'candidate';stage.mkdir()
assets=stage/'skills';assets.mkdir()
source=PACK/'upstream'/'EL4CTEO__blender-skills'
# Core six slices; full upstream reference trees separately retained in package/upstream
names=['blender-core','blender-scene-setup','blender-asset-qa','blender-export-pipelines','blender-game-optimization','blender-rendering','blender-pipeline-automation','blender-retopology-uv','blender-pbr-materials','blender-character-rigging','blender-animation','blender-lighting-lookdev','blender-sculpting','blender-geometry-nodes']
for name in names:
 src=source/'skills'/name
 if src.is_dir():copytree(src,assets/name)
copytree(PACK/'recipes',stage/'recipes')
copytree(source/'shared',stage/'shared')
shutil.copy2(source/'LICENSE',stage/'LICENSE-EL4CTEO')
(stage/'README.md').write_text('Staged WatooM Blender Builder. No OpenCode production integration activated.\nSee bundled IMPLEMENTATION-PLAN.md.\n')
files=sorted(p for p in stage.rglob('*') if p.is_file())
info['files']=[{'path':str(p.relative_to(stage)),'sha256':sha(p)} for p in files]
(stage/'manifest.json').write_text(json.dumps(info,indent=2))
if len([p for p in assets.iterdir() if (p/'SKILL.md').exists()])<8:fail('missing skill slices',snap)
# Verify copied scripts compile when Python; ignore Blender-only syntax/import limitations.
for file in stage.rglob('*.py'):
 import ast
 try:ast.parse(file.read_text(errors='replace'))
 except SyntaxError as e:fail('syntax '+str(file.relative_to(stage))+': '+str(e),snap)
if DEST.exists():DEST.rename(snap/'replaced-live')
try:
 stage.rename(DEST)
 for entry in info['files']:
  p=DEST/entry['path']
  if not p.is_file() or sha(p)!=entry['sha256']:raise RuntimeError('checksum mismatch '+str(p))
 info['installed_manifest_sha']=sha(DEST/'manifest.json');(snap/'manifest.json').write_text(json.dumps(info,indent=2))
 log('RESULT=PASS STAGED_ONLY=yes SKILLS='+str(len(list((DEST/'skills').glob('*')))))
 log('SNAPSHOT='+str(snap));log('ROLLBACK=python3 '+str(pathlib.Path(__file__))+' --action rollback --snapshot '+str(snap)+' --i-approve')
except Exception as e:
 if DEST.exists():shutil.move(str(DEST),str(snap/'failed-candidate'))
 if (snap/'replaced-live').exists():shutil.move(str(snap/'replaced-live'),str(DEST))
 fail(str(e),snap)
