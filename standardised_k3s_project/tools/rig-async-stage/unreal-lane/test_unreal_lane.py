import json, os, pathlib, sys, tempfile, unittest
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'worker-source'))
sys.path.insert(0, str(HERE.parents[2] / 'ansible/roles/watoom-code/files/skills/watoom-metahuman/scripts'))
import unreal_lane as lane
import unreal_worker as uw
import rig_lane

GOOD = lambda job='probe-20261107-aaaa': {'schema': 1, 'job': job, 'op': 'probe', 'created': 1.0, 'package': None, 'params': {}}


class Contract(unittest.TestCase):
    def test_accepts_a_valid_probe_manifest(self):
        self.assertEqual('probe', lane.validate_manifest(GOOD(), expected_job='probe-20261107-aaaa')['op'])

    def test_rejects_everything_unexpected(self):
        bad = [
            {**GOOD(), 'op': 'run-shell'},                                   # not in the allow-list
            {**GOOD(), 'job': '../escape-1234'},                              # path-like id
            {**GOOD(), 'params': {'cmd': 'calc.exe'}},                        # parameters the op does not take
            {**GOOD(), 'package': {'sha256': 'a' * 64, 'bytes': 5}},          # package for a no-package op
            {**GOOD(), 'schema': 2},
            {**GOOD(), 'extra': 1},                                           # unknown key
        ]
        for m in bad:
            with self.assertRaises(ValueError, msg=str(m)):
                lane.validate_manifest(m)
        with self.assertRaises(ValueError):
            lane.validate_manifest(GOOD('probe-20261107-aaaa'), expected_job='probe-20261107-bbbb')   # name/content mismatch

    def test_result_validation(self):
        m = GOOD()
        ok = {'schema': 1, 'job': m['job'], 'op': 'probe', 'status': 'PASS', 'files': {'probe.json': {'sha256': 'b' * 64, 'bytes': 3}}}
        self.assertEqual('PASS', lane.validate_result(ok, m)['status'])
        for mutate in ({'job': 'other-job-12345'}, {'status': 'MAYBE'}, {'files': {'evil.exe': {'sha256': 'b' * 64, 'bytes': 1}}},
                       {'files': {'../x.json': {'sha256': 'b' * 64, 'bytes': 1}}}, {'files': {'a.json': {'sha256': 'zz', 'bytes': 1}}}):
            with self.assertRaises(ValueError):
                lane.validate_result({**ok, **mutate}, m)


class FakeTransport:
    """In-memory jail: inputs {name: bytes}, uploads {job: {name: bytes}}; can fail on demand."""
    def __init__(self):
        self.inputs, self.uploads, self.fail_get, self.fail_put = {}, {}, False, False

    def list_jobs(self): return sorted(n[len(lane.PREFIX):-5] for n in self.inputs if n.startswith(lane.PREFIX) and n.endswith('.json'))
    def has_result(self, job): return 'result.json' in self.uploads.get(job, {})

    def get(self, name, local):
        if self.fail_get:
            raise RuntimeError('link down')
        pathlib.Path(local).write_bytes(self.inputs[name])

    def put(self, job, files):
        if self.fail_put:
            raise RuntimeError('link down')
        for f in files:
            self.uploads.setdefault(job, {})[pathlib.Path(f).name] = pathlib.Path(f).read_bytes()


def make_lane(t, runner=None, **cfg):
    root = tempfile.mkdtemp()
    config = {'root': root, 'memory_gib': 24, 'plugins': ['MetaHumanCharacter'], **cfg}
    def fake_runner(plan, timeout):
        work = pathlib.Path(plan).parent
        (work / 'probe.json').write_text('{"engine": "x"}')
        (work / 'unreal.log').write_text('log')
        return 0
    return uw.Lane(config, t, runner=runner or fake_runner)


