import unittest,struct,copy,subprocess,tempfile,json
from pathlib import Path
from codec import decode,encode,CodecError

def fixture(empty=False):
 count=0 if empty else 2;names=b'neutral\0fixture\0';start=48+20*count+len(names)
 body=struct.pack('<8sIIfHHIIIIII',b'_pilC3S_',2,0,1/30,2,0,count,0,48,start,48+20*count,56+20*count)
 if count:body+=struct.pack('<IIffHBB',start,1,0,1,2,18,1)+struct.pack('<IIffHBB',start+16,1,0,1,2,20,2)
 body+=names
 if count:body+=struct.pack('<HHIHHI',0,0,1023,1,1,1023)+struct.pack('<HH4HHH4H',0,0,0,0,0,4095,1,0,0,0,0,4095)
 return struct.pack('<IIf',14,0,2/30)+b'OPAQUE_EVENTS'+struct.pack('<I',len(body))+body
class Tests(unittest.TestCase):
 def test_roundtrip_and_values(self):
  b=fixture();d=decode(b);self.assertEqual(encode(b,d),b);self.assertEqual(d['tracks'][0]['frames'][1]['values'],[-1,0,0]);self.assertEqual(d['tracks'][1]['frames'][0]['values'],[0,0,0,1])
 def test_edit_preserves_wrapper(self):
  b=fixture();d=decode(b);d['tracks'][0]['frames'][0]['values']=[0.5,0.25,-0.1];e=encode(b,d);self.assertEqual(e[:d['body_offset']],b[:d['body_offset']]);v=decode(e)['tracks'][0]['frames'][0]['values'];self.assertTrue(all(abs(a-c)<0.002 for a,c in zip(v,[0.5,0.25,-0.1])))
 def test_empty(self):
  b=fixture(True);self.assertEqual(decode(b)['tracks'],[]);self.assertEqual(encode(b,decode(b)),b)
 def test_reject_malformed(self):
  b=fixture();base=decode(b)['body_offset']
  for offset,fmt,val in [(0,'I',15),(base+8,'I',3),(base+32,'I',0),(base+48+18,'B',99),(base+16,'f',float('nan'))]:
   x=bytearray(b);struct.pack_into('<'+fmt,x,offset,val)
   with self.assertRaises((CodecError,ValueError)):decode(bytes(x))
  with self.assertRaises(CodecError):decode(b[:-1])
 def test_reject_timing_edit(self):
  b=fixture();d=decode(b);d['tracks'][0]['frames'][0]['tick']=1
  with self.assertRaises(CodecError):encode(b,d)
 def test_cli_fresh_output(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);(p/'a.clip').write_bytes(fixture());cli=Path(__file__).with_name('ts4_animation.py');args=['python3',str(cli),'decode','--source',str(p/'a.clip'),'--output',str(p/'a.json')]
   self.assertEqual(subprocess.run(args,capture_output=True).returncode,0);self.assertNotEqual(subprocess.run(args,capture_output=True).returncode,0)
if __name__=='__main__':unittest.main()
