"""Isolated native qualifier receipt tests; subprocesses are mocked, Unreal never runs."""
import unittest,pathlib,tempfile,runpy,sys,json,os
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[3]
CANDIDATES=os.environ.get('WATOOM_LMB_CANDIDATE_DIR')
QUALIFIER=pathlib.Path(CANDIDATES)/'qualify-landscape.py' if CANDIDATES else ROOT/'tools/fab/qualify-landscape.py'
@unittest.skipUnless('native_input_files' in QUALIFIER.read_text(), 'Pending approval: use WATOOM_LMB_CANDIDATE_DIR for isolated release tests')
class NativeReceipts(unittest.TestCase):
 def exercise(self,change=False,missing=False):
  with tempfile.TemporaryDirectory(prefix='lmb-native-fixture-',dir='/data/ai/helper-scripts/reports') as folder:
   root=pathlib.Path(folder);source=root/'source';bp=source/'Content/LandscapeMeshBuilder/Blueprints/BP_LandscapeMeshBuilder.uasset';bp.parent.mkdir(parents=True);bp.write_bytes(b'AAAA')
   (source/'Config').mkdir();(source/'Config/DefaultEngine.ini').write_text('fixture')
   (source/'LandscapeMeshBuilder.uproject').write_text('{"Plugins":[]}')
   if missing:bp.unlink()
   template=root/'template.json';template.write_text(json.dumps({'spec':{'template':{'spec':{'volumes':[{'name':n,'hostPath':{}} for n in ['engine','content','job']],'containers':[{}]}}}}))
   out=root/'receipt';code=QUALIFIER.read_text().replace("/data/ai/assets/fab/landscape-mesh-builder-48364dff",str(source)).replace('/data/ai/helper-scripts/reports/remaining-acceptance-20261017T202822Z/pack-9cdd1f83/job.json',str(template))
   def run(args,**kw):
    if args[:2]==['kubectl','create']:
     (out/'native-result.json').write_text('{"status":"NATIVE_COMPILE_PASS"}')
     if change:
      st=bp.stat();bp.write_bytes(b'BBBB');os.utime(bp,ns=(st.st_atime_ns,st.st_mtime_ns))
    return type('Completed',(),{'stdout':'fixture','stderr':'','returncode':0})()
   original=pathlib.Path.read_text
   def read(path,*a,**kw):
    if str(path)=='/proc/meminfo':return 'MemAvailable: 16000000 kB'
    return original(path,*a,**kw)
   with patch.object(sys,'argv',[str(QUALIFIER),'--evidence',str(out),'--memory-gib','4']),patch('subprocess.run',side_effect=run),patch('subprocess.check_output',return_value=b'{"status":{"succeeded":1}}'),patch('os.chown'),patch.object(pathlib.Path,'read_text',read):
    if missing:
     with self.assertRaises(AssertionError):exec(compile(code,str(QUALIFIER),'exec'),{'__file__':str(ROOT/'tools/fab/qualify-landscape.py'),'__name__':'__main__'})
     return
    with self.assertRaises(SystemExit) as exit:exec(compile(code,str(QUALIFIER),'exec'),{'__file__':str(ROOT/'tools/fab/qualify-landscape.py'),'__name__':'__main__'})
    receipt=json.loads((out/'qualification.json').read_text());self.assertEqual(exit.exception.code,1 if change else 0);self.assertEqual(receipt['source_unchanged'],not change);self.assertEqual(len(receipt['native_input_files']),3);self.assertEqual(len(receipt['native_input_sha256']),64)
    self.assertEqual(receipt['status'],'NATIVE_SOURCE_CHANGED' if change else 'NATIVE_COMPILE_PASS')
 def test_native_receipt_records_external_hashes(self):self.exercise()
 def test_native_same_metadata_changed_contents_fails(self):self.exercise(change=True)
 def test_missing_blueprint_prevents_launch(self):self.exercise(missing=True)
if __name__=='__main__':unittest.main()