class WorkerLogic(unittest.TestCase):
    def test_runs_one_probe_uploads_artifacts_then_result_last(self):
        t = FakeTransport(); job = 'probe-20261107-aaaa'
        t.inputs[lane.manifest_name(job)] = json.dumps(GOOD(job)).encode()
        order = []
        progress_phases = []
        real_put = t.put
        def recording_put(j, files):
            files = list(files)
            order.append([pathlib.Path(f).name for f in files])
            for f in files:
                if pathlib.Path(f).name == 'progress.json':
                    progress_phases.append(json.loads(pathlib.Path(f).read_text())['phase'])
            return real_put(j, files)
        t.put = recording_put
        w = make_lane(t)
        self.assertEqual(job, w.once())
        self.assertEqual(['result.json'], order[-1])                              # result.json is the last upload
        result = json.loads(t.uploads[job]['result.json'])
        self.assertEqual('PASS', result['status'])
        progress = json.loads(t.uploads[job]['progress.json'])
        self.assertEqual(('UPLOADING', job), (progress['phase'], progress['job']))
        self.assertIsInstance(progress['timestamp'], (int, float))
        self.assertEqual(['FETCHING', 'RUNNING', 'UPLOADING'], progress_phases)
        self.assertEqual({'probe.json', 'unreal.log'}, set(result['files']))
        self.assertNotIn('plan.json', result['files'])
        self.assertIsNone(w.once())                                                # never run twice
        lane.validate_result(result, GOOD(job))

    def test_invalid_manifest_is_reported_not_run(self):
        t = FakeTransport(); job = 'probe-20261107-bbbb'
        t.inputs[lane.manifest_name(job)] = json.dumps({**GOOD(job), 'op': 'format-disk'}).encode()
        ran = []
        w = make_lane(t, runner=lambda p, to: ran.append(1) or 0)
        self.assertEqual(job, w.once())
        self.assertEqual([], ran)
        self.assertEqual('FAIL', json.loads(t.uploads[job]['result.json'])['status'])
        result = json.loads(t.uploads[job]['result.json'])
        self.assertIn('Rejected manifest', result['reason'])
        self.assertEqual(('request', 'unknown'), (result['failure_stage'], result['failure_code']))

    def test_download_trouble_before_running_is_retried_not_failed(self):
        t = FakeTransport(); job = 'probe-20261107-cccc'
        t.inputs[lane.manifest_name(job)] = json.dumps(GOOD(job)).encode()
        t.fail_get = True
        w = make_lane(t)
        self.assertIsNone(w.once())
        self.assertFalse(w.journal.exists())
        t.fail_get = False
        self.assertEqual(job, w.once())

    def test_a_crash_mid_run_is_never_replayed(self):
        t = FakeTransport(); job = 'probe-20261107-dddd'
        t.inputs[lane.manifest_name(job)] = json.dumps(GOOD(job)).encode()
        def die(plan, timeout):
            raise KeyboardInterrupt()        # worker killed while the job was RUNNING (journal stays)
        w = make_lane(t, runner=die)
        with self.assertRaises(KeyboardInterrupt):
            w.once()
        w2 = uw.Lane(w.cfg, t, runner=lambda p, to: self.fail('replayed'))        # a restarted worker
        self.assertEqual(job, w2.once())
        result = json.loads(t.uploads[job]['result.json'])
        self.assertEqual('FAIL', result['status'])
        self.assertIn('not replayed', result['reason'])
        self.assertEqual(('run', 'worker_error'), (result['failure_stage'], result['failure_code']))

    def test_runner_timeout_is_a_structured_failure(self):
        import subprocess
        t = FakeTransport(); job = 'probe-20261107-hhhh'
        t.inputs[lane.manifest_name(job)] = json.dumps(GOOD(job)).encode()
        w = make_lane(t, runner=lambda p, timeout: (_ for _ in ()).throw(subprocess.TimeoutExpired('unreal_runner', timeout)))
        self.assertEqual(job, w.once())
        result = json.loads(t.uploads[job]['result.json'])
        self.assertEqual(('run', 'timeout'), (result['failure_stage'], result['failure_code']))
        self.assertNotIn('argv', result.get('reason', ''))

    def test_progress_write_failure_does_not_change_job_execution(self):
        from unittest.mock import patch
        t = FakeTransport(); job = 'probe-20261107-iiii'
        t.inputs[lane.manifest_name(job)] = json.dumps(GOOD(job)).encode()
        w = make_lane(t)
        real_atomic = uw.atomic
        def fail_only_progress(path, value):
            if pathlib.Path(path).name == 'progress.json':
                raise OSError('progress storage unavailable')
            return real_atomic(path, value)
        with patch.object(uw, 'atomic', side_effect=fail_only_progress):
            self.assertEqual(job, w.once())
        self.assertEqual('PASS', json.loads(t.uploads[job]['result.json'])['status'])

    def test_defers_while_another_rig_consumer_is_busy_or_paused(self):
        t = FakeTransport(); job = 'probe-20261107-eeee'
        t.inputs[lane.manifest_name(job)] = json.dumps(GOOD(job)).encode()
        busy = pathlib.Path(tempfile.mkdtemp()) / 'active.private.json'
        busy.write_text(json.dumps({'phase': 'RUNNING'}))
        w = make_lane(t, busy_journals=[str(busy)])
        self.assertIsNone(w.once())
        busy.write_text(json.dumps({'phase': 'DONE'}))
        self.assertEqual(job, w.once())
        t.inputs[lane.manifest_name('probe-20261107-ffff')] = json.dumps(GOOD('probe-20261107-ffff')).encode()
        w.paused = lambda: True
        self.assertIsNone(w.once())

    def test_memory_limit_comes_from_config_not_the_manifest(self):
        t = FakeTransport(); job = 'probe-20261107-gggg'
        t.inputs[lane.manifest_name(job)] = json.dumps(GOOD(job)).encode()
        seen = {}
        def runner(plan, timeout):
            seen.update(json.loads(pathlib.Path(plan).read_text()))
            (pathlib.Path(plan).parent / 'probe.json').write_text('{}')
            return 0
        make_lane(t, runner=runner, memory_gib=32).once()
        self.assertEqual(32 * 1024 ** 3, seen['memory_bytes'])
        self.assertEqual('ue_probe_api.py', seen['script'])


