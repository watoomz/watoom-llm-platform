import ast,pathlib,unittest,tempfile,subprocess,types,json,sys,fcntl,time,os,secrets
from unittest.mock import Mock
SOURCE=pathlib.Path(__file__).with_name("accept-render.py")
TREE=ast.parse(SOURCE.read_text())
STOP=next(n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name=="stop")
DETACH=next(n for n in TREE.body if isinstance(n,ast.If) and ast.unparse(n.test)=="a.detach")
class SupervisionTests(unittest.TestCase):
 def test_real_termination_signal_is_deferred_during_restoration(self):
  code="import signal,os,json\ncleanup=False\n"+ast.unparse(STOP)+"\nsignal.signal(signal.SIGTERM,stop)\ntry:os.kill(os.getpid(),signal.SIGTERM)\nexcept KeyboardInterrupt:pass\nelse:raise RuntimeError('render cancellation not delivered')\ncleanup=True\nos.kill(os.getpid(),signal.SIGTERM)\nprint('RESTORE_CONTINUED')\n"
  result=subprocess.run([sys.executable,"-c",code],capture_output=True,text=True,timeout=5)
  self.assertEqual(result.returncode,0,result.stderr);self.assertIn("RESTORE_CONTINUED",result.stdout)
 def namespace(self,root,observed="inactive",lookup_code=0,owner=None):
  calls=[]
  def atomic(path,value):path.write_text(json.dumps(value))
  def run(args,**_):
   calls.append(args)
   if args[0]=="systemctl":return types.SimpleNamespace(returncode=lookup_code,stdout=observed+"\n")
   self.assertEqual(json.loads((root/"dungeon-bake-supervisor.json").read_text())["status"],"LAUNCH_INTENT")
   return types.SimpleNamespace(returncode=0)
  runtime=types.SimpleNamespace(handle=Mock(return_value={"phase":"qwen-ready","owner":owner,"uncertain":False}))
  namespace={"a":types.SimpleNamespace(detach=True),"r":root,"pathlib":pathlib,"fcntl":fcntl,"json":json,"os":__import__("os"),"runtime":runtime,"config":{"startup_timeout":600,"stop_timeout":180},"atomic":atomic,"subprocess":types.SimpleNamespace(run=run),"time":time,"__file__":str(SOURCE)}
  return namespace,calls
 def execute(self,ns):
  try:exec(compile(ast.Module(body=[DETACH],type_ignores=[]),str(SOURCE),"exec"),ns)
  finally:
   if "launch_lock" in ns:ns["launch_lock"].close()
 @unittest.skipUnless(os.environ.get("WATOOM_RUN_SYSTEMD_TESTS")=="1","explicit isolated systemd test")
 def test_real_systemd_timeout_preserves_restoration(self):
  with tempfile.TemporaryDirectory(prefix="watoom-restore-shield-") as directory:
   root=pathlib.Path(directory);os.chown(root,1009,1009)
   marker=root/"phase";script=root/"probe.py"
   code="import signal,os,time,pathlib\ncleanup=False\n"+ast.unparse(STOP)+"\nsignal.signal(signal.SIGTERM,stop)\np=pathlib.Path("+repr(str(marker))+")\ntry:\n p.write_text('RUNNING')\n while True:time.sleep(.05)\nexcept KeyboardInterrupt:pass\nfinally:\n cleanup=True\n p.write_text('RESTORING')\n time.sleep(4)\n p.write_text('RESTORED')\n"
   compile(code,str(script),"exec")
   script.write_text(code);script.chmod(0o644)
   unit="watoom-restore-shield-"+secrets.token_hex(6)
   command=["systemd-run","--unit="+unit,"--property=RuntimeMaxSec=2","--property=TimeoutStopSec=8","--property=KillMode=mixed","--property=NoNewPrivileges=yes","setpriv","--reuid=1009","--regid=1009","--clear-groups","--no-new-privs",sys.executable,str(script)]
   subprocess.run(command,check=True,capture_output=True,text=True,timeout=10)
   try:
    deadline=time.monotonic()+5
    while not marker.exists() and time.monotonic()<deadline:time.sleep(.05)
    self.assertTrue(marker.exists())
    subprocess.run(["systemctl","kill","--kill-whom=main","--signal=TERM",unit],check=True,capture_output=True,timeout=5)
    deadline=time.monotonic()+12
    while time.monotonic()<deadline:
     if marker.read_text()=="RESTORED":break
     time.sleep(.1)
    self.assertEqual(marker.read_text(),"RESTORED")
    time.sleep(.2)
    values=subprocess.check_output(["systemctl","show",unit,"-p","Result","-p","ExecMainStatus","-p","MainPID"],text=True)
    self.assertIn("Result=timeout",values);self.assertIn("ExecMainStatus=0",values);self.assertIn("MainPID=0",values)
    target=os.environ.get("WATOOM_SYSTEMD_TEST_EVIDENCE")
    if target:pathlib.Path(target).write_text(json.dumps({"status":"PASS","unit":unit,"result":values,"restoration_completed_after_runtime_limit":True,"actual_gpu_or_models_used":False},indent=2))
   finally:subprocess.run(["systemctl","stop",unit],capture_output=True,timeout=12)
 def test_existing_supervisor_blocks_duplicate(self):
  for state in ("active","activating","deactivating"):
   with self.subTest(state=state),tempfile.TemporaryDirectory() as directory:
    root=pathlib.Path(directory);(root/"dungeon-bake-supervisor.json").write_text(json.dumps({"unit":"watoom-dungeon-bake-fixture"}))
    ns,calls=self.namespace(root,observed=state)
    with self.assertRaisesRegex(RuntimeError,"has not ended"):self.execute(ns)
    self.assertEqual(len(calls),1);self.assertEqual(calls[0][0],"systemctl")
 def test_unknown_service_manager_outcome_fails_closed(self):
  with tempfile.TemporaryDirectory() as directory:
   root=pathlib.Path(directory);(root/"dungeon-bake-supervisor.json").write_text(json.dumps({"unit":"watoom-dungeon-bake-fixture"}))
   ns,calls=self.namespace(root,lookup_code=1)
   with self.assertRaisesRegex(RuntimeError,"Cannot verify"):self.execute(ns)
   self.assertEqual(len(calls),1)
 def test_launch_intent_precedes_start_and_restore_has_budget(self):
  with tempfile.TemporaryDirectory() as directory:
   root=pathlib.Path(directory);ns,calls=self.namespace(root)
   with self.assertRaises(SystemExit):self.execute(ns)
   self.assertEqual(len(calls),1)
   self.assertIn("--property=RuntimeMaxSec=2700",calls[0]);self.assertIn("--property=TimeoutStopSec=900",calls[0]);self.assertIn("--property=KillMode=mixed",calls[0])
   self.assertEqual(json.loads((root/"dungeon-bake-supervisor.json").read_text())["status"],"LAUNCHED")
 def test_owned_gpu_prevents_launch(self):
  with tempfile.TemporaryDirectory() as directory:
   ns,calls=self.namespace(pathlib.Path(directory),owner="another-operator")
   with self.assertRaisesRegex(RuntimeError,"ownership"):self.execute(ns)
   self.assertEqual(calls,[])
if __name__=="__main__":unittest.main()
