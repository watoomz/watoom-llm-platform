import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
from store import Store
from worker import Worker
from broker_service import Client,GENERATION_BROKER_TIMEOUT

def connection_with(lines):
 connection=MagicMock();connection.__enter__.return_value=connection
 connection.makefile.return_value.readline.side_effect=[json.dumps(x).encode()+b"\n" for x in lines]
 return connection

class ClientProgress(unittest.TestCase):
 def test_streams_stages_then_returns_result(self):
  seen=[];connection=connection_with([{"progress":"loading-model"},{"progress":"generating"},{"result":{"tested":True}}])
  with patch("broker_service.socket.socket",return_value=connection):
   self.assertEqual(Client("/fixture")("generate",{"id":"a","revision":"b"},{"prompt":"bench"},progress=seen.append),{"tested":True})
  self.assertEqual(seen,["loading-model","generating"])
  self.assertIs(json.loads(connection.sendall.call_args.args[0])["progress"],True)
  self.assertEqual(connection.settimeout.call_args_list[0].args[0],GENERATION_BROKER_TIMEOUT)
  self.assertLessEqual(connection.settimeout.call_args_list[-1].args[0],GENERATION_BROKER_TIMEOUT)

 def test_no_opt_in_without_callback(self):
  connection=connection_with([{"result":{}}])
  with patch("broker_service.socket.socket",return_value=connection):
   Client("/fixture")("generate",{"id":"a","revision":"b"},{"prompt":"bench"})
  self.assertNotIn("progress",json.loads(connection.sendall.call_args.args[0]))

 def test_failing_callback_and_unknown_stage_do_not_abandon_transaction(self):
  seen=[]
  def callback(stage):
   seen.append(stage);raise OSError("database locked")
  connection=connection_with([{"progress":"bogus"},{"progress":"generating"},{"error":"ValueError: boom","code":"operation_failed"}])
  with patch("broker_service.socket.socket",return_value=connection):
   with self.assertRaisesRegex(ValueError,"boom"):Client("/fixture")("generate",{"id":"a","revision":"b"},{"prompt":"x"},progress=callback)
  self.assertEqual(seen,["generating"])

 def test_progress_cannot_extend_overall_deadline(self):
  connection=connection_with([{"progress":"generating"},{"result":{}}])
  with patch("broker_service.socket.socket",return_value=connection),patch("broker_service.time.monotonic",side_effect=[0,GENERATION_BROKER_TIMEOUT+1]):
   with self.assertRaises(TimeoutError):Client("/fixture")("generate",{"id":"a","revision":"b"},{"prompt":"x"},progress=lambda s:None)

class WorkerStage(unittest.TestCase):
 def test_stage_is_recorded_while_generating_and_cleared_after(self):
  with tempfile.TemporaryDirectory() as root:
   store=Store(Path(root)/"catalog.sqlite");store.enqueue({"operation":"generate","id":"x","revision":"a"*40,"prompt":"A bench"})
   observed=[]
   class Ops:
    def generate(self,*args,progress=None,**kwargs):
     progress("generating");observed.append((store.jobs()[0]["state"],store.jobs()[0]["stage"]))
     return {"tested":True}
   self.assertTrue(Worker(store,Ops()).once())
   self.assertEqual(observed,[("GENERATING","generating")])
   job=store.jobs()[0];self.assertEqual((job["state"],job["stage"]),("GENERATION_VERIFIED",None));store.close()

 def test_stage_never_touches_non_generating_job(self):
  with tempfile.TemporaryDirectory() as root:
   store=Store(Path(root)/"catalog.sqlite");key=store.enqueue({"operation":"generate","id":"x"})
   store.transition(key,"FAILED","0","x");store.set_stage(key,"generating")
   self.assertIsNone(store.jobs()[0]["stage"]);store.close()

if __name__=="__main__":unittest.main()

class ServerReport(unittest.TestCase):
 def test_disconnected_client_does_not_abort_broker(self):
  import socket,threading,broker_service,os
  with tempfile.TemporaryDirectory() as tmp:
   calls=[]
   class FakeBroker:
    def __init__(self,*a):pass
    def __call__(self,action,record,request=None,progress=None):
     for stage in ("loading-model","generating","publishing"):progress(stage);calls.append(stage)
     return {"tested":True}
   config={"catalog":str(Path(tmp)/"c.sqlite"),"ui_uid":os.getuid(),"ui_gid":os.getgid(),"socket":str(Path(tmp)/"b.sock"),"state":tmp,"stage_only":False}
   Path(tmp,"cfg.json").write_text(json.dumps(config))
   store=Store(config["catalog"]);store.db.execute("INSERT INTO models VALUES('m','r',?)",(json.dumps({"revision":"r"}),));store.db.commit();store.close()
   servers=[]
   class Server(broker_service.socketserver.UnixStreamServer):
    def __init__(self,*a,**k):super().__init__(*a,**k);servers.append(self)
   with patch("broker_service.Broker",FakeBroker),patch("broker_service.os.geteuid",return_value=0),patch("broker_service.secure_socket"),patch("broker_service.socketserver.UnixStreamServer",Server),patch("sys.argv",["x","--config",str(Path(tmp,"cfg.json"))]):
    thread=threading.Thread(target=broker_service.main,daemon=True);thread.start()
    import time
    for _ in range(100):
     if servers and Path(config["socket"]).exists():break
     time.sleep(0.05)
    with socket.socket(socket.AF_UNIX) as s:
     s.connect(config["socket"]);s.sendall(json.dumps({"action":"generate","id":"m","revision":"r","request":{},"progress":True}).encode()+b"\n")
     s.shutdown(socket.SHUT_RDWR)
    for _ in range(100):
     if len(calls)==3:break
     time.sleep(0.05)
    servers[0].shutdown();thread.join(5)
   self.assertEqual(calls,["loading-model","generating","publishing"])
