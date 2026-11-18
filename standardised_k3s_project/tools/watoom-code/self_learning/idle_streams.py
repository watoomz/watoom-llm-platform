"""Allow only positively observed, read-only native SSE heartbeats through idle drain."""
import socket,struct,time,re,json
from release_guard import active_clear,validate
HEARTBEAT=re.compile(rb'(?:[0-9a-fA-F]+\r\n)?: heartbeat\n\n(?:\r\n)?')
def key(connection):
 if connection['state']!='01':raise RuntimeError('Non-established connection cannot qualify as idle SSE')
 def decode(value):
  ip,port=value.split(':')
  if len(ip)!=8:raise RuntimeError('Only inspected IPv4 streams supported')
  return socket.inet_ntoa(bytes.fromhex(ip)[::-1]),int(port,16)
 local,lp=decode(connection['local']);remote,rp=decode(connection['remote'])
 if lp!=4096:raise RuntimeError('Unexpected application port')
 return local,lp,remote,rp
def classify(payload):return bool(HEARTBEAT.fullmatch(payload))
def notification(payload):
 match=re.fullmatch(rb'(?:[0-9a-fA-F]+\r\n)?data: ([^\r\n]+)\n\n(?:\r\n)?',payload)
 if not match:return False
 try:
  value=json.loads(match[1]);return isinstance(value,dict) and value.get('type') in ('skill.updated','provider.updated') and value.get('data')=={}
 except (ValueError,TypeError):return False
class NonIdleStreams(RuntimeError):
 def __init__(self,counters):
  self.unqualified={k for k,v in counters.items() if v['heartbeats']<1 or v['other_server_payloads'] or v['client_payloads']}
  super().__init__('Connections were not exclusively native idle SSE heartbeats and empty Skill/provider registry notifications; nothing terminated: '+json.dumps([{'connection':list(k),**v} for k,v in counters.items()]))

def closed_unqualified(error,current):
 return not error.unqualified & {key(c) for c in current['connections']} and not current['processes']

def observe(connections,seconds=20):
 counters={key(c):{'heartbeats':0,'native_skill_notifications':0,'other_server_payloads':0,'client_payloads':0,'other_event_types':[]} for c in connections}
 sock=socket.socket(socket.AF_PACKET,socket.SOCK_RAW,socket.htons(3));sock.settimeout(1)
 try:
  deadline=time.monotonic()+seconds
  while time.monotonic()<deadline:
   try:raw=sock.recv(65535)
   except TimeoutError:continue
   if len(raw)<54 or raw[12:14]!=b'\x08\x00':continue
   ip=raw[14:];ihl=(ip[0]&15)*4
   if ip[9]!=6 or len(ip)<ihl+20:continue
   tcp=ip[ihl:struct.unpack('!H',ip[2:4])[0]];sp,dp=struct.unpack('!HH',tcp[:4]);payload=tcp[(tcp[12]>>4)*4:]
   if not payload:continue
   source=socket.inet_ntoa(ip[12:16]);target=socket.inet_ntoa(ip[16:20]);forward=(source,sp,target,dp);reverse=(target,dp,source,sp)
   if forward in counters:
    counters[forward]['heartbeats' if classify(payload) else 'native_skill_notifications' if notification(payload) else 'other_server_payloads']+=1
    if not classify(payload) and not notification(payload):
     try:
      kind=json.loads(payload.split(b'data: ',1)[1].split(b'\n\n',1)[0]).get('type','UNKNOWN')
      if not isinstance(kind,str) or not re.fullmatch('[a-zA-Z0-9._-]{1,100}',kind):kind='UNKNOWN'
     except (ValueError,IndexError,AttributeError):kind='NON_SSE_FRAME_'+str(len(payload))
     if kind not in counters[forward]['other_event_types']:counters[forward]['other_event_types'].append(kind)
   elif reverse in counters:counters[reverse]['client_payloads']+=1
 finally:sock.close()
 if any(v['heartbeats']<1 or v['other_server_payloads'] or v['client_payloads'] for v in counters.values()):raise NonIdleStreams(counters)
 return [{'connection':list(k),**v} for k,v in counters.items()]
def drain(m,clearance,save):
 m.verify_closed();active_clear(m.request('/api/session/active'));validate(m.request('/api/session/deployment-guard'),True);clearance()
 transport=m.transport();deadline=time.monotonic()+3
 # Completed local maintenance HTTP probes can briefly await their TCP FIN.
 # Wait for them to close; never classify or ignore a persistent local stream.
 while any(c['remote'].startswith('0100007F:') for c in transport['connections']) and time.monotonic()<deadline:
  time.sleep(.1);transport=m.transport()
 if transport['processes']:raise RuntimeError('Application child processes active')
 connections=transport['connections']
 try:proof=observe(connections) if connections else []
 except NonIdleStreams as error:
  # A completed HTTP probe must actually disappear before one bounded retry.
  # No payload is whitelisted and no connection/process is killed or ignored.
  current=m.transport()
  if not closed_unqualified(error,current):raise
  active_clear(m.request('/api/session/active'));validate(m.request('/api/session/deployment-guard'),True);clearance();m.verify_closed()
  connections=m.transport()['connections']
  proof=observe(connections) if connections else []
 allowed={key(c) for c in connections}
 current=m.transport()
 if current['processes'] or not {key(c) for c in current['connections']}<=allowed:raise RuntimeError('Transport changed during idle stream observation')
 active_clear(m.request('/api/session/active'));validate(m.request('/api/session/deployment-guard'),True);clearance();m.verify_closed()
 save({'status':'PASS','seconds':20 if connections else 0,'idle_streams':proof,'raw_payload_retained':False,'connections_killed':False,'active_executions':0})
