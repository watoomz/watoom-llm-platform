import base64, hashlib, json, pathlib, tempfile, time, unittest,struct
from broker import Broker, validate

class QueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.base=pathlib.Path(self.tmp.name)
        self.project=self.base/'project';self.root=self.base/'private'
        for folder in ['assets','incoming/a','status','results']:(self.project/folder).mkdir(parents=True)
        for folder in ['blobs','outputs']:(self.root/folder).mkdir(parents=True)
        self.source=self.project/'assets'/'cube.glb';raw=json.dumps({'asset':{'version':'2.0'}}).encode();raw+=b' '*((-len(raw))%4);self.source.write_bytes(b'glTF'+struct.pack('<III',2,20+len(raw),len(raw))+struct.pack('<I',0x4e4f534a)+raw)
        self.spec={'schema':1,'mode':'still','source':str(self.source.resolve()),'source_sha256':hashlib.sha256(self.source.read_bytes()).hexdigest(),'resolution':[64,64]}
        (self.project/'incoming/a/request.json').write_text(json.dumps(self.spec))
        self.broker=Broker(self.root,self.project)
    def tearDown(self):self.broker.db.close();self.tmp.cleanup()
    def claim(self):self.broker.scan();return self.broker.operation({'op':'claim'},'rig-stage')
    def rpc(self,op,claim,**values):return self.broker.operation({'op':op,'job':claim['job'],'token':claim['token'],**values},'rig-stage')
    def test_duplicate_scan_and_one_slot(self):
        c=self.claim();self.broker.scan();self.assertEqual(self.broker.db.execute('select count(*) from jobs').fetchone()[0],1)
        self.assertIsNone(self.broker.operation({'op':'claim'},'other')['job'])
        self.assertEqual(base64.b64decode(self.rpc('fetch',c,offset=0)['data']),self.source.read_bytes())
    def test_expiry_requires_reconciliation_no_replay(self):
        c=self.claim();self.broker.db.execute('update jobs set expires=0');self.broker.db.commit()
        self.assertIsNone(self.broker.operation({'op':'claim'},'rig-stage')['job'])
        self.assertEqual(self.broker.db.execute('select state from jobs').fetchone()[0],'RECONCILIATION_REQUIRED')
        with self.assertRaises(ValueError):self.rpc('heartbeat',c)
    def test_original_source_change_rejects_completion(self):
        c=self.claim();self.source.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Source hash mismatch'):self.rpc('complete',c,files={})
    def test_token_worker_and_path_rejection(self):
        c=self.claim()
        with self.assertRaises(ValueError):self.broker.operation({'op':'heartbeat','job':c['job'],'token':c['token']},'imposter')
        with self.assertRaises(ValueError):self.rpc('upload',c,name='../escape',offset=0,data='AA==')
        with self.assertRaises(ValueError):self.rpc('upload',c,name='capture.png',offset=1,data='AA==')
    def test_source_hash_and_command_rejection(self):
        with self.assertRaises(ValueError):validate({**self.spec,'script':'evil.py'},self.project)
        self.source.write_bytes(b'changed')
        with self.assertRaises(ValueError):validate(self.spec,self.project)
    def test_receipt_requires_hashes_windows_boundary_and_pixels(self):
        c=self.claim();receipt={'source_sha256':self.spec['source_sha256'],'platform':'Windows','memory_limit_verified':True,'engine':'5.2.1 LTS','status':'CAPTURED_VISUAL_REVIEW_PENDING','images':['capture.png']}
        raw=json.dumps(receipt).encode();self.rpc('upload',c,name='worker.json',offset=0,data=base64.b64encode(raw).decode())
        files={'worker.json':hashlib.sha256(raw).hexdigest()}
        with self.assertRaises(ValueError):self.rpc('complete',c,files=files)
        raw=bytes([137,80,78,71,13,10,26,10])+struct.pack('>I',13)+b'IHDR'+struct.pack('>II',64,64);self.rpc('upload',c,name='capture.png',offset=0,data=base64.b64encode(raw).decode());files['capture.png']=hashlib.sha256(raw).hexdigest()
        result=self.rpc('complete',c,files=files);self.assertEqual(result['state'],'COMPLETED_VISUAL_REVIEW_PENDING')
        self.broker.scan();self.assertFalse(json.loads((self.project/'status/a.json').read_text())['receipt']['visual_acceptance'])
        self.assertIsNone(self.broker.operation({'op':'claim'},'rig-stage')['job'])
    def test_native_only_claim_preserves_manual_queue(self):
        self.broker.scan()
        self.assertIsNone(self.broker.operation({'op':'claim','native_only':True},'rig-stage')['job'])
        native={'request_id':'isolated-native-fixture'}
        identity=self.broker.admit(self.spec,[str(self.project/'assets')],native)
        claim=self.broker.operation({'op':'claim','native_only':True},'rig-stage')
        self.assertEqual(claim['job'],identity)
        self.assertEqual(self.broker.db.execute("select count(*) from jobs where state='QUEUED' and native='null'").fetchone()[0],1)
    def test_native_cancellation_binding_and_claim_race(self):
        import subprocess,sys
        native={'request_id':'isolated-native-fixture'}
        identity=self.broker.admit(self.spec,[str(self.project/'assets')],native)
        cmd=[sys.executable,str(pathlib.Path(__file__).with_name('broker.py')),'--root',str(self.root),'--project',str(self.project),'--cancel-native']
        bad=subprocess.run(cmd,input=json.dumps({'job':identity,'native':{'request_id':'wrong'}}),text=True,capture_output=True)
        self.assertNotEqual(bad.returncode,0)
        good=subprocess.run(cmd,input=json.dumps({'job':identity,'native':native}),text=True,capture_output=True)
        self.assertEqual(good.returncode,0,good.stdout);self.assertEqual(json.loads(good.stdout)['state'],'CANCELLED')
        self.assertIsNone(self.broker.operation({'op':'claim','native_only':True},'rig-stage')['job'])
        other=self.broker.admit(self.spec,[str(self.project/'assets')],{'request_id':'second-native-fixture'})
        claim=self.broker.operation({'op':'claim','native_only':True},'rig-stage')
        claimed=subprocess.run(cmd,input=json.dumps({'job':other,'native':{'request_id':'second-native-fixture'}}),text=True,capture_output=True)
        self.assertEqual(json.loads(claimed.stdout)['state'],'CLAIMED')
        self.assertTrue(self.rpc('heartbeat',claim)['alive'])
if __name__=='__main__':unittest.main()
