"""Negative controls: barried inventory cannot drift in replicas or spec."""
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock
import g3h_cutover as cut

class BarrierInvariantTests(TestCase):
    def test_rejects_postbarrier_drift(self):
        base={'metadata':{'name':'llama-cpp-test','uid':'same-uid',
                          'resourceVersion':'1','annotations':{}},
              'spec':{'replicas':1,'template':{'metadata':{'labels':{'a':'b'}}}}}
        for field in ('replicas','template'):
            with self.subTest(field=field), TemporaryDirectory() as temp:
                before=copy.deepcopy(base)
                updated=copy.deepcopy(base)
                updated['metadata']['resourceVersion']='2'
                if field=='replicas':
                    updated['spec']['replicas']=0
                else:
                    updated['spec']['template']['metadata']['labels']['a']='changed'
                inventory=[{'llama-cpp-test':before},{'llama-cpp-test':updated}]
                def fake_models():
                    return copy.deepcopy(inventory.pop(0))
                def fake_k(*args):
                    if 'patch' in args:
                        acknowledged=copy.deepcopy(before)
                        acknowledged['metadata']['resourceVersion']='2'
                        acknowledged['metadata']['annotations']={'watoom.io/gpu-cutover-barrier':'set'}
                        # nonce must match; extract from JSON patch operations
                        ops=json.loads(args[args.index('-p')+1])
                        acknowledged['metadata']['annotations']=next(op['value'] for op in ops if op['path']=='/metadata/annotations')
                        return json.dumps(acknowledged)
                    raise AssertionError(args)
                (Path(temp)/'policy-live-check.json').write_text(json.dumps({'checked_at':__import__('time').time(),'checks':[]}))
                with mock.patch.object(cut,'quiescent'), mock.patch.object(cut,'models',side_effect=fake_models), mock.patch.object(cut,'k',side_effect=fake_k):
                    with self.assertRaisesRegex(RuntimeError,'GPU (replica|protected spec) drift'):
                        cut.barrier({},Path(temp))
                    proof=json.loads((Path(temp)/'cutover-barrier.json').read_text())
                    self.assertNotEqual(proof['status'],'complete')
