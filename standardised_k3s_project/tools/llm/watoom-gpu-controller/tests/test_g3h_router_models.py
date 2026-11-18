import copy
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from controller import State,Conflict,Unsafe
from durable_store import DurableStore
from g3h_service import Runtime
from test_kubernetes_actuator import FakeAPI


class RouterModelTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.api=FakeAPI();self.api.items['other']=copy.deepcopy(self.api.items['mesh'])
        self.api.items['other']['metadata']['uid']='other-uid'
        for item in self.api.items.values():
            item['metadata']['generation']=1;item['status']['observedGeneration']=1
        self.alive=True
        config={'state_root':str(self.root),'primary':'qwen','mesh':'mesh','models':['qwen','mesh','other'],
                'startup_timeout':0.1,'stop_timeout':0.1,'released_gpu_max_mib':1500}
        self.runtime=Runtime(config,api=self.api,probe=lambda *args:True,identity=lambda pid:'1234' if self.alive else None)
        DurableStore(self.root/'state.json').save(State())

    def tearDown(self):self.tmp.cleanup()

    def call(self,action='request-model',**kw):
        with patch('g3h_service.subprocess.run',return_value=SimpleNamespace(stdout='0',returncode=0)):
            return self.runtime.handle({'action':action,**kw},private=False,pid=123,uid=0)

    def test_qwen_normal_request_has_no_scale(self):
        self.assertTrue(self.call(deployment='qwen',allow_switch=False)['allowed'])
        self.assertEqual(list((self.root/'intents').glob('*.json')),[])

    def test_preserves_existing_model_switch_and_primary_return(self):
        self.call(deployment='other',allow_switch=True)
        self.assertEqual(self.call('status')['phase'],'model-ready')
        self.assertEqual(self.api.items['qwen']['spec']['replicas'],0)
        self.assertEqual(self.api.items['other']['spec']['replicas'],1)
        self.call(deployment='qwen',allow_switch=True)
        self.assertEqual(self.call('status')['phase'],'qwen-ready')
        self.assertEqual(self.api.items['other']['spec']['replicas'],0)
        self.assertEqual(self.api.items['qwen']['spec']['replicas'],1)

    def test_actual_busy_backend_blocks_switch(self):
        self.runtime.actuator.probe=lambda name,kind:kind!="idle"
        with self.assertRaises(Conflict):self.call(deployment='other',allow_switch=True)
        self.assertEqual(self.api.items['qwen']['spec']['replicas'],1)
        self.assertEqual(list((self.root/'intents').glob('*.json')),[])

    def test_nonexplicit_switch_refused(self):
        with self.assertRaises(Conflict):self.call(deployment='other',allow_switch=False)
        self.assertEqual(self.api.items['qwen']['spec']['replicas'],1)

    def test_mesh_activation_remains_worker_only(self):
        with self.assertRaises(Unsafe):self.call(deployment='mesh',allow_switch=True)

    def test_router_request_cannot_reclaim_mesh_during_acquisition(self):
        DurableStore(self.root/'state.json').save(State('acquiring','mesh-job',1))
        (self.root/'worker.json').write_text('{"job":"mesh-job","pid":999,"start":"9999"}')
        with self.assertRaises(Conflict):self.call(deployment='qwen',allow_switch=True)
        self.assertEqual(self.api.items['qwen']['spec']['replicas'],1)

    def test_router_timeout_retains_ownership_and_unknown_outcome(self):
        self.api.fail_after_apply=True
        with self.assertRaises(TimeoutError):self.call(deployment='other',allow_switch=True)
        status=self.call('status')
        self.assertEqual(status['phase'],'recovery-required')
        self.assertEqual(status['owner_kind'],'router')
        self.assertTrue(status['uncertain'])

    def test_host_recovery_cannot_reclaim_live_router_owner(self):
        self.api.fail_after_apply=True
        with self.assertRaises(TimeoutError):self.call(deployment='other',allow_switch=True)
        status=self.call('status')
        with self.assertRaises(Unsafe):
            self.runtime.handle({'action':'recover','job':status['owner'],'generation':status['generation']},private=True,pid=0,uid=0)

    def test_ended_router_recovery_reconciles_and_restores_primary(self):
        self.api.fail_after_apply=True
        with self.assertRaises(TimeoutError):self.call(deployment='other',allow_switch=True)
        status=self.call('status');self.api.fail_after_apply=False;self.alive=False
        with patch('g3h_service.subprocess.run',return_value=SimpleNamespace(stdout='0',returncode=0)):
            self.runtime.handle({'action':'recover','job':status['owner'],'generation':status['generation']},private=True,pid=0,uid=0)
        self.assertIsNone(self.call('status')['owner'])
        self.assertEqual(self.api.items['qwen']['spec']['replicas'],1)
        self.assertEqual(self.api.items['other']['spec']['replicas'],0)


if __name__=='__main__':unittest.main()
