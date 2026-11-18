#!/usr/bin/env python3
"""Reproducibly snapshot upstream public skills. Network fetch only with --i-approve."""
import argparse,datetime,hashlib,json,pathlib,subprocess,sys
p=argparse.ArgumentParser();p.add_argument('--i-approve',action='store_true');p.add_argument('--dry-run',action='store_true');a=p.parse_args()
base=pathlib.Path(__file__).resolve().parent.parent/'upstream'
repos=['EL4CTEO/blender-skills','arjun988/blender-skills','nicceasy/3d-product','kevinbadi/blender-skills']
if a.dry_run:
 for r in repos:print('PLAN git clone immutable commit of',r,'into',base/(r.replace('/','__')))
 sys.exit(0)
if not a.i_approve:sys.exit('BLOCKED: fetching external source requires --i-approve; review upstream before use')
base.mkdir(parents=True,exist_ok=True)
index=[];failed=False
for r in repos:
 dst=base/r.replace('/','__')
 if dst.exists():
  if (dst/'.git').exists():
   z=subprocess.run(['git','-C',str(dst),'rev-parse','HEAD'],capture_output=True,text=True,timeout=12)
   print('PRESERVED existing vendor snapshot',r,z.stdout.strip());index.append({'repo':r,'path':str(dst),'commit':z.stdout.strip(),'status':'preserved'});continue
  print('BLOCKED destination exists',dst);failed=True;continue
 try:
  proc=subprocess.run(['git','clone','--depth','1','--no-tags','https://github.com/'+r+'.git',str(dst)],capture_output=True,text=True,timeout=130)
  if proc.returncode:print('FAIL clone',r,proc.stderr[:300]);failed=True;continue
  sha=subprocess.run(['git','-C',str(dst),'rev-parse','HEAD'],capture_output=True,text=True,timeout=12).stdout.strip()
  index.append({'repo':r,'path':str(dst),'commit':sha,'status':'fetched'});print('PASS',r,sha)
 except Exception as e:print('BLOCKED',r,str(e));failed=True
for entry in index:
 dst=pathlib.Path(entry['path']);files=[f for f in dst.rglob('*') if f.is_file() and '.git' not in f.parts]
 entry['licenses']=[str(f.relative_to(dst)) for f in files if f.name.lower().startswith(('license','licence','copying'))]
 entry['sha256']={str(f.relative_to(dst)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
 entry['modifications']='none; WatooM adaptations maintained outside this tree'
 entry['reuse']='reviewed code only' if entry['licenses'] else 'NO LICENCE FOUND: retain source for assessment only; no redistribution or code adaptation'
(base/'PROVENANCE.json').write_text(json.dumps(index,indent=2));sys.exit(1 if failed else 0)
