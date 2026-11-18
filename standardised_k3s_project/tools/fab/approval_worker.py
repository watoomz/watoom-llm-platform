#!/usr/bin/env python3
"""Poll only project Fab requests; trust native completed question answers, never agent prose."""
import pathlib,sys,json,fcntl,re,subprocess
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'watoom-code'))
from maintenance_guard import Maintenance
import owned_catalog as owned
ROOTS=[pathlib.Path('/data/ai/projects')/x for x in ['games','development','pipelines']]
STATE=pathlib.Path('/data/ai/private/fab-acquisition')

def approval_proof(messages,v,digest):
 marker='FAB_APPROVAL:'+digest
 for msg in messages:
  for part in msg.get('content',[]):
   if part.get('type')!='tool' or part.get('name')!='question':continue
   st=part.get('state',{});questions=st.get('input',{}).get('questions',[])
   if st.get('status')!='completed' or len(questions)!=1:continue
   q=questions[0];text=q.get('question','')
   if any(value not in text for value in [marker,v['asset_id'],v['project'],v['title'],v['reason'],v['preparation_plan'],json.dumps(v.get('format_selection'),sort_keys=True,separators=(',',':'))]):continue
   if st.get('metadata',{}).get('answers') != [['Approve download']]:continue
   if 'Approve download' not in [x.get('label') for x in q.get('options',[])]:continue
   return {'session_id':v['session_id'],'message_id':msg.get('id'),'tool_id':part.get('id'),'request_hash':digest,'native_answer':'Approve download'}
 return None

def main():
 owned.root();STATE.mkdir(parents=True,exist_ok=True,mode=0o700)
 lock=(STATE/'worker.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 evidence=pathlib.Path('/data/ai/helper-scripts/reports/fab-approval-worker');evidence.mkdir(exist_ok=True)
 m=None
 for root in ROOTS:
  if not root.is_dir():continue
  for base in root.iterdir():
   if base.is_symlink() or not base.is_dir():continue
   requests=base/'.opencode/asset-requests'
   if not requests.is_dir() or requests.is_symlink():continue
   for path in sorted(requests.glob('*.json')):
    if path.name.endswith('.receipt.json') or path.is_symlink() or path.stat().st_size>16384:continue
    try:
     if re.fullmatch('[a-f0-9]{64}',path.stem) and (STATE/(path.stem+'.json')).exists():continue
     v,item=owned.request(path);digest=owned.canonical(v)
     if v.get('status')!='AWAITING_OWNER_APPROVAL':continue
     decision=STATE/(digest+'.json')
     if decision.exists():continue
     if m is None:m=Maintenance('watoom-code','watoom-code',evidence,True,True)
     info=m.request('/api/session/'+v['session_id']).get('data',{})
     if pathlib.Path(info.get('location',{}).get('directory','/')).resolve()!=base.resolve():continue
     messages=m.request('/api/session/'+v['session_id']+'/message').get('data',[])
     proof=approval_proof(messages,v,digest)
     if not proof:continue
     owned.atomic(decision,{'schema':1,'request':v,'request_hash':digest,'owner_approval_evidence':proof,'status':'APPROVED'},0o600)
     r=subprocess.run([sys.executable,str(pathlib.Path(owned.__file__)),'fulfill','--approval',digest],timeout=5*3600)
     # Same existing project coordinator only, never a new session.
     receipt=base/'.opencode/asset-requests'/(digest+'.receipt.json')
     if receipt.exists():
      m.request('/api/session/'+v['session_id']+'/prompt',{'text':'Owner-approved Fab acquisition has a real project receipt at '+str(receipt)+'. Read its exact status, reconcile existing source/job before continuing the approved preparation plan. Source download/index is not engine-ready acceptance; use supported workers, complete materials/dependencies and independent runtime/visual gates. Preserve originals; do not execute downloaded plugin/code or invent missing conversion routes.','resume':True})
    except Exception as e:
     owned.atomic(evidence/(path.stem+'.error.json'),{'request':str(path),'error':str(e)[:1000]})
if __name__=='__main__':main()
