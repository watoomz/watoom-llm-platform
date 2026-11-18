"""Offline safety/restore tests. No Kubernetes, Docker, Ansible or live mutation."""
import gzip
from contextlib import closing
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import recovery


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def backup(self):
        root = self.root / 'backup'; root.mkdir()
        db = self.root / 'original.sqlite'
        with closing(sqlite3.connect(db)) as c, c:
            c.execute('create table fixture(value text)')
            c.execute("insert into fixture values ('retained')")
        with db.open('rb') as src, gzip.open(root / 'application.sqlite.gz', 'wb') as dst:
            dst.write(src.read())
        self.manifest(root)
        return root

    def manifest(self, root):
        values = {str(p.relative_to(root)): recovery.digest(p) for p in root.rglob('*')
                  if p.is_file() and p.name != 'manifest.json'}
        (root / 'manifest.json').write_text(json.dumps({'files': values}))

    def test_verified_sqlite_restore_into_new_directory(self):
        root = self.backup(); dest = self.root / 'restore'
        result = recovery.restore_test(root, dest)
        self.assertEqual(result['result'], 'PASS')
        with closing(sqlite3.connect(dest / 'application.sqlite')) as c:
            self.assertEqual(c.execute('select value from fixture').fetchone(), ('retained',))

    def test_corrupt_backup_is_refused_before_restore(self):
        root = self.backup(); (root / 'application.sqlite.gz').write_bytes(b'corrupt')
        with self.assertRaises(ValueError):
            recovery.restore_test(root, self.root / 'restore')
        self.assertFalse((self.root / 'restore').exists())

    def test_manifest_traversal_is_refused(self):
        root = self.backup()
        (root / 'manifest.json').write_text(json.dumps({'files': {'../original.sqlite': recovery.digest(self.root / 'original.sqlite')}}))
        with self.assertRaises(ValueError):
            recovery.verify_backup(root)

    def test_manifest_symlink_is_refused(self):
        root = self.backup(); (root / 'link').symlink_to(self.root / 'original.sqlite')
        (root / 'manifest.json').write_text(json.dumps({'files': {'link': recovery.digest(self.root / 'original.sqlite')}}))
        with self.assertRaises(ValueError):
            recovery.verify_backup(root)

    def test_existing_restore_target_is_never_overwritten(self):
        root = self.backup(); target = self.root / 'restore'; target.mkdir()
        sentinel = target / 'keep'; sentinel.write_text('unchanged')
        with self.assertRaises(ValueError):
            recovery.restore_test(root, target)
        self.assertEqual(sentinel.read_text(), 'unchanged')

    def test_longest_prefix_and_boundary_do_not_hide_unknown_paths(self):
        policy = {'storage': [{'path': '/', 'mode': 'boundary'}, {'path': '/data', 'mode': 'boundary'},
                             {'path': '/data/ai', 'mode': 'capture'}, {'path': '/data/ai/models', 'mode': 'reacquire'}]}
        self.assertEqual(recovery.classify('/data/ai/models/weights.gguf', policy)['mode'], 'reacquire')
        self.assertEqual(recovery.classify('/data/unclassified', policy)['mode'], 'unclassified')

    def test_evidence_boolean_without_real_checksum_cannot_pass(self):
        policy = {'required_evidence': ['source']}; inv = {'storage': []}
        value = recovery.coverage(inv, policy, {'source': {'verified': True, 'location': str(self.root / 'absent'), 'sha256': '0' * 64}})
        self.assertEqual(value['result'], 'BLOCKED')

    def test_evidence_checksum_is_checked(self):
        p = self.root / 'proof'; p.write_text('verified restore report')
        policy = {'required_evidence': ['state']}; inv = {'storage': []}
        evidence = {'state': {'verified': True, 'location': str(p), 'sha256': recovery.digest(p)}}
        self.assertEqual(recovery.coverage(inv, policy, evidence)['result'], 'READY_FOR_ISOLATED_DRILL')
        p.write_text('changed')
        self.assertEqual(recovery.coverage(inv, policy, evidence)['result'], 'BLOCKED')

    def test_unknown_storage_blocks_recovery_readiness(self):
        value = recovery.coverage({'storage': [{'path': '/unknown', 'mode': 'unclassified'}]}, {'required_evidence': []}, {})
        self.assertEqual(value['result'], 'BLOCKED')

    def test_apply_refuses_source_machine_before_running_any_command(self):
        machine = Path('/etc/machine-id')
        if not machine.exists():
            self.skipTest('Linux replacement-host guard')
        p = self.root / 'inventory.json'
        p.write_text(json.dumps({'source_machine_id_sha256': hashlib.sha256(machine.read_bytes()).hexdigest()}))
        with patch('recovery.subprocess.run') as execute, self.assertRaisesRegex(ValueError, 'production machine'):
            recovery.run_phase({}, p, self.root / 'absent', '03-foundation', None, self.root / 'run')
        execute.assert_not_called()

    def test_bundle_restores_files_and_sqlite_only_inside_target(self):
        root = self.backup(); (root / 'private').mkdir()
        (root / 'private/sqlite-map.json').write_text(json.dumps([{'original': '/app/fixture.sqlite', 'snapshot': 'application.sqlite.gz'}]))
        with tarfile.open(root / 'private-state.tar.gz', 'w:gz') as archive:
            content = b'configuration retained'
            info = tarfile.TarInfo('etc/fixture.conf'); info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
        self.manifest(root)
        target = self.root / 'isolated'
        value = recovery.restore_bundle(root, target)
        self.assertEqual(value['result'], 'RESTORED_ISOLATED_NOT_ACTIVATED')
        self.assertEqual((target / 'etc/fixture.conf').read_bytes(), b'configuration retained')
        with closing(sqlite3.connect(target / 'app/fixture.sqlite')) as c:
            self.assertEqual(c.execute('pragma integrity_check').fetchone()[0], 'ok')

    def test_bundle_traversal_is_refused(self):
        root = self.backup(); (root / 'private').mkdir()
        (root / 'private/sqlite-map.json').write_text('[]')
        with tarfile.open(root / 'private-state.tar.gz', 'w:gz') as archive:
            info = tarfile.TarInfo('../escaped'); info.size = 1
            archive.addfile(info, io.BytesIO(b'x'))
        self.manifest(root)
        with self.assertRaises(tarfile.FilterError):
            recovery.restore_bundle(root, self.root / 'isolated')
        self.assertFalse((self.root / 'escaped').exists())



    def capture_fixture(self, budget=10000000):
        source = self.root / 'source'; source.mkdir()
        (source / 'authored.txt').write_text('project source')
        db = source / 'service.db'
        with closing(sqlite3.connect(db)) as c, c:
            c.execute('create table fixture(value text)')
            c.execute("insert into fixture values ('consistent snapshot')")
        destination = self.root / 'captures'; destination.mkdir()
        policy = {'capture_roots': [str(source)], 'project_roots': [], 'exclude_directory_names': [],
                  'storage': [{'path': str(source), 'mode': 'capture', 'reason': 'fixture'}],
                  'capture_max_source_bytes': budget, 'minimum_free_bytes': 0}
        return source, destination, policy

    def test_capture_snapshots_sqlite_and_bundle_restores_it(self):
        source, parent, policy = self.capture_fixture()
        target = parent / '20261107T120000Z'
        with patch('recovery.CAPTURE_PARENT', parent), patch('recovery.K3S_DATABASE', self.root / 'absent'), \
             patch('recovery.inventory', return_value={'storage': []}), patch('recovery.command', return_value='{}'), \
             patch('recovery.subprocess.run'):
            value = recovery.capture(policy, target, True)
        self.assertEqual(value['result'], 'CAPTURED_NOT_OFFHOST_VERIFIED')
        entries = json.loads((target / 'private/sqlite-map.json').read_text())
        self.assertEqual(entries[0]['original'], str(source / 'service.db'))
        isolated = self.root / 'restored'
        recovery.restore_bundle(target, isolated)
        restored_db = isolated / str(source / 'service.db').lstrip('/')
        with closing(sqlite3.connect(restored_db)) as c:
            self.assertEqual(c.execute('select value from fixture').fetchone()[0], 'consistent snapshot')

    def test_capture_budget_failure_never_publishes_a_success_manifest(self):
        source, parent, policy = self.capture_fixture(budget=1)
        target = parent / '20261107T120001Z'
        with patch('recovery.CAPTURE_PARENT', parent), patch('recovery.K3S_DATABASE', self.root / 'absent'), \
             patch('recovery.inventory', return_value={'storage': []}), patch('recovery.command', return_value='{}'), \
             patch('recovery.subprocess.run'), self.assertRaisesRegex(ValueError, 'storage budget'):
            recovery.capture(policy, target, True)
        self.assertFalse((target / 'manifest.json').exists())


    def test_capture_exports_exact_running_docker_images_without_starting_them(self):
        source, parent, policy = self.capture_fixture()
        target = parent / '20261107T120002Z'
        inv = {'storage': [], 'docker': [{'running': True, 'image': 'fixture:current', 'imageID': 'sha256:fixture'}]}
        def probe(args, **kwargs):
            return json.dumps([{'Id': 'sha256:fixture', 'Size': 1024}]) if args[:3] == ['docker', 'image', 'inspect'] else '{}'
        def execute(args, **kwargs):
            if args[:3] == ['docker', 'image', 'save']:
                with tarfile.open(args[4], 'w') as archive:
                    data = b'[]'; info = tarfile.TarInfo('manifest.json'); info.size = len(data)
                    archive.addfile(info, io.BytesIO(data))
        with patch('recovery.CAPTURE_PARENT', parent), patch('recovery.K3S_DATABASE', self.root / 'absent'), \
             patch('recovery.inventory', return_value=inv), patch('recovery.command', side_effect=probe), \
             patch('recovery.subprocess.run', side_effect=execute) as calls:
            recovery.capture(policy, target, True)
        self.assertTrue((target / 'private/docker-images.tar.gz').exists())
        self.assertFalse((target / 'private/docker-images.tar').exists())
        self.assertTrue(all('start' not in str(call) and 'restart' not in str(call) for call in calls.call_args_list))
        recovery.verify_backup(target)

    def test_capture_refuses_a_docker_tag_that_changed_under_a_running_container(self):
        source, parent, policy = self.capture_fixture()
        target = parent / '20261107T120003Z'
        inv = {'storage': [], 'docker': [{'running': True, 'image': 'fixture:current', 'imageID': 'sha256:old'}]}
        def probe(args, **kwargs):
            return json.dumps([{'Id': 'sha256:new', 'Size': 1024}]) if args[:3] == ['docker', 'image', 'inspect'] else '{}'
        with patch('recovery.CAPTURE_PARENT', parent), patch('recovery.K3S_DATABASE', self.root / 'absent'), \
             patch('recovery.inventory', return_value=inv), patch('recovery.command', side_effect=probe), \
             patch('recovery.subprocess.run'), self.assertRaisesRegex(ValueError, 'Docker tag'):
            recovery.capture(policy, target, True)
        self.assertFalse((target / 'manifest.json').exists())

if __name__ == '__main__':
    unittest.main()