class RunnerProject(unittest.TestCase):
    def test_enables_only_pinned_plugins_non_optional(self):
        import unreal_runner as ur
        prov = {'metahuman_plugins': {'Engine/Plugins/MetaHuman/MetaHumanCharacter/MetaHumanCharacter.uplugin': {}, 'Engine/Plugins/MetaHuman/MetaHumanSDK/MetaHumanSDK.uplugin': {},
                                      'Engine/Plugins/MetaHuman/MetaHumanLiveLink/MetaHumanLiveLink.uplugin': {}, 'Engine/Plugins/MetaHuman/MetaHumanAnimator/MetaHuman.uplugin': {}}}
        names = ur.plugins_to_enable(prov)
        self.assertEqual(['MetaHumanCharacter', 'MetaHumanSDK'], names)                 # Animator/LiveLink are not enabled
        d = pathlib.Path(tempfile.mkdtemp())
        doc = json.loads(ur.write_project(d, names).read_text())
        self.assertTrue(all('Optional' not in p for p in doc['Plugins']))                # Optional entries silently did not load
        self.assertIn('MetaHumanCharacter', [p['Name'] for p in doc['Plugins']])
        with self.assertRaises(RuntimeError):
            ur.plugins_to_enable({'metahuman_plugins': {}})


SKIN = lambda job='skin-20261107-aaaa': {'schema': 1, 'job': job, 'op': 'metahuman-skin', 'created': 1.0,
                                         'package': {'sha256': 'c' * 64, 'bytes': 1234},
                                         'params': {'asset': '/Game/EditableCharacters/Base_Female/MHC_Base_Female', 'name': 'MHC_Base_Female', 'bake_makeup': False}}


