import unittest,tempfile,pathlib,json,hashlib,zipfile,stat,sys
from test_broker import QueueTests
from broker import Broker
import completion_outbox as outbox
from game_contract import validate_game
from game_runner import unpack
class CaptureSceneContract(unittest.TestCase):
 def base(self,tmp):
  folder=tmp/'.opencode/rig-job-snapshots';folder.mkdir(parents=True,exist_ok=True);source=folder/('a'*64+'.zip');source.write_bytes(b'fixture')
  return {'kind':'godot','mode':'game','operation':'capture-scene','project':str(tmp),'source':str(source),
          'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'source_fingerprint':'b'*64,
          'job':'fixture-job','scene':'scenes/fixture.tscn','output_directory':'.opencode/captures/fixture',
          'images':['a.png'],'deadline_sec':900}
 def test_valid_capture_scene_manifest_passes(self):
  with tempfile.TemporaryDirectory() as d:
   tmp=pathlib.Path(d);v=self.base(tmp);validate_game(v,[str(tmp)])
 def test_missing_job_field_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   tmp=pathlib.Path(d);v=self.base(tmp);del v['job']
   with self.assertRaises(ValueError):validate_game(v,[str(tmp)])
 def test_scene_outside_tscn_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   tmp=pathlib.Path(d);v=self.base(tmp);v['scene']='scenes/fixture.gd'
   with self.assertRaises(ValueError):validate_game(v,[str(tmp)])
 def test_scene_path_traversal_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   tmp=pathlib.Path(d);v=self.base(tmp);v['scene']='../escape.tscn'
   with self.assertRaises(ValueError):validate_game(v,[str(tmp)])
 def test_output_directory_outside_captures_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   tmp=pathlib.Path(d);v=self.base(tmp);v['output_directory']='scripts/evil'
   with self.assertRaises(ValueError):validate_game(v,[str(tmp)])
 def test_deadline_sec_out_of_range_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   tmp=pathlib.Path(d);v=self.base(tmp);v['deadline_sec']=3000
   with self.assertRaises(ValueError):validate_game(v,[str(tmp)])
 def test_duplicate_image_names_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   tmp=pathlib.Path(d);v=self.base(tmp);v['images']=['a.png','a.png']
   with self.assertRaises(ValueError):validate_game(v,[str(tmp)])
 def test_plain_capture_manifest_unaffected_by_the_new_schema(self):
  with tempfile.TemporaryDirectory() as d:
   tmp=pathlib.Path(d);folder=tmp/'.opencode/rig-job-snapshots';folder.mkdir(parents=True);source=folder/('a'*64+'.zip');source.write_bytes(b'x')
   v={'kind':'godot','mode':'game','operation':'capture','project':str(tmp),'source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'source_fingerprint':'c'*64}
   validate_game(v,[str(tmp)])

class AsyncQueue(QueueTests):
 def game(self):
  folder=self.project/'.opencode/rig-job-snapshots';folder.mkdir(parents=True,exist_ok=True);source=folder/('a'*64+'.zip');source.write_bytes(b'operator-fixture-frozen-input')
  return {'kind':'godot','mode':'game','operation':'import','project':str(self.project),'source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'source_fingerprint':'b'*64}
 def test_default_consumer_does_not_steal_game(self):
  game=self.game();identity=self.broker.admit(game,[str(self.project)],{'operator_fixture':True,'request_id':'fixture-game'});self.assertIsNone(self.broker.operation({'op':'claim'},'legacy')['job']);claim=self.broker.operation({'op':'claim','job_kind':'godot'},'rig-game');self.assertEqual(claim['job'],identity)
 def test_both_kinds_queue_while_one_slot_busy(self):
  first=self.claim();game=self.game();second=self.broker.admit(game,[str(self.project)],{'operator_fixture':True,'request_id':'fixture-game'});self.assertIsNone(self.broker.operation({'op':'claim','job_kind':'godot'},'rig-game')['job']);self.assertEqual(self.broker.db.execute('select state from jobs where id=?',(second,)).fetchone()[0],'QUEUED');self.rpc('failed',first,error='operator fixture completion');self.assertEqual(self.broker.operation({'op':'claim','job_kind':'godot'},'rig-game')['job'],second)
 def test_pause_requires_same_token_explicit_resume(self):
  claim=self.claim();self.assertEqual(self.rpc('pause',claim)['state'],'PAUSED');self.broker.expire();self.broker.db.commit();self.assertEqual(self.broker.db.execute('select state from jobs where id=?',(claim['job'],)).fetchone()[0],'PAUSED')
  with self.assertRaises(ValueError):self.rpc('complete',claim,files={})
  with self.assertRaises(ValueError):self.broker.operation({'op':'resume','job':claim['job'],'token':'wrong'},'rig-stage')
  self.assertEqual(self.rpc('resume',claim)['state'],'QUEUED');nextclaim=self.broker.operation({'op':'claim'},'rig-stage');self.assertEqual(nextclaim['job'],claim['job']);self.assertNotEqual(nextclaim['token'],claim['token'])
 def test_game_does_not_accept_commands_or_mutated_archive(self):
  game=self.game()
  with self.assertRaises(ValueError):validate_game({**game,'command':'unsafe'},[str(self.project)])
  pathlib.Path(game['source']).write_bytes(b'mutated')
  with self.assertRaises(ValueError):validate_game(game,[str(self.project)])
class CaptureAdmission(unittest.TestCase):
 def test_completion_helper_does_not_shadow_capture_enqueue(self):
  import native_bridge as bridge,types
  sys.path.append('/data/github/watoom-standardised-homelab/standardised_k3s_project/tools/watoom-code')
  import asset_capture_bridge as legacy
  with tempfile.TemporaryDirectory() as d:
   before=(bridge.enqueue,bridge.row,legacy.PRIVATE,legacy.REPORTS,legacy.cancelled);calls=[];published=[]
   try:
    legacy.PRIVATE=pathlib.Path(d);legacy.REPORTS=pathlib.Path(d);legacy.cancelled=lambda *a,**k:False
    bridge.enqueue=lambda request,manifest:calls.append(request) or 'fixture-external-job'
    bridge.row=lambda job:{'state':'QUEUED'}
    api=types.SimpleNamespace(ns='isolated-stage',name='app',request=lambda *a,**k:{'data':{}})
    request={'request_id':'c'*64,'project':d,'session_id':'ses_fixture','job':'capture-fixture'}
    self.assertTrue(bridge.dispatch(api,request,{},lambda *a,**k:published.append((a,k)),{}))
    self.assertEqual(len(calls),1);self.assertEqual(published[-1][0][1],'QUEUED')
   finally:bridge.enqueue,bridge.row,legacy.PRIVATE,legacy.REPORTS,legacy.cancelled=before
class ZipBoundary(unittest.TestCase):
 def run_case(self,name):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d);archive=p/'input.zip'
   with zipfile.ZipFile(archive,'w') as z:z.writestr(name,'unsafe')
   with self.assertRaises(ValueError):unpack(archive,p/'project')
 def test_parent_escape(self):self.run_case('../escape')
 def test_drive_and_ads(self):self.run_case('c:escape')
 def test_windows_device(self):self.run_case('assets/CON.png')
 def test_case_collision(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)
   with zipfile.ZipFile(p/'input.zip','w') as z:z.writestr('Scripts/a.gd','a');z.writestr('scripts/A.gd','b')
   with self.assertRaises(ValueError):unpack(p/'input.zip',p/'project')
 def test_mixed_case_verified_closure(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d);raw=b'verified';name='Scripts/Fixture.gd'
   with zipfile.ZipFile(p/'input.zip','w') as z:z.writestr(name,raw);z.writestr('.rig-input-manifest.json',json.dumps({'source_fingerprint':'a'*64,'files':{name:hashlib.sha256(raw).hexdigest()}}))
   self.assertEqual(unpack(p/'input.zip',p/'project')['source_fingerprint'],'a'*64)
class Notification(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.before=outbox.ROOT;outbox.ROOT=pathlib.Path(self.tmp.name)
 def tearDown(self):outbox.ROOT=self.before;self.tmp.cleanup()
 def api(self,offline=False,interrupted=False):
  class API:
   ns='watoom-code-rig-jobs';name='watoom-code';calls=[]
   def request(this,path,body=None):
    if body is None:return {'data':{'idleOutcome':'interrupted' if interrupted else 'succeeded'}}
    this.calls.append((path,body))
    if offline:raise TimeoutError('response lost')
    return {'data':{'id':body['id']}}
  return API()
 def enqueue(self):outbox.enqueue({'request_id':'a'*64,'job':'fixture'},'ses_fixture','existing job finished',kind='godot',application={'namespace':'watoom-code-rig-jobs','name':'watoom-code'})
 def test_connection_loss_retries_same_input_once(self):
  self.enqueue();a=self.api(offline=True);self.assertEqual(outbox.drain(a),0);id=a.calls[0][1]['id'];b=self.api();self.assertEqual(outbox.drain(b),1);self.assertEqual(b.calls[0][1]['id'],id);self.assertEqual(b.calls[0][1]['delivery'],'queue');self.assertEqual(outbox.drain(b),0)
 def test_interrupted_coordinator_is_not_woken(self):self.enqueue();a=self.api(interrupted=True);self.assertEqual(outbox.drain(a),1);self.assertFalse(a.calls[0][1]['resume'])
 def test_other_application_not_notified(self):self.enqueue();a=self.api();a.ns='other';self.assertEqual(outbox.drain(a),0);self.assertEqual(a.calls,[])
if __name__=='__main__':unittest.main()
