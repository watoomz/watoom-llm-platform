import json
from pathlib import Path
import tempfile
import unittest
from controller import State, Conflict, Unsafe
from durable_store import DurableStore
from g3h_service import Runtime

JOB = '20261012T120000Z-12345678'
OTHER = '20261012T120001Z-12345678'


class API:
    def get(self, name):
        return {'metadata': {'uid': name, 'resourceVersion': '1', 'generation': 1},
                'spec': {'replicas': 1 if name == 'qwen' else 0},
                'status': {'readyReplicas': 1, 'observedGeneration': 1}}


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.units = lambda job: {'ActiveState': 'active', 'MainPID': '123'}
        self.identity = lambda pid: '999'
        self.runtime = Runtime({'state_root': str(self.root), 'primary': 'qwen', 'mesh': 'mesh',
                                'stop_timeout': 0.01, 'startup_timeout': 0.01},
                               api=API(), probe=lambda *args: True,
                               units=lambda job: self.units(job), identity=lambda pid: self.identity(pid))
        DurableStore(self.root / 'state.json').save(State())

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, action, **kw):
        return self.runtime.handle({'action': action, **kw}, private=True, pid=123, uid=0)

    def test_production_cutover_proof_preserves_process_identity_callable(self):
        proof={'status':'complete','models':{name:{'uid':name,'status':'acknowledged'} for name in ('qwen','mesh')}}
        (self.root/'cutover-proof.json').write_text(json.dumps(proof))
        config={**self.runtime.c,'cutover_required':True,'deployment_identity':{name:{'uid':name} for name in ('qwen','mesh')}}
        runtime=Runtime(config,api=API(),probe=lambda *args:True,units=self.units,identity=self.identity)
        result=runtime.handle({'action':'begin','job':JOB},private=True,pid=123,uid=0)
        self.assertEqual(result,{'generation':1})
        owner=json.loads((self.root/'worker.json').read_text())
        self.assertEqual(owner['start'],'999')
        self.assertEqual(owner['pid'],123)

    def test_oneshot_mainpid_is_verified_during_activation(self):
        self.units=lambda job:{'ActiveState':'activating','MainPID':'123'}
        self.assertEqual(self.call('begin',job='game-worker'),{'generation':1})

    def test_cpu_park_preserves_ownership_and_never_starts_mesh(self):
        self.call('begin',job='game-worker')
        calls=[]
        self.runtime.actuator.scale=lambda name,n,g:calls.append((name,n,g))
        self.runtime.actuator.stopped=lambda name:True
        self.call('park-cpu',job='game-worker',generation=1)
        self.assertEqual(calls,[('qwen',0,1)])
        state=DurableStore(self.root / "state.json").load()
        self.assertEqual((state.phase,state.owner),('cpu-active','game-worker'))
        with self.assertRaises(Conflict):self.call('can-use-qwen')

    def test_cpu_park_requires_idle_backend(self):
        self.call('begin',job='game-worker')
        self.runtime.actuator.probe=lambda name,kind:False
        with self.assertRaises(Conflict):self.call('park-cpu',job='game-worker',generation=1)
        self.assertEqual(DurableStore(self.root / 'state.json').load().phase,'acquiring')

    def test_moss_image_host_worker_parks_primary_and_never_starts_mesh(self):
        self.call('begin',job='moss-image')
        calls=[]
        self.runtime.actuator.scale=lambda name,n,g:calls.append((name,n,g))
        self.runtime.actuator.stopped=lambda name:True
        self.call('park-cpu',job='moss-image',generation=1)
        self.assertEqual(calls,[('qwen',0,1)])
        state=DurableStore(self.root / 'state.json').load()
        self.assertEqual((state.phase,state.owner),('cpu-active','moss-image'))
        with self.assertRaises(Conflict):self.call('can-use-qwen')

    def test_moss_image_park_requires_idle_backend(self):
        self.call('begin',job='moss-image')
        self.runtime.actuator.probe=lambda name,kind:False
        with self.assertRaises(Conflict):self.call('park-cpu',job='moss-image',generation=1)
        self.assertEqual(DurableStore(self.root / 'state.json').load().phase,'acquiring')

    def test_moss_image_must_be_its_own_unit_mainpid(self):
        self.units=lambda job:{'ActiveState':'active','MainPID':'999'}
        with self.assertRaises(Unsafe):self.call('begin',job='moss-image')

    def test_cpu_park_denies_other_worker(self):
        self.call('begin',job=JOB)
        with self.assertRaises(Unsafe):self.call('park-cpu',job=JOB,generation=1)

    def test_router_cannot_acquire(self):
        with self.assertRaises(Unsafe):
            self.runtime.handle({'action': 'begin', 'job': JOB}, private=False, pid=123, uid=0)

    def test_unauthorized_uid(self):
        with self.assertRaises(Unsafe):
            self.runtime.handle({'action': 'status'}, private=True, pid=123, uid=1009)

    def test_missing_state_fails_closed(self):
        (self.root / 'state.json').unlink()
        with self.assertRaises(Unsafe):
            self.call('can-use-qwen')

    def test_corrupt_state_fails_closed(self):
        (self.root / 'state.json').write_text('{}')
        with self.assertRaises(ValueError):
            self.call('can-use-qwen')

    def test_second_begin_preserves_first_identity(self):
        self.call('begin', job=JOB)
        before = (self.root / 'worker.json').read_bytes()
        with self.assertRaises(Conflict):
            self.call('begin', job=OTHER)
        self.assertEqual(before, (self.root / 'worker.json').read_bytes())

    def test_pid_not_unit_owner_rejected(self):
        self.units = lambda job: {'ActiveState': 'active', 'MainPID': '124'}
        with self.assertRaises(Unsafe):
            self.call('begin', job=JOB)

    def test_acquisition_blocks_router_before_mesh_scale(self):
        self.call('begin', job=JOB)
        with self.assertRaises(Conflict):
            self.call('can-use-qwen')

    def test_pending_intent_blocks_idle_router(self):
        self.runtime.journal.write({'id': 'pending', 'name': 'qwen', 'generation': 0, 'status': 'pending'})
        with self.assertRaises(Unsafe):
            self.call('can-use-qwen')

    def test_live_owner_recovery_rejected_all_phases(self):
        self.call('begin', job=JOB)
        for phase in ('cpu-active', 'acquiring', 'mesh-active', 'stopping-qwen', 'starting-mesh', 'restoring', 'recovery-required'):
            DurableStore(self.root / 'state.json').save(State(phase, JOB, 1, phase == 'recovery-required'))
            with self.subTest(phase=phase), self.assertRaises(Unsafe):
                self.call('recover', job=JOB, generation=1)

    def test_dead_unit_live_pid_rejected(self):
        self.call('begin', job=JOB)
        self.units = lambda job: {'ActiveState': 'failed', 'MainPID': '0'}
        with self.assertRaises(Unsafe):
            self.call('recover', job=JOB, generation=1)

    def test_dead_owner_recovers_every_phase(self):
        self.call('begin', job=JOB)
        self.units = lambda job: {'ActiveState': 'failed', 'MainPID': '0'}
        self.identity = lambda pid: None
        calls = []
        self.runtime.controller._restore = lambda job, generation: calls.append((job, generation))
        for phase in ('cpu-active', 'acquiring', 'mesh-active', 'stopping-qwen', 'starting-mesh', 'restoring', 'recovery-required'):
            DurableStore(self.root / 'state.json').save(State(phase, JOB, 1, phase == 'recovery-required'))
            self.call('recover', job=JOB, generation=1)
        self.assertEqual(calls, [(JOB, 1)] * 7)

    def test_exec_stop_post_recovers_only_after_main_process_ended(self):
        self.call('begin', job=JOB)
        self.units = lambda job: {'ActiveState': 'deactivating', 'MainPID': '0'}
        self.identity = lambda pid: None
        calls=[]
        self.runtime.controller._restore=lambda job, generation:calls.append(job)
        self.call('recover',job=JOB,generation=1)
        self.assertEqual(calls,[JOB])

    def test_stale_epoch_no_recovery(self):
        self.call('begin', job=JOB)
        with self.assertRaises(Conflict):
            self.call('recover', job=JOB, generation=0)

    def test_pid_reuse_cannot_restore(self):
        self.call('begin', job=JOB)
        self.identity = lambda pid: 'new-start'
        with self.assertRaises(Unsafe):
            self.call('restore', job=JOB, generation=1)


if __name__ == '__main__':
    unittest.main()
