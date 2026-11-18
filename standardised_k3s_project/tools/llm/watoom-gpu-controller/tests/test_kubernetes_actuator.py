import copy
from pathlib import Path
import tempfile
import unittest
from kubernetes_actuator import KubernetesActuator,IntentJournal,MutationUnsafe,FENCE

class FakeAPI:
    def __init__(self):
        self.items={n:{'metadata':{'uid':n+'-uid','resourceVersion':'1','annotations':{}},'spec':{'replicas':1 if n=='qwen' else 0},'status':{'replicas':1 if n=='qwen' else 0,'readyReplicas':1 if n=='qwen' else 0}} for n in ('qwen','mesh')}
        self.fail_after_apply=False
        self.before_apply=None
    def get(self,name):return copy.deepcopy(self.items[name])
    def patch(self,name,patch):
        if self.before_apply is not None:
            fn=self.before_apply;self.before_apply=None;fn()
        obj=self.items[name]
        for p in patch:
            if p['op']=='test':
                key=p['path'].split('/')[-1]
                if obj['metadata'][key]!=p['value']:raise RuntimeError('409 Conflict')
        for p in patch:
            if p['op']=='add':obj['metadata']['annotations']=p['value']
            if p['op']=='replace':
                obj['spec']['replicas']=p['value'];obj['status']['replicas']=p['value'];obj['status']['readyReplicas']=p['value']
        obj['metadata']['resourceVersion']=str(int(obj['metadata']['resourceVersion'])+1)
        if self.fail_after_apply:raise TimeoutError('simulated lost response after commit')
        return self.get(name)

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.api=FakeAPI();self.j=IntentJournal(Path(self.tmp.name)/'ops')
        self.a=KubernetesActuator(self.api,self.j)
    def test_scale_ack(self):
        self.a.scale('mesh',1,1)
        self.assertTrue(self.a.healthy('mesh'))
        self.assertEqual(self.j.pending(),[])
    def test_stale_generation_rejected(self):
        with self.assertRaises(MutationUnsafe):self.a.scale('mesh',1,2)
    def test_unknown_outcome_cannot_retry(self):
        self.api.fail_after_apply=True
        with self.assertRaises(TimeoutError):self.a.scale('mesh',1,1)
        with self.assertRaises(MutationUnsafe):self.a.scale('qwen',0,1)
        self.api.fail_after_apply=False
        self.assertTrue(self.a.fence_and_reconcile(1))
        self.assertEqual(self.j.pending(),[])
    def test_old_pending_patch_after_barrier_rejected(self):
        old=self.api.get('mesh')
        self.api.fail_after_apply=True
        with self.assertRaises(TimeoutError):self.a.scale('mesh',1,1)
        self.api.fail_after_apply=False
        self.assertTrue(self.a.fence_and_reconcile(1))
        stale=[{'op':'test','path':'/metadata/uid','value':old['metadata']['uid']},{'op':'test','path':'/metadata/resourceVersion','value':old['metadata']['resourceVersion']}]
        with self.assertRaisesRegex(RuntimeError,'409'):self.api.patch('mesh',stale)
    def test_old_pending_write_commits_before_barrier(self):
        self.api.fail_after_apply=True
        with self.assertRaises(TimeoutError):self.a.scale('mesh',1,1)
        self.api.fail_after_apply=False
        self.assertTrue(self.a.fence_and_reconcile(1))
        self.assertTrue(self.a.healthy('mesh'))
    def test_corrupt_intent_fails_closed(self):
        (self.j.root/'corrupt.json').write_text('{')
        with self.assertRaises(MutationUnsafe):self.a.fence_and_reconcile(1)
    def test_not_an_unauthorized_writer_fence(self):
        # Model an old client that patches spec.replicas without a resourceVersion test.
        self.a.scale('mesh',1,1)
        self.api.patch('mesh',[{'op':'replace','path':'/spec/replicas','value':0}])
        self.assertFalse(self.a.healthy('mesh'))
    def test_unknown_name_rejected(self):
        with self.assertRaises(MutationUnsafe):self.a.scale('anything',1,1)

if __name__=='__main__':unittest.main()
