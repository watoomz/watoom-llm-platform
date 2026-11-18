from pathlib import Path
import tempfile
import unittest
from controller import State,Conflict,Unsafe
from durable_store import DurableStore
from g3h_service import Runtime
from kubernetes_api import APIError
from test_kubernetes_actuator import FakeAPI


class API(FakeAPI):
    def patch(self,*args):
        try:return super().patch(*args)
        except RuntimeError as error:raise APIError('Kubernetes rejected stale version',409) from error


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.api=API();self.probe=lambda *args:True
        self.runtime=Runtime({'state_root':str(self.root),'primary':'qwen','mesh':'mesh','stop_timeout':1,'startup_timeout':1},
             api=self.api,probe=lambda *args:self.probe(*args),identity=lambda pid:'1234')
        DurableStore(self.root/'state.json').save(State())

    def tearDown(self):self.tmp.cleanup()

    def call(self,private=True):
        return self.runtime.handle({'action':'selftest-reconciliation'},private=private,pid=123,uid=0)

    def test_metadata_only_unknown_ack_reconciles_without_replica_change(self):
        before={name:obj['spec'].copy() for name,obj in self.api.items.items()}
        result=self.call()
        self.assertEqual(result['result'],'PASS')
        self.assertTrue(result['stale_patch_rejected'])
        self.assertEqual(before,{name:obj['spec'] for name,obj in self.api.items.items()})
        self.assertEqual(self.runtime.journal.pending(),[])

    def test_router_cannot_access_privileged_selftest(self):
        with self.assertRaises(Unsafe):self.call(private=False)
        self.assertEqual(self.api.items['qwen']['metadata']['resourceVersion'],'1')

    def test_active_owner_is_preserved(self):
        DurableStore(self.root/'state.json').save(State('mesh-active','existing-job',1))
        with self.assertRaises(Conflict):self.call()
        self.assertEqual(self.api.items['qwen']['metadata']['resourceVersion'],'1')

    def test_health_failure_keeps_owner_held(self):
        calls=iter([True,False]);self.probe=lambda *args:next(calls)
        with self.assertRaises(Unsafe):self.call()
        with self.runtime.store.exclusive():
            state=self.runtime.store.load()
        self.assertEqual(state.phase,'recovery-required')
        self.assertTrue(state.uncertain)
        self.assertIsNotNone(state.owner)


if __name__=='__main__':unittest.main()
