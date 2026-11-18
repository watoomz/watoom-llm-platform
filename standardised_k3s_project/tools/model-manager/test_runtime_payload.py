import tempfile,json,unittest,os
from pathlib import Path
from unittest.mock import patch
from runtime_payload import verify,sha
class Payload(unittest.TestCase):
 def test_manifest_and_read_only_root(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);runtime=root/"payload";runtime.mkdir();(runtime/"bin").mkdir();(runtime/"bin/python").write_text("fixture")
   manifest=root/"manifest.json";manifest.write_text("{}");manifest.chmod(0o644)
   value={"path":str(runtime),"manifest":str(manifest),"sha256":sha(manifest)}
   with patch("runtime_payload.TOOLCHAIN",root):
    self.assertEqual(verify(value),runtime)
    runtime.chmod(0o777)
    with self.assertRaises(ValueError):verify(value)
    runtime.chmod(0o755);manifest.write_text("changed")
    with self.assertRaises(ValueError):verify(value)
 def test_disk_pressure_blocks_before_hardware_work(self):
  from broker import Broker
  from store import Store
  with tempfile.TemporaryDirectory() as d:
   store=Store(Path(d)/"catalog.sqlite");broker=Broker({"state":str(Path(d)/"broker")},store)
   with patch.object(broker,"kube",return_value={"items":[{"status":{"conditions":[{"type":"DiskPressure","status":"True"}]}}]}),patch("broker.shutil.disk_usage",return_value=type("D",(),{"free":100*1024**3})()):
    with self.assertRaisesRegex(ValueError,"disk pressure"):broker.hardware_admission({"kind":"gguf"})
   store.close()
