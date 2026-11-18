"""Tests for worker_status.py: fixture receipts and fakes only; nothing touches a real worker, the journal or the network."""
import json
import pathlib
import subprocess
import tempfile
import time
import unittest

import worker_status as ws

NOW = 1_800_000_000.0


class Fake:
    def __init__(self, stdout='', stderr='', returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


class WorkerStatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        for d in ('receipts', 'reports', 'results', 'jail/inputs', 'jail/uploads'):
            (self.root / d).mkdir(parents=True)

    def receipt(self, name, doc, age):
        path = self.root / 'receipts' / (name + '.json')
        path.write_text(json.dumps(doc))
        stamp = NOW - age
        import os
        os.utime(path, (stamp, stamp))
        return path

    def report(self, evidence, prepared, age):
        d = self.root / 'reports' / evidence
        d.mkdir(parents=True, exist_ok=True)
        (d / 'prepared.json').write_text(json.dumps(prepared))
        import os
        os.utime(d / 'prepared.json', (NOW - age, NOW - age))

    def jobs(self):
        return ws.receipt_jobs(self.root / 'receipts', self.root / 'reports', now=NOW)

    def test_stale_running_is_display_only_after_deadline_and_grace(self):
        age = 100 + ws.STALE_GRACE_SECONDS + 100
        self.report('ev', {'worker': 'bazzite', 'unit': 'watoom-godot-1', 'deadline_seconds': 100}, age=age)
        self.receipt('r', {'request_id': 'a' * 12, 'status': 'RUNNING', 'operation': 'import', 'evidence_id': 'ev', 'worker': 'bazzite'}, age=age)
        job = ws.receipt_jobs(self.root / 'receipts', self.root / 'reports', now=NOW,
                              active_units=[])[0]
        self.assertEqual('stale_running', job['state'])
        self.assertIsNone(job['finished'])
        self.assertIn('grace', job['detail'])
        job = ws.receipt_jobs(self.root / 'receipts', self.root / 'reports', now=NOW,
                              active_units=['watoom-godot-1.service'])[0]
        self.assertEqual('running', job['state'])
        unknown = ws.receipt_jobs(self.root / 'receipts', self.root / 'reports', now=NOW,
                                  active_units=[], unit_status_known=False)[0]
        self.assertEqual('running', unknown['state'])
        self.receipt('missing', {'request_id': 'b' * 12, 'status': 'RUNNING', 'operation': 'import', 'evidence_id': 'absent'}, age=ws.DEFAULT_DEADLINE_SECONDS + ws.STALE_GRACE_SECONDS + 100)
        missing = next(j for j in ws.receipt_jobs(self.root / 'receipts', self.root / 'reports', now=NOW,
                                                   active_units=['watoom-godot-1.service']) if j['id'] == 'bbbbbbbbbbbb')
        self.assertEqual('stale_running', missing['state'])
        self.assertFalse(ws.classify_stale_running(NOW - 50, NOW, 100, True, False))
        self.assertTrue(ws.classify_stale_running(0, 100 + ws.STALE_GRACE_SECONDS + 100, 100, True, False))

    def test_failed_job_carries_worker_duration_and_a_clipped_reason(self):
        self.report('ev1', {'worker': 'bazzite', 'unit': 'watoom-blender-bz-1', 'memory_limit': '4GiB', 'deadline_seconds': 300}, age=200)
        self.receipt('r1', {'request_id': 'a' * 64, 'status': 'FAILED', 'operation': 'blender', 'job': 'wolf-glb', 'project': '/data/ai/projects/games/zombie',
                            'evidence_id': 'ev1', 'failure_stage': 'run', 'failure_code': 'script_error',
                            'worker_result': {'status': 'FAIL', 'failure_reason': 'boom ' * 200}}, age=50)
        job = self.jobs()[0]
        self.assertEqual(('bazzite', 'failed', 'blender', 'wolf-glb', 'zombie'), (job['worker'], job['state'], job['operation'], job['name'], job['project']))
        self.assertEqual(150, job['seconds'])
        self.assertLessEqual(len(job['detail']), ws.REASON_MAX)
        self.assertEqual('4GiB', job['memory_limit'])
        self.assertEqual(('run', 'script_error'), (job['failure_stage'], job['failure_code']))
        doc = self.build(sh=None, journal=lambda now=None: None)
        self.assertNotIn('/data/ai', json.dumps(doc['jobs']))   # only the project folder name leaves the host
        self.assertFalse([k for k in doc['jobs'][0] if k.startswith('_')])

    def test_status_mapping_and_unlabelled_jobs_are_the_server_worker(self):
        for i, (status, state) in enumerate([('COMPLETED', 'completed'), ('RUNNING', 'running'), ('STALE_RESULT', 'stale'), ('STALE_REQUEST', 'stale'),
                                              ('RECONCILIATION_REQUIRED', 'needs_review'), ('SOMETHING_NEW', 'unknown')]):
            self.receipt('r%d' % i, {'request_id': str(i) * 12, 'status': status, 'operation': 'import', 'project': '/x/p', 'worker_result': {}}, age=10 + i)
        got = {j['id'][0]: (j['state'], j['worker']) for j in self.jobs()}
        self.assertEqual(('completed', 'server'), got['0'])
        self.assertEqual('running', got['1'][0])
        self.assertEqual('needs_review', got['4'][0])
        self.assertEqual('unknown', got['5'][0])

    def test_running_job_still_staging_uses_its_receipt_time_as_the_start(self):
        self.receipt('s', {'request_id': 'e' * 12, 'status': 'RUNNING', 'operation': 'import', 'evidence_id': 'not-written-yet', 'worker': 'bazzite'}, age=420)
        job = self.jobs()[0]
        self.assertEqual(NOW - 420, job['started'])
        self.assertIsNone(job['finished'])
        self.assertIsNone(job['unit'])

    def test_running_job_has_no_finish_or_duration(self):
        self.report('ev', {'worker': 'bazzite', 'unit': 'u'}, age=90)
        self.receipt('r', {'request_id': 'b' * 12, 'status': 'RUNNING', 'operation': 'import', 'evidence_id': 'ev', 'worker': 'bazzite'}, age=60)
        job = self.jobs()[0]
        self.assertIsNone(job['finished'])
        self.assertIsNone(job['seconds'])
        self.assertEqual('bazzite', job['worker'])

    def test_raw_command_dumps_become_readable_reasons(self):
        self.receipt('r', {'request_id': 'd' * 12, 'status': 'RECONCILIATION_REQUIRED', 'operation': 'import', 'project': '/x/p',
                           'reason': "Command '['/usr/bin/python3', '/long/path/game_bazzite.py', '--operation', 'import']' returned non-zero exit status 255."}, age=5)
        self.assertEqual('worker command returned non-zero exit status 255', self.jobs()[0]['detail'])
        self.assertEqual('plain reason', ws.friendly('plain reason'))
        self.assertEqual('worker command failed', ws.friendly("Command '[a]' blew up"))

    def test_broken_or_foreign_files_are_ignored(self):
        (self.root / 'receipts' / 'bad.json').write_text('{not json')
        (self.root / 'receipts' / 'list.json').write_text('[1,2]')
        self.assertEqual([], self.jobs())

    def lane(self):
        return ws.lane_jobs(self.root / 'results', self.root / 'jail')

    def test_rig_lane_job_without_result_is_queued_or_running_and_with_result_is_an_outcome(self):
        inputs = self.root / 'jail' / 'inputs'
        (inputs / 'ue-job-skin-1.json').write_text(json.dumps({'job': 'skin-1', 'op': 'metahuman-skin', 'created': NOW - 120, 'params': {'name': 'MHC_Base_Female'}}))
        (inputs / 'ue-job-skin-2.json').write_text(json.dumps({'job': 'skin-2', 'op': 'probe', 'created': NOW - 900}))
        (self.root / 'jail' / 'uploads' / 'ue-skin-2').mkdir()
        (self.root / 'jail' / 'uploads' / 'ue-skin-2' / 'result.json').write_text(json.dumps({'job': 'skin-2', 'op': 'probe', 'status': 'PASS', 'finished': NOW - 600, 'files': ['a']}))
        (self.root / 'results' / 'skin-3').mkdir()
        (self.root / 'results' / 'skin-3' / 'result.json').write_text(json.dumps({'job': 'skin-3', 'op': 'metahuman-skin', 'status': 'FAIL', 'error': 'out of memory', 'finished': NOW - 3000}))
        by = {j['name']: j for j in self.lane()}
        self.assertEqual('queued_or_running', by['skin-1']['state'])
        self.assertEqual('MHC_Base_Female', by['skin-1']['project'])
        self.assertEqual('completed', by['skin-2']['state'])
        self.assertEqual('failed', by['skin-3']['state'])
        self.assertEqual('out of memory', by['skin-3']['detail'])
        self.assertTrue(all(j['worker'] == 'rig' for j in by.values()))

    def test_optional_rig_progress_phase_is_shown_without_result(self):
        (self.root / 'jail' / 'inputs' / 'ue-job-phase-1.json').write_text(json.dumps({'job': 'phase-1', 'op': 'probe', 'created': NOW - 12}))
        upload = self.root / 'jail' / 'uploads' / 'ue-phase-1'
        upload.mkdir()
        (upload / 'progress.json').write_text(json.dumps({'job': 'phase-1', 'phase': 'RUNNING', 'timestamp': NOW - 4}))
        job = next(j for j in self.lane() if j['name'] == 'phase-1')
        self.assertEqual('RUNNING', job['phase'])
        self.assertEqual(NOW - 4, job['phase_at'])
        self.assertEqual('rig phase: running', job['detail'])

    def test_moss_sidecars_become_completed_image_worker_jobs(self):
        output = self.root / 'moss'
        output.mkdir()
        ident = 'a' * 32
        (output / (ident + '.json')).write_text(json.dumps({'scene': 'private prompt', 'created': NOW - 90}))
        image = output / (ident + '.png')
        image.write_bytes(b'png fixture')
        import os
        os.utime(image, (NOW, NOW))
        (output / ('b' * 32 + '.json')).write_text(json.dumps({'created': NOW - 10}))  # no result yet
        (output / ('c' * 32 + '.json')).write_text('{broken')
        (output / ('d' * 32 + '.json')).write_text(json.dumps({'created': NOW - 5, 'hidden': True}))
        (output / ('d' * 32 + '.png')).write_bytes(b'png fixture')  # hidden by the operator
        jobs = ws.moss_jobs(output)
        self.assertEqual(1, len(jobs))
        self.assertEqual(('moss', 'completed', ident[-12:], 90),
                         (jobs[0]['worker'], jobs[0]['state'], jobs[0]['id'], jobs[0]['seconds']))
        self.assertNotIn('private prompt', json.dumps(jobs))

    def test_untrusted_rig_timestamps_cannot_break_snapshot_sorting(self):
        (self.root / 'jail' / 'inputs' / 'ue-job-time-1.json').write_text(json.dumps({'job': 'time-1', 'op': 'probe', 'created': 'not-a-time'}))
        upload = self.root / 'jail' / 'uploads' / 'ue-time-1'
        upload.mkdir()
        (upload / 'result.json').write_text(json.dumps({'job': 'time-1', 'op': 'probe', 'status': 'PASS', 'finished': 'yesterday', 'files': []}))
        job = next(j for j in self.lane() if j['name'] == 'time-1')
        self.assertIsInstance(job['finished'], (int, float))

    def test_bazzite_probe_parses_units_and_ram(self):
        out = 'UP\n11866603520\nUNIT watoom-blender-bz-17.service 1799999900\nUNIT watoom-godot-import-9.service 1799999950\n'
        got = ws.bazzite_state(lambda cmd, timeout: Fake(out), None, NOW)
        self.assertTrue(got['reachable'])
        self.assertEqual(11866603520, got['free_ram_bytes'])
        self.assertEqual(['blender', 'godot import'], [u['label'] for u in got['units']])
        self.assertEqual(1799999900.0, got['units'][0]['started'])

    def test_unreachable_bazzite_is_reported_and_not_hammered(self):
        down = ws.bazzite_state(lambda cmd, timeout: Fake('', 'ssh: connect to host: Connection timed out', 255), None, NOW)
        self.assertFalse(down['reachable'])
        self.assertIn('timed out', down['error'])
        calls = []
        again = ws.bazzite_state(lambda cmd, timeout: calls.append(1) or Fake('UP\n1\n'), down, NOW + 30)
        self.assertEqual([], calls)                       # inside the back-off window: no new SSH attempt
        self.assertFalse(again['reachable'])
        later = ws.bazzite_state(lambda cmd, timeout: Fake('UP\n1\n'), down, NOW + ws.BAZZITE_BACKOFF + 1)
        self.assertTrue(later['reachable'])

    def test_bazzite_history_and_failure_code_carry_across_snapshots(self):
        previous = {'reachable': True, 'checked': NOW - 60, 'last_ok': NOW - 60, 'consecutive_failures': 2,
                    'first_failure': NOW - 20, 'units': []}
        got = ws.bazzite_state(lambda cmd, timeout: Fake('', 'ssh down', 255), previous, NOW)
        self.assertEqual(NOW - 60, got['last_ok'])
        self.assertEqual(3, got['consecutive_failures'])
        self.assertEqual(NOW - 20, got['first_failure'])
        self.assertEqual('unreachable', got['failure_code'])

    def test_probe_exceptions_become_offline_not_crashes(self):
        def boom(cmd, timeout):
            raise subprocess.TimeoutExpired(cmd, timeout)
        self.assertFalse(ws.bazzite_state(boom, None, NOW)['reachable'])

    def test_rig_contact_reads_the_journal_epoch(self):
        run = lambda *a, **k: Fake('1799999990.123456 host sshd-session[1]: Accepted publickey for watoom-render-transfer from 10.99.1.44 port 1 ssh2: ED25519 SHA256:x\n')
        self.assertEqual(1799999990.0, ws.rig_contact(run=run))
        self.assertIsNone(ws.rig_contact(run=lambda *a, **k: Fake('')))
        def broken(*a, **k):
            raise OSError('no journalctl')
        self.assertIsNone(ws.rig_contact(run=broken))

    def build(self, **kw):
        return ws.build(NOW, None, receipts=self.root / 'receipts', reports=self.root / 'reports', lane_results=self.root / 'results', jail=self.root / 'jail', **kw)

    def test_build_marks_workers_busy_from_units_and_pending_lane_jobs(self):
        self.report('ev', {'worker': 'bazzite', 'unit': 'watoom-blender-bz-17', 'memory_limit': '4GiB', 'deadline_seconds': 300}, age=40)
        self.receipt('r', {'request_id': 'c' * 12, 'status': 'RUNNING', 'operation': 'blender', 'job': 'wolf-glb', 'project': '/x/zombie', 'evidence_id': 'ev', 'worker': 'bazzite'}, age=40)
        (self.root / 'jail' / 'inputs' / 'ue-job-j1.json').write_text(json.dumps({'job': 'j1', 'op': 'metahuman-skin', 'created': NOW - 60}))
        doc = self.build(sh=lambda cmd, timeout: Fake('UP\n5\nUNIT watoom-blender-bz-17.service 1799999960\n'), journal=lambda now=None: NOW - 15)
        self.assertTrue(doc['bazzite']['busy'])
        self.assertEqual('wolf-glb', doc['bazzite']['units'][0]['name'])      # the unit is joined to the receipt that owns it
        self.assertEqual('4GiB', doc['bazzite']['units'][0]['memory_limit'])
        self.assertTrue(doc['rig']['online'])
        self.assertEqual(15, doc['rig']['quiet_for_seconds'])
        self.assertTrue(doc['rig']['busy'])
        self.assertEqual('queued_or_running', doc['rig']['waiting_or_running'][0]['state'])

    def test_quiet_rig_is_offline_after_three_minutes_and_idle_workers_are_not_busy(self):
        doc = self.build(sh=lambda cmd, timeout: Fake('UP\n5\n'), journal=lambda now=None: NOW - 400)
        self.assertFalse(doc['rig']['online'])
        self.assertFalse(doc['rig']['busy'])
        self.assertFalse(doc['bazzite']['busy'])
        self.assertEqual(1, doc['schema'])

    def test_collector_records_bad_receipts_and_reachability_history(self):
        (self.root / 'receipts' / 'bad.json').write_text('{broken')
        prev = {'bazzite': {'reachable': False, 'checked': NOW - 500, 'last_ok': NOW - 700, 'consecutive_failures': 2,
                            'first_failure': NOW - 400, 'failure_code': 'unreachable'}}
        doc = ws.build(NOW, prev, receipts=self.root / 'receipts', reports=self.root / 'reports', lane_results=self.root / 'results',
                       jail=self.root / 'jail', sh=lambda cmd, timeout: Fake('', 'down', 255), journal=lambda now=None: None,
                       media_root=self.root / 'media')
        self.assertFalse(doc['collector']['sources']['receipts']['ok'])
        self.assertIn('unreadable', doc['collector']['sources']['receipts']['error'])
        self.assertEqual(3, doc['bazzite']['consecutive_failures'])
        self.assertEqual('down', doc['bazzite']['health'])
        self.assertEqual('down', doc['rig']['health'])

    def test_collector_records_journal_source_failure(self):
        def broken(now=None):
            raise OSError('journal unavailable')
        doc = ws.build(NOW, receipts=self.root / 'receipts', reports=self.root / 'reports', lane_results=self.root / 'results',
                       jail=self.root / 'jail', sh=lambda cmd, timeout: Fake('UP\n5\n'), journal=broken, media_root=self.root / 'media')
        source = doc['collector']['sources']['journal']
        self.assertFalse(source['ok'])
        self.assertIn('journal unavailable', source['error'])

    def test_metrics_include_worker_health_queue_age_and_24h_outcomes(self):
        doc = {'generated': NOW, 'bazzite': {'reachable': False, 'busy': True, 'consecutive_failures': 2},
               'rig': {'online': True, 'busy': False}, 'jobs': []}
        jobs = [{'worker': 'bazzite', 'state': 'running', 'started': NOW - 700},
                {'worker': 'rig', 'state': 'completed', 'finished': NOW - 100},
                {'worker': 'server', 'state': 'failed', 'finished': NOW - 90000}]
        body = ws.render_metrics(doc, NOW, jobs)
        self.assertIn('watoom_worker_up{worker="bazzite"} 0', body)
        self.assertIn('watoom_worker_busy{worker="bazzite"} 1', body)
        self.assertIn('watoom_worker_oldest_running_job_seconds{worker="bazzite"} 700.0', body)
        self.assertIn('watoom_worker_jobs{worker="rig",state="completed"} 1', body)
        self.assertNotIn('state="failed"', body)
        self.assertIn('watoom_worker_snapshot_timestamp_seconds', body)

    def test_atomic_write_is_world_readable_and_leaves_no_temp_file(self):
        out = self.root / 'state' / 'workers.json'
        ws.write_atomic(out, {'a': 1})
        self.assertEqual({'a': 1}, json.loads(out.read_text()))
        self.assertEqual(0o644, out.stat().st_mode & 0o777)
        self.assertEqual(['workers.json'], sorted(p.name for p in out.parent.iterdir()))

    def test_metrics_atomic_write_is_world_readable_and_leaves_no_temp_file(self):
        out = self.root / 'textfile' / 'watoom-workers.prom'
        ws.write_metrics_atomic(out, 'watoom_test 1\n')
        self.assertEqual('watoom_test 1\n', out.read_text())
        self.assertEqual(0o644, out.stat().st_mode & 0o777)
        self.assertEqual(['watoom-workers.prom'], sorted(p.name for p in out.parent.iterdir()))


try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None


@unittest.skipIf(Image is None, 'Pillow not installed')
class OutputMediaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.projects = self.root / 'projects'
        self.cap = self.projects / 'game' / '.opencode' / 'captures'
        self.cap.mkdir(parents=True)
        for d in ('receipts', 'reports', 'results', 'jail/inputs', 'jail/uploads', 'media'):
            (self.root / d).mkdir(parents=True)

    def png(self, path, size=(800, 600), mode='RGBA'):
        Image.new(mode, size, (200, 40, 40, 255) if mode == 'RGBA' else (200, 40, 40)).save(path)
        return path

    def receipt_with(self, name, receipt_doc, status='COMPLETED', age=30, project=None, extra=None):
        rfile = self.projects / 'game' / ('receipt-%s.json' % name)
        rfile.write_text(json.dumps(receipt_doc))
        doc = {'request_id': name * 12, 'status': status, 'operation': 'capture-scene', 'job': name, 'project': str(project or self.projects / 'game'), 'receipt': str(rfile), 'worker_result': {}}
        doc.update(extra or {})
        path = self.root / 'receipts' / (name + '.json')
        path.write_text(json.dumps(doc))
        import os
        os.utime(path, (NOW - age, NOW - age))

    def build(self, **kw):
        return ws.build(NOW, None, receipts=self.root / 'receipts', reports=self.root / 'reports', lane_results=self.root / 'results', jail=self.root / 'jail',
                        media_root=self.root / 'media', roots=(self.projects, self.root / 'results', self.root / 'jail'), sh=None, journal=lambda now=None: None, **kw)

    def job(self, doc, name):
        return next(j for j in doc['jobs'] if j['name'] == name)

    def test_capture_images_become_a_thumbnail_and_a_viewable_copy_without_leaking_paths(self):
        a, b = self.png(self.cap / 'world_wide.png', (3000, 1500)), self.png(self.cap / 'close.png')
        self.receipt_with('c', {'images': [{'path': str(a), 'sha256': 'x'}, {'path': str(b), 'sha256': 'y'}]})
        doc = self.build()
        outputs = self.job(doc, 'c')['outputs']
        self.assertEqual(['world_wide.png', 'close.png'], [o['name'] for o in outputs])
        first = outputs[0]
        self.assertEqual((3000, 1500), (first['width'], first['height']))
        thumb, view = self.root / 'media' / first['thumb'], self.root / 'media' / first['view']
        with Image.open(thumb) as t, Image.open(view) as v:
            self.assertEqual('JPEG', t.format)
            self.assertLessEqual(max(t.size), ws.THUMB_PX)
            self.assertLessEqual(max(v.size), ws.VIEW_PX)
        self.assertEqual(0o644, thumb.stat().st_mode & 0o777)
        self.assertNotIn(str(self.projects), json.dumps(doc))

    def test_moss_output_flows_through_the_shared_thumbnail_and_media_path(self):
        output = self.projects / 'moss-image' / 'output'
        output.mkdir(parents=True)
        ident = 'd' * 32
        image = self.png(output / (ident + '.png'))
        import os
        os.utime(image, (NOW, NOW))
        (output / (ident + '.json')).write_text(json.dumps({'scene': 'private prompt', 'created': NOW - 45}))
        doc = self.build(moss_output=output)
        job = next(j for j in doc['jobs'] if j['worker'] == 'moss')
        self.assertEqual(('completed', ident[-12:]), (job['state'], job['id']))
        self.assertEqual('image', job['outputs'][0]['kind'])
        self.assertTrue((self.root / 'media' / job['outputs'][0]['thumb']).is_file())
        self.assertNotIn(str(self.projects), json.dumps(job))
        self.assertNotIn('private prompt', json.dumps(job))

    def test_llama_mesh_jobs_become_meshy_worker_jobs_with_glb_output(self):
        mesh = self.projects / 'mesh-jobs'
        out = self.projects / 'mesh-out' / 'cube-1' / 'game-ready'
        out.mkdir(parents=True)
        (out / 'asset.glb').write_bytes(b'glTF' + b'\x02\x00\x00\x00' + b'\x14\x00\x00\x00' + b'\x00' * 8)
        for state, ident, finished in (('complete', '20261016T235759Z-21c01f01', '2026-10-17T00:02:31+00:00'),
                                       ('failed', '20261016T235800Z-aaaaaaaa', '2026-10-17T00:03:00+00:00'),
                                       ('running', '20261016T235801Z-bbbbbbbb', None)):
            job = mesh / state / ident
            job.mkdir(parents=True)
            (job / 'request.json').write_text(json.dumps({'name': 'cube', 'created_at': '2026-10-16T23:57:59+00:00', 'prompt': 'private prompt'}))
            (job / 'status.json').write_text(json.dumps({'state': state, 'finished_at': finished, 'error': 'secret /path',
                                                         'output_dir': str(out.parent)}))
        (mesh / 'complete' / 'not-a-job').mkdir()
        jobs = ws.mesh_jobs(mesh)
        self.assertEqual({('completed', 'meshy'), ('failed', 'meshy'), ('running', 'meshy')}, {(j['state'], j['worker']) for j in jobs})
        done = next(j for j in jobs if j['state'] == 'completed')
        self.assertEqual(272, done['seconds'])
        self.assertNotIn('private prompt', json.dumps(jobs))
        self.assertNotIn('secret', json.dumps(jobs))
        doc = self.build(mesh_root=mesh)
        shown = next(j for j in doc['jobs'] if j['worker'] == 'meshy' and j['state'] == 'completed')
        self.assertEqual('model', shown['outputs'][0]['kind'])
        self.assertTrue(all(not k.startswith('_') for k in shown))
        self.assertNotIn(str(self.projects), json.dumps(shown))

    def test_images_outside_the_allowed_roots_and_symlinks_are_never_read(self):
        outside = self.png(self.root / 'secret.png')
        inside = self.png(self.cap / 'ok.png')
        link = self.cap / 'link.png'
        link.symlink_to(outside)
        self.receipt_with('d', {'images': [{'path': str(outside)}, {'path': str(link)}, {'path': str(inside)}]})
        outputs = self.job(self.build(), 'd')['outputs']
        self.assertEqual(['ok.png'], [o['name'] for o in outputs])

    def test_script_outputs_are_listed_by_name_and_images_among_them_are_shown(self):
        out_dir = self.projects / 'game' / '.opencode' / 'blender-out'
        out_dir.mkdir()
        (out_dir / 'wolf.glb').write_bytes(b'x' * 2048)
        self.png(out_dir / 'preview.png')
        self.receipt_with('e', {'outputs': [{'file': '.opencode/blender-out/wolf.glb', 'bytes': 2048}, {'file': '.opencode/blender-out/preview.png'},
                                           {'file': '../../etc/passwd'}]})
        outputs = self.job(self.build(), 'e')['outputs']
        self.assertEqual({('image', 'preview.png'), ('model', 'wolf.glb')}, {(o['kind'], o['name']) for o in outputs})
        model = next(o for o in outputs if o['name'] == 'wolf.glb')
        self.assertEqual(2048, model['bytes'])
        self.assertEqual(b'x' * 2048, (self.root / 'media' / model['model']).read_bytes())    # copied as-is, served to the 3D viewer
        self.assertNotIn(str(self.projects), json.dumps(outputs))

    def test_running_and_pending_jobs_have_no_outputs_and_old_media_is_pruned(self):
        self.receipt_with('f', {'images': [{'path': str(self.png(self.cap / 'f.png'))}]})
        self.receipt_with('r', {}, status='RUNNING')
        self.build()
        stale = self.root / 'media' / 'gone-job'
        stale.mkdir()
        (stale / 'v0.jpg').write_bytes(b'x')
        doc = self.build()
        self.assertEqual([], self.job(doc, 'r')['outputs'])
        self.assertFalse(stale.exists())
        self.assertTrue((self.root / 'media' / ('f' * 12)).is_dir())

    def test_existing_media_is_reused_not_reencoded(self):
        self.receipt_with('g', {'images': [{'path': str(self.png(self.cap / 'g.png'))}]})
        first = self.job(self.build(), 'g')['outputs'][0]
        thumb = self.root / 'media' / first['thumb']
        before = thumb.stat().st_mtime_ns
        self.build()
        self.assertEqual(before, thumb.stat().st_mtime_ns)

    def test_models_are_capped_and_oversized_ones_skipped(self):
        files = []
        for i in range(5):
            f = self.cap / ('m%d.glb' % i)
            f.write_bytes(b'g%d' % i)
            files.append({'path': str(f)})
        self.receipt_with('m', {'images': files})
        names = [o['name'] for o in self.job(self.build(), 'm')['outputs'] if o['kind'] == 'model']
        self.assertEqual(ws.MAX_MODELS_PER_JOB, len(names))
        ws.MAX_MODEL_BYTES, saved = 1, ws.MAX_MODEL_BYTES
        try:
            self.receipt_with('n', {'images': [{'path': str(self.cap / 'm0.glb')}]})
            self.assertEqual([], [o for o in self.job(self.build(), 'n')['outputs'] if o['kind'] == 'model'])
        finally:
            ws.MAX_MODEL_BYTES = saved

    def test_an_unreadable_image_is_skipped_not_fatal(self):
        bad = self.cap / 'bad.png'
        bad.write_bytes(b'not a png')
        good = self.png(self.cap / 'good.png')
        self.receipt_with('h', {'images': [{'path': str(bad)}, {'path': str(good)}]})
        self.assertEqual(['good.png'], [o['name'] for o in self.job(self.build(), 'h')['outputs']])

    def test_rig_job_images_are_shown_from_its_result_folder(self):
        folder = self.root / 'results' / 'skin-9'
        folder.mkdir()
        (folder / 'result.json').write_text(json.dumps({'job': 'skin-9', 'op': 'metahuman-skin', 'status': 'PASS', 'finished': NOW - 100, 'files': ['a']}))
        self.png(folder / 'Head_Basecolor.png')
        (folder / 'm.dna').write_bytes(b'd' * 10)
        outputs = self.job(self.build(), 'skin-9')['outputs']
        (folder / 'head.glb').write_bytes(b'glTF')
        outputs = self.job(self.build(), 'skin-9')['outputs']
        self.assertEqual({('image', 'Head_Basecolor.png'), ('file', 'm.dna'), ('model', 'head.glb')}, {(o['kind'], o['name']) for o in outputs})


class RigNoteTests(unittest.TestCase):
    def test_note_only_when_a_job_has_no_phase(self):
        self.assertEqual(ws.rig_note([]), '')
        self.assertEqual(ws.rig_note([{'phase': 'RUNNING'}]), '')
        self.assertIn('1 job', ws.rig_note([{'phase': None}]))
        self.assertIn('2 jobs', ws.rig_note([{'phase': None}, {'phase': 'RUNNING'}, {}]))


if __name__ == '__main__':
    unittest.main()
