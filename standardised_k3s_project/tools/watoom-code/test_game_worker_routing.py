import json,pathlib,sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from game_worker_bridge import local_route_blocked as blocked

class LocalRouteBlocked(unittest.TestCase):
    def test_bazzite_not_started_waits_instead_of_parking_the_model(self):
        for op in ('capture','capture-scene','capture-p7','import','regression','blender'):
            self.assertTrue(blocked(op,None,False,{}),op)
    def test_opt_in_flag_restores_local_route(self):
        self.assertFalse(blocked('capture',None,False,{'local_fallback':True}))
    def test_bazzite_ran_means_no_local_route(self):
        self.assertFalse(blocked('capture',object(),False,{}))
    def test_godot_game_routes_itself(self):
        self.assertFalse(blocked('godot-game',None,False,{}))
    def test_unreal_export_routes_itself(self):
        self.assertFalse(blocked('unreal-export',None,False,{}))
    def test_existing_evidence_goes_to_reconciliation(self):
        self.assertFalse(blocked('capture',None,True,{}))

class BlenderFailureReason(unittest.TestCase):
    def test_priority_order(self):
        from blender_bazzite import failure_reason as f
        self.assertIn('OUTPUT_PULL',f('OUTPUT_PULL_FAILED',True,True,4,300,['x'],None,1))
        self.assertIn('memory limit 4GiB',f(None,True,True,4,300,['x'],None,137))
        self.assertIn('deadline 300s',f(None,False,True,4,300,['x'],None,124))
        self.assertEqual('script raised: boom',f(None,False,False,4,300,['Traceback','boom'][-1:],None,1))
        self.assertIn('script reported: bad',f(None,False,False,4,300,[],{'error':'bad'},1))
        self.assertIn('exited 3',f(None,False,False,4,300,[],None,3))

class RigWait(unittest.TestCase):
    def test_rig_only_after_ten_minutes(self):
        from game_worker_bridge import bazzite_wait as w
        since,ok=w(None,5000);self.assertEqual((5000,False),(since,ok))
        since,ok=w({'waiting_since':5000},5000+599);self.assertFalse(ok);self.assertEqual(5000,since)
        since,ok=w({'waiting_since':5000},5000+600);self.assertTrue(ok)
    def test_bad_or_future_timestamp_restarts_the_clock(self):
        from game_worker_bridge import bazzite_wait as w
        for bad in ('x',None,10**12):self.assertEqual((7000,False),w({'waiting_since':bad},7000))

class RigRetryHint(unittest.TestCase):
    def rig_config(self, **overrides):
        cfg = {'enabled': True, 'operations': ['import', 'regression', 'capture', 'capture-p7'],
               'projects': ['/data/ai/projects/games/rig-async-qualification-20261026']}
        cfg.update(overrides)
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump(cfg, tmp)
        tmp.close()
        return pathlib.Path(tmp.name)

    def test_non_timeout_failure_gets_no_hint(self):
        from game_worker_bridge import rig_retry_hint
        cfg = self.rig_config()
        with patch('game_worker_bridge.RIG_CONFIG', cfg):
            self.assertEqual('', rig_retry_hint('/data/ai/projects/games/rig-async-qualification-20261026', 'capture', 'script_error'))

    def test_enrolled_operation_and_project_gets_the_hint(self):
        from game_worker_bridge import rig_retry_hint
        cfg = self.rig_config()
        with patch('game_worker_bridge.RIG_CONFIG', cfg):
            hint = rig_retry_hint('/data/ai/projects/games/rig-async-qualification-20261026', 'capture', 'timeout')
        self.assertIn('watoom_rig_game_job', hint)

    def test_unenrolled_project_gets_no_hint(self):
        from game_worker_bridge import rig_retry_hint
        cfg = self.rig_config()
        with patch('game_worker_bridge.RIG_CONFIG', cfg):
            self.assertEqual('', rig_retry_hint('/data/ai/projects/games/zombie-animal-survival', 'capture', 'timeout'))

    def test_unenrolled_operation_gets_no_hint(self):
        from game_worker_bridge import rig_retry_hint
        cfg = self.rig_config()
        with patch('game_worker_bridge.RIG_CONFIG', cfg):
            self.assertEqual('', rig_retry_hint('/data/ai/projects/games/rig-async-qualification-20261026', 'capture-scene', 'timeout'))

    def test_rig_disabled_gets_no_hint(self):
        from game_worker_bridge import rig_retry_hint
        cfg = self.rig_config(enabled=False)
        with patch('game_worker_bridge.RIG_CONFIG', cfg):
            self.assertEqual('', rig_retry_hint('/data/ai/projects/games/rig-async-qualification-20261026', 'capture', 'timeout'))

    def test_missing_config_file_is_handled_gracefully(self):
        from game_worker_bridge import rig_retry_hint
        with patch('game_worker_bridge.RIG_CONFIG', pathlib.Path('/no/such/file.json')):
            self.assertEqual('', rig_retry_hint('/data/ai/projects/games/rig-async-qualification-20261026', 'capture', 'timeout'))

