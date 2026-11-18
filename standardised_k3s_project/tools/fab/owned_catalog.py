#!/usr/bin/env python3
"""Owned Fab catalog and operator-approved acquisition. No new service or credentials."""
import argparse,datetime,fcntl,hashlib,json,os,pathlib,re,subprocess,sys,tempfile
CAT=pathlib.Path('/data/ai/assets/catalog/fab-owned.json')
PRIVATE=pathlib.Path('/data/ai/private/fab-acquisition')
REPORTS=pathlib.Path('/data/ai/helper-scripts/reports')
HERE=pathlib.Path(__file__).resolve().parent

def atomic(p,v,mode=0o644):
 p.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(dir=p.parent)
 try:
  os.fchmod(fd,mode)
  with os.fdopen(fd,'w') as f:json.dump(v,f,indent=2);f.flush();os.fsync(f.fileno())
  os.replace(tmp,p)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
def root():
 if os.geteuid()!=0:raise PermissionError('Operator only; agents cannot authorize acquisition')
def canonical(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def catalog():return json.loads(CAT.read_text())
def project(v):
 p=pathlib.Path(v);r=p.resolve(strict=True)
 if p.is_symlink() or not r.is_relative_to('/data/ai/projects') or r==pathlib.Path('/data/ai/projects') or not r.is_dir():raise ValueError('Existing contained project required')
 return r
def request(p):
 p=pathlib.Path(p).resolve(strict=True);v=json.loads(p.read_text());base=project(v['project'])
 if not p.is_relative_to(base/'.opencode/asset-requests') or p.is_symlink():raise ValueError('Project request required')
 entries={x['id']:x for x in catalog()['assets']}
 if v['asset_id'] not in entries:raise ValueError('Not in authenticated owned catalog')
 if v.get('title')!=entries[v['asset_id']]['title']:raise ValueError('Title must match authenticated inventory')
 if not re.fullmatch(r'ses_[A-Za-z0-9]+',v.get('session_id','')):raise ValueError('Native coordinator session ID required')
 selection=v.get('format_selection',{})
 if not all(selection.get(k) for k in ['target_engine','available_formats','selected_format','source_evidence','rationale','engine_version']):raise ValueError('Verified format selection required before acquisition')
 if selection['selected_format'] not in selection['available_formats']:raise ValueError('Selected format not in inspected available formats')
 if not v.get('reason') or not v.get('preparation_plan'):raise ValueError('Reason and preparation plan required')
 return v,entries[v['asset_id']]
def main():
 ap=argparse.ArgumentParser();sp=ap.add_subparsers(dest='cmd',required=True)
 p=sp.add_parser('refresh');p.add_argument('--from-owned-json',type=pathlib.Path)
 p=sp.add_parser('request');p.add_argument('--project',required=True);p.add_argument('--asset-id',required=True);p.add_argument('--reason',required=True);p.add_argument('--preparation-plan',required=True);p.add_argument('--session-id',required=True);p.add_argument('--format-selection-json',required=True)
 p=sp.add_parser('approve');p.add_argument('--request',required=True);p.add_argument('--owner-approval-evidence',required=True)
 p=sp.add_parser('fulfill');p.add_argument('--approval',required=True)
 a=ap.parse_args()
 if a.cmd=='refresh':
  root();items=json.loads(a.from_owned_json.read_text()) if a.from_owned_json else json.loads(subprocess.check_output(['/data/ai/bin/epic-fab','list','--json'],timeout=120))
  if not isinstance(items,list) or not items:raise ValueError('Invalid owned response')
  result=[]
  for x in items:
   # UE-library assetIds are 32-hex; "extra" items (non-UE formats such as MetaHuman
   # .mhpkg packs, surfaced via `epic-fab extras`) are keyed by their Fab listing UUID.
   if not (re.fullmatch('[a-f0-9]{32}',x['id']) or re.fullmatch('[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',x['id'])):raise ValueError('Invalid owned ID')
   result.append({k:x.get(k) for k in ['id','title','type','ownedAt','source']}|{'ownership':'owned_account_inventory','availability':'NOT_YET_RECONCILED','conversion_readiness':'NOT_ASSESSED','license':'VERIFY_PER_SELECTED_ITEM'})
  previous={x['id']:x for x in json.loads(CAT.read_text())['assets']} if CAT.exists() else {}
  for item in result:
   old=previous.get(item['id'],{});source=old.get('source_path')
   if source and pathlib.Path(source).is_dir() and pathlib.Path(source).resolve().is_relative_to('/data/ai/assets/fab'):
    for key in ['availability','source_path','qualification_guide','conversion_readiness']:
     if key in old:item[key]=old[key]
  atomic(CAT,{'schema':1,'refreshed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source':'authenticated epic-fab list --json','scope':'owned items only; not storefront/purchases','assets':result})
  from pipeline_candidates import build
  build()
  CAT.with_suffix('.tsv').write_text('id\ttype\ttitle\n'+''.join(x['id']+'\t'+str(x['type'])+'\t'+x['title'].replace('\t',' ').replace('\n',' ')+'\n' for x in result))
  print(json.dumps({'status':'PASS','count':len(result),'catalog':str(CAT)}));return
 if a.cmd=='request':
  base=project(a.project);entries={x['id']:x for x in catalog()['assets']};item=entries.get(a.asset_id)
  if not item:raise ValueError('Unknown owned ID')
  v={'schema':1,'project':str(base),'asset_id':a.asset_id,'title':item['title'],'reason':a.reason,'preparation_plan':a.preparation_plan,'session_id':a.session_id,'format_selection':json.loads(a.format_selection_json),'status':'AWAITING_OWNER_APPROVAL','cost':'owned item; no purchase authorized'}
  ident=canonical(v);p=base/'.opencode/asset-requests'/(ident+'.json')
  if p.exists() and json.loads(p.read_text())!=v:raise ValueError('Request collision')
  atomic(p,v);print(json.dumps({'request':str(p),'request_hash':ident,'status':v['status']}));return
 root();PRIVATE.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(PRIVATE,0o700)
 if a.cmd=='approve':
  v,item=request(a.request)
  if len(a.owner_approval_evidence.strip())<12:raise ValueError('Explicit actual human approval evidence required')
  ident=canonical(v);p=PRIVATE/(ident+'.json')
  if p.exists():raise ValueError('Approval already exists; reconcile before replay')
  atomic(p,{'schema':1,'request':v,'request_hash':ident,'owner_approval_evidence':a.owner_approval_evidence,'status':'APPROVED','created_at':datetime.datetime.now(datetime.timezone.utc).isoformat()},0o600)
  print(json.dumps({'approval':ident,'status':'APPROVED'}));return
 if not re.fullmatch('[a-f0-9]{64}',a.approval):raise ValueError('Invalid approval ID')
 p=PRIVATE/(a.approval+'.json');st=p.stat()
 if p.is_symlink() or st.st_uid!=0 or st.st_mode&0o077:raise PermissionError('Trusted private operator approval required')
 lock=(PRIVATE/(a.approval+'.lock')).open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);v=json.loads(p.read_text())
 if v['status']!='APPROVED' or canonical(v['request'])!=v['request_hash'] or v['request_hash']!=a.approval:raise ValueError('Not approved or already attempted; inspect existing receipt')
 base=project(v['request']['project']);items={x['id']:x for x in catalog()['assets']};item=items[v['request']['asset_id']]
 selection=v['request'].get('format_selection')
 if not selection or selection['selected_format']!='Unreal Engine':
  v['status']='BLOCKED_FORMAT_DOWNLOAD_ROUTE';atomic(p,v,0o600)
  public={'asset_id':item['id'],'title':item['title'],'status':v['status'],'selected_format':selection.get('selected_format') if selection else None,'reason':'Selected format lacks a verified downloader route; no UE substitution or acquisition performed'}
  atomic(base/'.opencode/asset-requests'/(a.approval+'.receipt.json'),public);print(json.dumps(public));raise SystemExit(2)
 engine=selection['engine_version']
 if not re.fullmatch(r'UE_[0-9]+\.[0-9]+',engine):raise ValueError('Explicit supported UE version required')
 out=REPORTS/('fab-approved-'+a.approval);out.mkdir(exist_ok=False)
 atomic(out/'server-download-selection.json',[{'id':item['id'],'title':item['title']}]);v['status']='DOWNLOADING';v['evidence']=str(out);atomic(p,v,0o600)
 r=subprocess.run([sys.executable,str(HERE/'download-owned.py'),'--evidence',str(out),'--concurrency','2','--engine',engine],timeout=4*3600)
 v['status']='DOWNLOAD_FAILED' if r.returncode else 'SOURCE_DOWNLOADED_PREPARATION_PENDING';atomic(p,v,0o600)
 if r.returncode==0:
  c=subprocess.run([sys.executable,str(HERE/'index-receipt.py'),'--evidence',str(out)],timeout=2000)
  v['status']='SOURCE_INDEXED_PREPARATION_PENDING' if c.returncode==0 else 'SOURCE_DOWNLOADED_INDEX_PENDING';atomic(p,v,0o600)
 # Publish only safe receipt; never expose auth links/private raw downloader logs.
 public={'asset_id':item['id'],'title':item['title'],'status':v['status'],'project':str(base),'approval_hash':a.approval,'preparation_plan':v['request']['preparation_plan'],'note':'Source download/index is not engine or derivative acceptance; no plugin/code execution authorized'}
 atomic(base/'.opencode/asset-requests'/(a.approval+'.receipt.json'),public)
 print(json.dumps(public));raise SystemExit(0 if r.returncode==0 else 1)
if __name__=='__main__':main()
