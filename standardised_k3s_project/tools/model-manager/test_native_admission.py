import subprocess,unittest
from unittest.mock import MagicMock
import native_admission,release_guard
from admission_errors import AdmissionBusy

def api(*responses):
 m=MagicMock();m.request.side_effect=list(responses);return m

class NativeIdlePreflight(unittest.TestCase):
 def test_dropped_transport_keeps_image_queued(self):
  with self.assertRaises(AdmissionBusy):
   native_admission.check_native_idle(api(release_guard.UnsafeRelease("Maintenance command failed: http.client readline")))
 def test_probe_timeout_keeps_image_queued(self):
  with self.assertRaises(AdmissionBusy):
   native_admission.check_native_idle(api({"data":{"version":1,"supported":True,"held":False,"leases":0}},subprocess.TimeoutExpired("kubectl",40)))
 def test_contract_failure_still_fails(self):
  with self.assertRaises(release_guard.UnsafeRelease) as raised:
   native_admission.check_native_idle(api({"data":{"version":2,"supported":True,"held":False,"leases":0}},{"data":{}}))
  self.assertNotIsInstance(raised.exception,AdmissionBusy)
 def test_other_unsafe_release_is_not_downgraded(self):
  with self.assertRaises(release_guard.UnsafeRelease) as raised:
   native_admission.check_native_idle(api(release_guard.UnsafeRelease("Maintenance requires one identified app pod")))
  self.assertNotIsInstance(raised.exception,AdmissionBusy)
 def test_lease_held_is_busy_without_active_probe(self):
  probe=api({"data":{"version":1,"supported":True,"held":False,"leases":1}})
  with self.assertRaises(AdmissionBusy):native_admission.check_native_idle(probe)
  self.assertEqual(probe.request.call_count,1)
 def test_idle_passes(self):
  native_admission.check_native_idle(api({"data":{"version":1,"supported":True,"held":False,"leases":0}},{"data":{}}))

if __name__=="__main__":unittest.main()
