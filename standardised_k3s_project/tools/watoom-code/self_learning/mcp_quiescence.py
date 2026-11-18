"""Quiesce only inspected, idle Mesh stdio adapters through native MCP lifecycle APIs."""
import json,time,urllib.parse
SERVER='watoom-llama-mesh'
ADAPTER_SHA256='fcf46b72701405233b6849e426b657606bf848e43de5cefef37bfe5481cff738'
def endpoint(directory,action=None):
 base='/api/mcp' if action is None else '/api/experimental/mcp/'+SERVER+'/'+action
 return base+'?'+urllib.parse.urlencode({'location[directory]':directory})
def connected(m,directory):
 return any(x['name']==SERVER and x.get('status',{}).get('status')=='connected' for x in m.request(endpoint(directory))['data'])
def quiesce(m,state,save):
 if not m.request('/api/session/deployment-guard')['data']['held']:raise RuntimeError('Native admission fence required before MCP quiescence')
 if m.request('/api/session/active')['data']:raise RuntimeError('Active sessions prevent MCP quiescence')
 if not state.get('owner'):raise RuntimeError('Owned native admission token required')
 m.exec("import os,json,sys,pathlib;v=json.loads(pathlib.Path(os.environ['WATOOM_DEPLOYMENT_GATE_FILE']).read_text());assert v=={'version':1,'owner':sys.argv[1]},'Admission fence belongs to another operation'",state['owner'])
 if 'mcp_connections' not in state:
  code="""import pathlib,os,json,hashlib
result=[]
script=pathlib.Path('/config/watoom-tools/watoom-llama-mesh.py')
for p in pathlib.Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:
  args=(p/'cmdline').read_bytes().split(bytes([0]))
  if args[:3]!=[b'/usr/bin/python3',str(script).encode(),b'mcp']:continue
  fds={x.name:os.readlink(x) for x in (p/'fd').iterdir()}
  # The inspected synchronous adapter has no bridge socket while waiting on stdin.
  if set(fds)!={'0','1','2'} or (p/'wchan').read_text().strip() not in ['unix_stream_data_wait','pipe_read','anon_pipe_read']:raise RuntimeError('Mesh adapter is not idle on stdin')
  result.append({'pid':int(p.name),'start':(p/'stat').read_text().split()[21],'directory':os.readlink(p/'cwd'),'server':'watoom-llama-mesh','adapter_sha256':hashlib.sha256(script.read_bytes()).hexdigest()})
 except FileNotFoundError:continue
print(json.dumps(result))
"""
  entries=json.loads(m.exec(code))
  for entry in entries:
   if entry['adapter_sha256']!=ADAPTER_SHA256:raise RuntimeError('Mesh adapter differs from inspected synchronous implementation')
   if not connected(m,entry['directory']):raise RuntimeError('Idle adapter lacks matching native connection')
  state['mcp_connections']=entries;save(state)
 for entry in state['mcp_connections']:
  if connected(m,entry['directory']):m.request(endpoint(entry['directory'],'disconnect'),{})
 deadline=time.monotonic()+15
 while m.transport()['processes']:
  if time.monotonic()>deadline:raise RuntimeError('Application processes remain after native MCP disconnect; no processes killed')
  time.sleep(0.5)
 state['mcp_quiesced']=True;save(state)
def restore(m,state,save):
 for entry in state.get('mcp_connections',[]):
  if not connected(m,entry['directory']):m.request(endpoint(entry['directory'],'connect'),{})
  if not connected(m,entry['directory']):raise RuntimeError('Original MCP connection did not recover')
 state['mcp_restored']=True;save(state)
