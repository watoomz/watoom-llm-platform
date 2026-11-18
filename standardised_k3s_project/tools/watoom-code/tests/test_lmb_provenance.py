import unittest,tempfile,pathlib,sys,json,os,copy
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import lmb_provenance as p
class Provenance(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=pathlib.Path(self.tmp.name);self.file=self.root/'BP.uasset';self.file.write_bytes(b'AAAA');self.rows=p.native_input_files(self.root)
  self.request=dict(request_id='a'*64,job='one',operation='lmb-qualify',source_fingerprint='b'*64)
  self.receipt={**self.request,'native_input_files':self.rows,'native_input_sha256':p.native_input_sha256(self.rows)}
 def test_production_js_manifest_execution(self):
  guard=pathlib.Path(__file__).resolve().parents[3]/'ansible/roles/watoom-code/files/coordinator-guard/index.js'
  manifest=p.coordinator_manifest(self.root,guard)
  self.assertEqual(len(manifest['rows']),2)
  self.assertEqual(len(manifest['fingerprint']),64)
  self.assertIn('["BP.uasset","4",',manifest['serialized'])
 def test_cli_report_private_and_exclusive(self):
  guard=pathlib.Path(__file__).resolve().parents[3]/'ansible/roles/watoom-code/files/coordinator-guard/index.js'
  output=self.root/'report.json'
  with __import__('unittest.mock',fromlist=['patch']).patch.object(sys,'argv',['provenance','--project',str(self.root),'--guard',str(guard),'--native-source',str(self.root),'--output',str(output)]):
   self.assertEqual(p.main(),0)
   self.assertEqual(output.stat().st_mode & 0o777,0o600)
   with self.assertRaises(FileExistsError):p.main()
 def test_unchanged(self):self.assertEqual(p.receipt_report(self.receipt,self.request,self.rows)['status'],'PASS')
 def test_identity_mismatch(self):
  for key in p.IDENTITY_FIELDS:
   receipt=copy.deepcopy(self.receipt);receipt[key]='wrong';self.assertEqual(p.receipt_report(receipt,self.request,self.rows)['status'],'FAIL')
 def test_historical(self):
  report=p.receipt_report({'status':'QUALIFIED_NATIVE_COMPILE_ONLY'},self.request,self.rows);self.assertEqual(report['status'],'WARNING');self.assertGreaterEqual(len(report['warnings']),5)
 def test_changed_raw_same_metadata(self):
  st=self.file.stat();self.file.write_bytes(b'BBBB');os.utime(self.file,ns=(st.st_atime_ns,st.st_mtime_ns));self.assertEqual(self.file.stat().st_size,st.st_size);new=p.native_input_files(self.root);self.assertNotEqual(p.native_input_sha256(new),p.native_input_sha256(self.rows));self.assertEqual(p.receipt_report(self.receipt,self.request,new)['status'],'FAIL')
 def test_metadata_only_native_identity(self):
  st=self.file.stat();os.utime(self.file,ns=(st.st_atime_ns,st.st_mtime_ns+1));self.assertEqual(p.native_input_sha256(self.rows),p.native_input_sha256(p.native_input_files(self.root)))
 def test_missing(self):self.file.unlink();self.assertEqual(p.receipt_report(self.receipt,self.request,[])['status'],'FAIL')
 def test_added(self):
  (self.root/'added').write_text('x');self.assertEqual(p.receipt_report(self.receipt,self.request,p.native_input_files(self.root))['status'],'FAIL')
 def test_symlink(self):
  (self.root/'link').symlink_to(self.file)
  with self.assertRaises(ValueError):p.native_input_files(self.root)
 def test_duplicate(self):
  with self.assertRaises(ValueError):p.native_input_sha256(self.rows+self.rows)
 def test_digest_tamper(self):
  self.receipt['native_input_sha256']='f'*64;self.assertEqual(p.receipt_report(self.receipt,self.request,self.rows)['status'],'FAIL')
 def test_missing_native_source(self):
  with self.assertRaises(ValueError):p.native_input_files(self.root/'missing')
if __name__=='__main__':unittest.main()
