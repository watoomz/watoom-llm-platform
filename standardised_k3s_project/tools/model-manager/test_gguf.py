import struct,tempfile,unittest
from pathlib import Path
from gguf_header import context_limit,HeaderError
class Header(unittest.TestCase):
 def test_context_and_invalid_header(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"m.gguf";key=b"llama.context_length"
   p.write_bytes(b"GGUF"+struct.pack("<IQQQ",3,0,1,len(key))+key+struct.pack("<II",4,32768))
   self.assertEqual(context_limit(p),32768)
   p.write_bytes(b"not executable model data")
   with self.assertRaises(HeaderError):context_limit(p)
 def test_oversized_metadata_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"m.gguf";p.write_bytes(b"GGUF"+struct.pack("<IQQ",3,0,100001))
   with self.assertRaises(HeaderError):context_limit(p)