class SkinOp(unittest.TestCase):
    def test_manifest_rules(self):
        self.assertEqual('metahuman-skin', lane.validate_manifest(SKIN())['op'])
        for mutate in ({'package': None}, {'params': {'asset': '/Game/../../Windows/x', 'name': 'a'}}, {'params': {'asset': '/Engine/Foo/Bar', 'name': 'a'}},
                       {'params': {'name': 'MHC'}}, {'params': {'asset': '/Game/A/B', 'name': 'bad name!'}},
                       {'params': {'asset': '/Game/A/B', 'name': 'ok', 'cmd': 'x'}}, {'params': {'asset': '/Game/A/B', 'name': 'ok', 'bake_makeup': 'yes'}}):
            with self.assertRaises(ValueError, msg=str(mutate)):
                lane.validate_manifest({**SKIN(), **mutate})

    def test_unpack_refuses_escapes_and_non_assets(self):
        import unreal_runner as ur, zipfile
        def zipped(name, data=b'x'):
            p = pathlib.Path(tempfile.mkdtemp()) / 'p.zip'
            with zipfile.ZipFile(p, 'w') as z:
                z.writestr(name, data)
            return p
        for bad in ('../evil.uasset', '/abs/x.uasset', 'a/b.exe', 'a/CON.uasset', 'a\b.uasset', 'C:/x.uasset', 'a/b.uasset.'):
            with self.assertRaises(ValueError, msg=bad):
                ur.unpack_package(zipped(bad), pathlib.Path(tempfile.mkdtemp()) / 'Content')
        d = pathlib.Path(tempfile.mkdtemp()) / 'Content'
        self.assertEqual(['EditableCharacters/X/MHC_X.uasset'], ur.unpack_package(zipped('EditableCharacters/X/MHC_X.uasset', b'asset'), d))
        self.assertEqual(b'asset', (d / 'EditableCharacters/X/MHC_X.uasset').read_bytes())

    def test_unpack_refuses_control_characters_in_names(self):
        import unreal_runner as ur, zipfile
        for name in ('a/b' + chr(8) + '.uasset', 'a/b' + chr(10) + '.uasset', 'a/b' + chr(0) + 'c.uasset'):
            p = pathlib.Path(tempfile.mkdtemp()) / 'p.zip'
            with zipfile.ZipFile(p, 'w') as z:
                z.writestr(name, b'x')
            with self.assertRaises(ValueError):
                ur.unpack_package(p, pathlib.Path(tempfile.mkdtemp()) / 'Content')

    def test_editor_command_modes(self):
        import unreal_runner as ur
        full = ur.editor_command({'full_editor': True, 'null_rhi': False}, 'C:/UE', 'P.uproject', 'S.py', 'L.log')
        self.assertTrue(full[0].endswith('UnrealEditor.exe'))
        self.assertIn('-RenderOffScreen', full); self.assertNotIn('-NullRHI', full)       # a real renderer: TextureGraph needs one
        cmdlet = ur.editor_command({'full_editor': False, 'null_rhi': True}, 'C:/UE', 'P.uproject', 'S.py', 'L.log')
        self.assertTrue(cmdlet[0].endswith('UnrealEditor-Cmd.exe')); self.assertIn('-NullRHI', cmdlet)

    def test_worker_builds_the_request_from_validated_fields_only(self):
        import hashlib
        t = FakeTransport(); job = 'skin-20261107-aaaa'
        pkg = b'zipbytes'
        m = {**SKIN(job), 'package': {'sha256': hashlib.sha256(pkg).hexdigest(), 'bytes': len(pkg)}}
        t.inputs[lane.manifest_name(job)] = json.dumps(m).encode()
        t.inputs[lane.package_name(job)] = pkg
        seen = {}
        def runner(plan, timeout):
            seen.update(json.loads(pathlib.Path(plan).read_text()))
            (pathlib.Path(plan).parent / 'native-result.json').write_text('{}')
            return 0
        self.assertEqual(job, make_lane(t, runner=runner).once())
        self.assertEqual({'op': 'export_dcc', 'asset': '/Game/EditableCharacters/Base_Female/MHC_Base_Female', 'name': 'MHC_Base_Female', 'bake_makeup': False}, seen['request'])
        self.assertTrue(seen['full_editor']); self.assertTrue(seen['package']); self.assertFalse(seen['null_rhi'])
        self.assertNotIn('package.zip', json.loads(t.uploads[job]['result.json'])['files'])        # the input package is never sent back

    def test_corrupt_package_is_rejected_before_running(self):
        t = FakeTransport(); job = 'skin-20261107-bbbb'
        t.inputs[lane.manifest_name(job)] = json.dumps({**SKIN(job), 'package': {'sha256': 'd' * 64, 'bytes': 4}}).encode()
        t.inputs[lane.package_name(job)] = b'oops'
        ran = []
        w = make_lane(t, runner=lambda p, to: ran.append(1) or 0)
        self.assertEqual(job, w.once())
        self.assertEqual([], ran)
        self.assertIn('package hash mismatch', json.loads(t.uploads[job]['result.json'])['reason'])

    def test_submit_skin_packages_only_verified_character_files(self):
        import zipfile
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d); pack = d / 'pack'; (pack / 'Content/EditableCharacters/X').mkdir(parents=True)
            f = pack / 'Content/EditableCharacters/X/MHC_X.uasset'; f.write_bytes(b'character')
            (pack / 'metahuman-install.json').write_text(json.dumps({'characters': [{'name': 'MHC_X', 'object_path': '/Game/EditableCharacters/X/MHC_X.MHC_X'}],
                'installed': [{'character': 'MHC_X', 'file': 'Content/EditableCharacters/X/MHC_X.uasset', 'sha256': lane.sha256_file(f)}]}))
            transfer = d / 't'; (transfer / 'inputs').mkdir(parents=True)
            job = rig_lane.submit_skin(pack, 'X', transfer=transfer)
            m = json.loads((transfer / 'inputs' / lane.manifest_name(job)).read_text())
            self.assertEqual(lane.sha256_file(transfer / 'inputs' / lane.package_name(job)), m['package']['sha256'])
            with zipfile.ZipFile(transfer / 'inputs' / lane.package_name(job)) as z:
                self.assertEqual(['EditableCharacters/X/MHC_X.uasset'], z.namelist())
            f.write_bytes(b'tampered')
            with self.assertRaises(SystemExit):
                rig_lane.submit_skin(pack, 'X', transfer=transfer)
            self.assertEqual(2, len(list((transfer / 'inputs').iterdir())))            # no partial files left behind


