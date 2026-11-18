import copy
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from controller import State
from durable_store import DurableStore
from g3h_service import Runtime
from test_kubernetes_actuator import FakeAPI

JOB='20261012T120000Z-12345678'


class DeferredAPI(FakeAPI):
    def __init__(self):
        super().__init__()
        self.queued=None
        self.delay_once=True
        for item in self.items.values():
            item['metadata']['generation']=1
            item['status']['observedGeneration']=1

    def patch(self,name,ops):
        if self.delay_once:
            self.delay_once=False
            self.queued=(name,copy.deepcopy(ops))
            raise TimeoutError('transport timed out; server write still in flight')
        return super().patch(name,ops)

    def complete_late(self):
        name,ops=self.queued
        return super().patch(name,ops)


class LateWriteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.api=DeferredAPI();self.live=True
        config={'state_root':str(self.root),'primary':'qwen','mesh':'mesh',
                'stop_timeout':0.1,'startup_timeout':0.1,'released_gpu_max_mib':1500}
        self.runtime=Runtime(config,api=self.api,probe=lambda *args:True,
             units=lambda job:{'ActiveState':'active' if self.live else 'inactive','MainPID':'123' if self.live else '0'},
             identity=lambda pid:'old-worker-start' if self.live else None)
        DurableStore(self.root/'state.json').save(State())
        self.call('begin',job=JOB)
        with self.assertRaises(TimeoutError):self.call('activate',job=JOB,generation=1)

    def tearDown(self):self.tmp.cleanup()

    def call(self,action,**kw):
        return self.runtime.handle({'action':action,**kw},private=True,pid=123,uid=0)

    def recover(self):
        self.live=False
        with patch('g3h_service.subprocess.run',return_value=SimpleNamespace(stdout='0',returncode=0)):
            self.call('recover',job=JOB,generation=1)

    def test_late_write_after_recovery_barrier_rejected_at_api_boundary(self):
        self.recover()
        with self.assertRaisesRegex(RuntimeError,'409'):self.api.complete_late()
        self.assertEqual(self.api.items['qwen']['spec']['replicas'],1)
        self.assertEqual(self.api.items['mesh']['spec']['replicas'],0)
        self.assertEqual(self.call('status')['phase'],'qwen-ready')
        self.assertIsNone(self.call('status')['owner'])

    def test_late_write_before_recovery_is_observed_and_reconciled(self):
        self.api.complete_late()
        self.assertEqual(self.api.items['qwen']['spec']['replicas'],0)
        self.recover()
        self.assertEqual(self.api.items['qwen']['spec']['replicas'],1)
        self.assertEqual(self.api.items['mesh']['spec']['replicas'],0)
        self.assertFalse(self.call('status')['uncertain'])

    def test_timeout_cannot_release_or_grant_another_owner(self):
        status=self.call('status')
        self.assertEqual(status['owner'],JOB)
        self.assertTrue(status['uncertain'])
        with self.assertRaises(Exception):self.call('can-use-qwen')
        self.assertEqual(len(self.runtime.journal.pending()),1)


if __name__=='__main__':unittest.main()
