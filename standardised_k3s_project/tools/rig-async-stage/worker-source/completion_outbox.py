"""Durable, idempotent synthetic completion delivery; never interrupts an active turn."""
import pathlib,json,hashlib,os,secrets
ROOT=pathlib.Path('/data/ai/private/rig-async-stage/outbox')
def atomic(p,d):
 p.parent.mkdir(parents=True,exist_ok=True,mode=0o700);t=p.with_name('.'+p.name+'.'+secrets.token_hex(6))
 with t.open('x') as f:json.dump(d,f,indent=2);f.flush();os.fsync(f.fileno())
 os.replace(t,p)
def enqueue(request,coordinator,text,kind='blender',application=None):
 application=application or {'namespace':'watoom-code','name':'watoom-code'}
 key=hashlib.sha256((application['namespace']+':'+application['name']+':'+kind+':'+request['request_id']).encode()).hexdigest();p=ROOT/(key+'.json')
 body={'id':'msg_rig_'+key,'text':text,'description':'Existing external '+kind+' job completion','metadata':{'source':'rig-stage-completion','request_id':request['request_id'],'job':request['job'],'worker':'rig-stage'},'delivery':'queue','resume':True}
 if p.exists():
  old=json.loads(p.read_text())
  # Identity is application + coordinating session. The text embeds a status that can change after
  # the first notice (e.g. a later reconciliation); keep the first notice and never re-notify.
  if old['application']!=application or old['session']!=coordinator:raise ValueError('Completion identity conflict; no duplicate notification')
  return
 atomic(p,{'application':application,'session':coordinator,'body':body,'state':'PENDING','attempts':0})
def drain(api):
 if not ROOT.exists():return 0
 count=0
 for p in sorted(ROOT.glob('*.json'))[:512]:
  d=json.loads(p.read_text())
  if d['state']=='DELIVERED' or d['application']!={'namespace':api.ns,'name':api.name}:continue
  try:
   info=api.request('/api/session/'+d['session']).get('data',{});body=dict(d['body'])
   if info.get('idleOutcome')=='interrupted':body['resume']=False
   api.request('/api/session/'+d['session']+'/synthetic',body);d['state']='DELIVERED';count+=1
  except Exception as e:d['error']=str(e)[:300];d['attempts']+=1
  atomic(p,d)
 return count