class HomelabCli(unittest.TestCase):
    def test_submit_status_collect_roundtrip_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as d:
            transfer = pathlib.Path(d)
            (transfer / 'inputs').mkdir(); (transfer / 'uploads').mkdir()
            job = rig_lane.submit('probe', transfer=transfer)
            self.assertEqual('queued-or-running', rig_lane.status(job, transfer))
            up = transfer / 'uploads' / lane.upload_dir(job); up.mkdir()
            (up / 'probe.json').write_text('{"ok": true}')
            result = {'schema': 1, 'job': job, 'op': 'probe', 'status': 'PASS', 'files': {'probe.json': {'sha256': lane.sha256_file(up / 'probe.json'), 'bytes': 12}}}
            (up / 'result.json').write_text(json.dumps(result))
            self.assertEqual('complete-PASS', rig_lane.status(job, transfer))
            out = rig_lane.collect(job, out=str(transfer / 'out'), transfer=transfer)
            self.assertEqual(['probe.json'], out['files'])
            (up / 'probe.json').write_text('{"ok": false}')                          # tampered after hashing
            with self.assertRaises(SystemExit):
                rig_lane.collect(job, out=str(transfer / 'out2'), transfer=transfer)
            self.assertFalse((transfer / 'out2').exists())                            # nothing half-copied
            with self.assertRaises(SystemExit):
                rig_lane.cancel(job, transfer)                                         # already has a result

    def test_cancel_removes_an_unstarted_job(self):
        with tempfile.TemporaryDirectory() as d:
            transfer = pathlib.Path(d); (transfer / 'inputs').mkdir(); (transfer / 'uploads').mkdir()
            job = rig_lane.submit('probe', transfer=transfer)
            self.assertTrue(rig_lane.cancel(job, transfer)['cancelled'])
            self.assertEqual('unknown', rig_lane.status(job, transfer))


if __name__ == '__main__':
    unittest.main()
