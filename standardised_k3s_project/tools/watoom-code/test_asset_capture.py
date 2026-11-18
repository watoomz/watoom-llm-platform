import unittest,tempfile,pathlib,json,copy,sqlite3
from asset_capture_contract import manifest,native_proof,sha
from asset_capture_bridge import identity,cancelled
class Contract(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name);self.source=self.root/'source.blend';self.source.write_bytes(b'fixture');self.v={'schema':1,'mode':'still','source':str(self.source),'source_sha256':sha(self.source)}
 def tearDown(self):self.tmp.cleanup()
 def test_valid(self):self.assertEqual(manifest(self.v,[self.root]),self.v)
 def test_paths_and_code(self):
  for key,val in [('script','evil'),('source','/etc/passwd'),('source_sha256','unknown'),('samples',1000),('resolution',[8192,8192]),('frames',[1,121]),('pose',[{'bad':'entry'}]),('visibility',{'show':[{}]}),('output_format','mp4')]:
   with self.subTest(key=key):
    v=copy.deepcopy(self.v);v[key]=val
    with self.assertRaises(ValueError):manifest(v,[self.root])
 def test_video_requirements(self):
  for resolution,frames in [([129,192],[1,4]),([128,192],[1,1])]:
   v=copy.deepcopy(self.v);v.update(mode='animation',resolution=resolution,frames=frames,output_format='mp4')
   with self.assertRaises(ValueError):manifest(v,[self.root])
  v=copy.deepcopy(self.v);v.update(mode='animation',resolution=[128,192],frames=[1,4],output_format='mp4');self.assertEqual(manifest(v,[self.root]),v)
 def test_symlink(self):
  p=self.root/'link.blend';p.symlink_to(self.source);self.v['source']=str(p)
  with self.assertRaises(ValueError):manifest(self.v,[self.root])
 def test_native_proof(self):
  v={'request_id':'r','project':'p','job':'j','manifest_sha256':'h','call_id':'call'}
  m={'content':[{'type':'tool','name':'watoom_asset_capture','id':'call','state':{'status':'completed','input':{'action':'request','job':'j'},'metadata':v.copy()}}]}
  self.assertTrue(native_proof(m,v));m['content'][0]['state']['metadata']['manifest_sha256']='forged';self.assertFalse(native_proof(m,v))
 def test_stable_identity(self):
  v={k:k for k in ('project','job','manifest_sha256','session_id','message_id','call_id')};self.assertEqual(identity(v),identity(v));before=identity(v);v['manifest_sha256']='different';self.assertNotEqual(before,identity(v))
class Cancel(unittest.TestCase):
 def test_parent_interrupt_and_missing(self):
  with tempfile.TemporaryDirectory() as root:
   db=pathlib.Path(root)/'app.sqlite'
   with sqlite3.connect(db) as c:
    c.execute('create table session_v2(id text,parent_id text,idle_outcome text)');c.executemany('insert into session_v2 values(?,?,?)',[('root',None,'completed'),('child','root','completed')])
   self.assertFalse(cancelled('child',db));self.assertTrue(cancelled('missing',db))
   with sqlite3.connect(db) as c:c.execute("update session_v2 set idle_outcome='interrupted' where id='root'")
   self.assertTrue(cancelled('child',db))
   self.assertFalse(cancelled('child',db,active_sessions={'root'}))
   self.assertTrue(cancelled('child',db,active_sessions={'child'}))
   self.assertTrue(cancelled('missing',db,active_sessions={'missing'}))
if __name__=='__main__':unittest.main()