class BazziteUnreachable(unittest.TestCase):
    def test_ssh_failure_is_reported_as_unreachable_not_unstaged(self):
        import subprocess,sys,pathlib
        sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/'ansible/roles/watoom-code/files/skills/watoom-fab-owned-assets/scripts/unreal-export'))
        import bazzite as bz
        down=subprocess.CompletedProcess([],255,'','ssh: connect to host 10.99.30.111 port 22: Connection timed out\n')
        orig=bz.sh
        try:
            bz.sh=lambda *a,**k:down
            with self.assertRaisesRegex(RuntimeError,'Bazzite unreachable over SSH: .*Connection timed out'):bz.runtime_ready()
            bz.sh=lambda *a,**k:subprocess.CompletedProcess([],0,'','')   # reachable but nothing staged: still None
            self.assertIsNone(bz.runtime_ready())
        finally:bz.sh=orig

class OomDetection(unittest.TestCase):
    def test_the_word_oom_inside_names_is_not_a_memory_kill(self):
        from game_blender import is_oom
        journal="podman run -e WATOOM_OUTPUT=/project/.opencode/blender-out/j -e OMP_NUM_THREADS=2 ... Started watoom-blender-bz-1.service"
        self.assertFalse(is_oom(1,journal))                                   # an ordinary script error
        self.assertTrue(is_oom(137,''))                                        # SIGKILL
        self.assertTrue(is_oom(1,'kernel: Memory cgroup out of memory: Killed process 4242 (blender)'))
        self.assertTrue(is_oom(1,'systemd[1]: watoom.service: A process of this unit has been killed by the OOM killer.'))
        self.assertFalse(is_oom(1,None))

class BazziteUnitOptions(unittest.TestCase):
    def test_bazzite_user_units_never_use_options_that_break_podman_helpers(self):
        import pathlib
        for name in ('game_bazzite.py','blender_bazzite.py','asset_capture_bazzite.py'):
            code=pathlib.Path(__file__).with_name(name).read_text()
            for option in ('PrivateDevices','NoNewPrivileges=yes'):
                active=[l for l in code.splitlines() if option in l and not l.lstrip().startswith('#')]
                self.assertEqual([],active,name+' passes '+option+' to a user unit: podman cannot create its helper inside it')

class ExitEvidence(unittest.TestCase):
    def test_deadline_after_a_script_error_points_at_the_script(self):
        from capture_profiles import exit_evidence
        errors=['SCRIPT ERROR: Parse Error: Cannot find member "REPEAT_ENABLED" in base "Texture2D".','ERROR: Failed to load script "res://x.gd" with error "Parse error".']
        timed,out=exit_evidence(255,'',602,600,errors)
        self.assertTrue(timed)
        self.assertIn('WORKER_DEADLINE_EXCEEDED_AFTER_SCRIPT_ERROR',out[0])
        self.assertNotIn('This is not a script or compile error',out[0])
    def test_plain_deadline_keeps_the_scene_cost_advice(self):
        from capture_profiles import exit_evidence
        timed,out=exit_evidence(255,'',602,600,[])
        self.assertIn('This is not a script or compile error',out[0])
if __name__=='__main__':unittest.main()
