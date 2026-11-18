import unittest,tempfile,pathlib,json
from unittest.mock import patch
from broker import Broker
from store import Store
from admission_errors import AdmissionBusy
class Scheduling(unittest.TestCase):
 def test_preflight_busy_is_retryable_before_artifacts(self):
  for status in [dict(owner=None,uncertain=False,active_requests=1),dict(owner='other',uncertain=False,active_requests=0)]:
   with tempfile.TemporaryDirectory() as tmp:
    store=Store(pathlib.Path(tmp)/'catalog.sqlite');broker=Broker({'state':tmp,'controller_socket':'fixture'},store)
    with patch('native_admission.check_native_idle'),patch('maintenance_guard.Maintenance'),patch('broker.os.geteuid',return_value=0),patch('broker.rpc',return_value=status),patch.object(broker,'artifacts') as artifacts:
     with self.assertRaises(AdmissionBusy):broker._dispatch('generate',{'id':'a'*64})
     artifacts.assert_not_called()
    store.close()
 def test_uncertainty_is_not_retryable(self):
  with tempfile.TemporaryDirectory() as tmp:
   store=Store(pathlib.Path(tmp)/'catalog.sqlite');broker=Broker({'state':tmp,'controller_socket':'fixture'},store)
   with patch('native_admission.check_native_idle'),patch('maintenance_guard.Maintenance'),patch('broker.os.geteuid',return_value=0),patch('broker.rpc',return_value=dict(owner=None,uncertain=True,active_requests=1)):
    with self.assertRaises(ValueError) as error:broker._dispatch('generate',{'id':'a'*64})
    self.assertNotIsInstance(error.exception,AdmissionBusy)
   store.close()
if __name__=='__main__':unittest.main()
