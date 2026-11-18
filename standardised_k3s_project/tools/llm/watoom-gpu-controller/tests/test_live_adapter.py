import unittest
from unittest.mock import patch
from live_adapter import LiveActuator, LiveAdapterError

class LiveAdapterTests(unittest.TestCase):
    def test_requires_fencing(self):
        with self.assertRaises(LiveAdapterError):
            LiveActuator(base_url='https://kubernetes.default.svc',namespace='llama-cpp',token='t',ca_file='/ca',primary='q',mesh='m',journal_root='/tmp/ignore',generation=1)
    def test_requires_quiescence(self):
        with self.assertRaises(LiveAdapterError):
            LiveActuator(base_url='https://kubernetes.default.svc',namespace='llama-cpp',token='t',ca_file='/ca',primary='q',mesh='m',journal_root='/tmp/ignore',generation=1,legacy_fenced=True)
    def test_does_not_contact_cluster_on_construct(self):
        with patch('live_adapter.DeploymentAPI') as api, patch('live_adapter.IntentJournal') as journal:
            a=LiveActuator(base_url='https://kubernetes.default.svc',namespace='llama-cpp',token='t',ca_file='/ca',primary='q',mesh='m',journal_root='/tmp/ignore',generation=1,legacy_fenced=True,quiesced=True)
            self.assertEqual(a.primary,'q')
            api.return_value.get.assert_not_called()
            api.return_value.patch.assert_not_called()
    def test_invalid_generation(self):
        with self.assertRaises(LiveAdapterError):
            LiveActuator(base_url='https://kubernetes.default.svc',namespace='llama-cpp',token='t',ca_file='/ca',primary='q',mesh='m',journal_root='/tmp/ignore',generation=0,legacy_fenced=True,quiesced=True)
if __name__=='__main__':unittest.main()
