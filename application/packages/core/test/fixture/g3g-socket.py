import sys,json,pathlib,os,socket,socketserver,struct,threading
ROOT=pathlib.Path(sys.argv[1]);SOURCE=pathlib.Path(sys.argv[3]);sys.path[:0]=[str(SOURCE),'/data/github/watoom-standardised-homelab/standardised_k3s_project/tools/llm/watoom-gpu-controller/tests']
from g3h_service import Runtime,process_identity
from controller import State
from durable_store import DurableStore
from kubernetes_actuator import KubernetesActuator
from test_kubernetes_actuator import FakeAPI
api=FakeAPI()
if (ROOT/'api.json').exists():api.items=json.loads((ROOT/'api.json').read_text())
config={'state_root':str(ROOT),'primary':'qwen','mesh':'mesh','stop_timeout':0.1,'startup_timeout':0.1,'released_gpu_max_mib':1500}
peer={'pid':0}
def units(job):
 pid=peer['pid']
 if runtime.owner_path.exists():
  state=runtime.store.load()
  if state.owner:pid=json.loads(runtime.owner_path.read_text())['pid']
 live=process_identity(pid) is not None
 return {'ActiveState':'active' if live else 'inactive','MainPID':str(pid) if live else '0'}
runtime=Runtime(config,api=api,probe=lambda *args:True,units=units,identity=process_identity)
# Inject only the offline Kubernetes boundary. Ownership, generation, durable intents and RPC validation are the real deployed controller implementation.
runtime.actuator=KubernetesActuator(api,runtime.journal,allowed=('qwen','mesh'))
runtime.controller.actuator=runtime.actuator
if not (ROOT/'state.json').exists():DurableStore(ROOT/'state.json').save(State())
(ROOT/'api.json').write_text(json.dumps(api.items))
class Handler(socketserver.StreamRequestHandler):
 def handle(self):
  pid,uid,gid=struct.unpack('3i',self.connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12));peer['pid']=pid
  try:
   request=json.loads(self.rfile.readline(65537));result=runtime.handle(request,private=True,pid=pid,uid=uid);response={'result':result}
  except Exception as error:response={'error':type(error).__name__,'detail':str(error)}
  (ROOT/'api.json').write_text(json.dumps(api.items));self.wfile.write(json.dumps(response).encode()+b'\n')
sock=pathlib.Path(sys.argv[2])
if sock.exists():sock.unlink()
server=socketserver.UnixStreamServer(str(sock),Handler)
os.chmod(sock,0o600)
print('READY',flush=True);server.serve_forever()
