"""Offline operator CLI and filesystem boundary tests."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ADMIN = Path(__file__).resolve().parents[1] / 'admin'
FIXTURE = Path(__file__).parent / 'fixtures/mini-cards.jsonl'
spec = importlib.util.spec_from_file_location('wlk', ADMIN / 'wlk.py')
wlk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wlk)


class AdminTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'root'
        self.cards = self.base / 'input.jsonl'
        self.card = json.loads(FIXTURE.read_text().splitlines()[0])
        self.write([self.card])

    def write(self, cards):
        self.cards.write_text(''.join(json.dumps(c) + '\n' for c in cards))

    def snap(self, summary):
        card = dict(self.card, summary=summary)
        self.write([card])
        return wlk.snapshot(self.cards, self.root)

    def cli(self, *args):
        return subprocess.run([sys.executable, '-B', str(ADMIN / 'wlk.py'), *map(str, args)], capture_output=True, text=True)

    def test_fixture_and_counts(self):
        _, report = wlk.validate_bytes(FIXTURE.read_bytes())
        self.assertTrue(report['valid'])
        self.assertEqual(report['cards'], 5)
        self.assertEqual(report['products'], {'blender': 2, 'godot': 3})
        self.assertEqual(report['kinds']['api_method'], 3)

    def test_quarantine_not_healthy(self):
        for status, healthy in [('quarantined', 0), ('unverified', 0), ('verified', 1), ('source_checked', 1)]:
            with self.subTest(status=status):
                self.write([dict(self.card, status=status)])
                result = self.cli('validate', self.cards)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)['healthy'], healthy)

    def test_all_required_fields(self):
        for key in wlk.REQUIRED:
            card = self.card.copy()
            del card[key]
            with self.subTest(key=key):
                self.assertFalse(wlk.validate_bytes(json.dumps(card).encode())[1]['valid'])

    def test_bad_schema(self):
        changes = [{'id': '../evil'}, {'signature': '  '}, {'status': 'healthy'}, {'trust_tier': 'agent'},
                   {'kind': 'unknown'}, {'product': 'unknown'}, {'version': '4.x'}, {'summary': 'a' * 301},
                   {'params': [{}]}, {'params': [{'name': 1, 'type': '', 'default': None, 'doc': ''}]},
                   {'returns': []}, {'aliases': [1]}, {'constraints': 'none'}, {'examples': {}},
                   {'source': {}}, {'source': {'uri': '', 'revision': '4', 'span': 'x'}}, {'deprecated': 1}]
        for change in changes:
            with self.subTest(change=change):
                self.assertFalse(wlk.validate_bytes(json.dumps(dict(self.card, **change)).encode())[1]['valid'])
        for data in (b'', b'[]', b'{broken', b'null'):
            self.assertFalse(wlk.validate_bytes(data)[1]['valid'])

    def test_duplicate_and_invalid_exit(self):
        self.write([self.card, self.card])
        result = self.cli('validate', self.cards)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('duplicate', result.stdout)
        with self.assertRaises(ValueError):
            wlk.snapshot(self.cards, self.root)
        self.assertFalse(self.root.exists())

    def test_snapshot_manifest_idempotence(self):
        sid = wlk.snapshot(self.cards, self.root)
        directory = self.root / 'snapshots' / sid
        manifest_bytes = (directory / 'manifest.json').read_bytes()
        manifest = json.loads(manifest_bytes)
        self.assertEqual(manifest['sha256'], hashlib.sha256(self.cards.read_bytes()).hexdigest())
        self.assertEqual(manifest['cards'], 1)
        self.assertEqual(manifest['products'], {'godot': 1})
        self.assertTrue(manifest['created'])
        self.assertEqual((directory / 'cards.jsonl').read_bytes(), self.cards.read_bytes())
        self.assertEqual(wlk.snapshot(self.cards, self.root), sid)
        self.assertEqual((directory / 'manifest.json').read_bytes(), manifest_bytes)
        self.assertEqual(len(list((self.root / 'snapshots').iterdir())), 1)

    def test_activate_and_exact_rollback(self):
        first, second = self.snap('first'), self.snap('second')
        wlk.activate(first, self.root)
        # Preserve an existing absolute internal target exactly.
        active = self.root / 'cards.jsonl'
        active.unlink()
        original = str(self.root / 'snapshots' / first / 'cards.jsonl')
        active.symlink_to(original)
        wlk.activate(second, self.root)
        self.assertEqual(json.loads((self.root / 'previous').read_text()), original)
        wlk.activate(second, self.root)  # no-op must not overwrite rollback target
        wlk.rollback(self.root)
        self.assertEqual(os.readlink(active), original)
        wlk.rollback(self.root)
        self.assertEqual(os.readlink(active), f'snapshots/{second}/cards.jsonl')

    def test_first_activation_rollback_and_missing_previous(self):
        sid = self.snap('one')
        with self.assertRaises(ValueError):
            wlk.rollback(self.root)
        wlk.activate(sid, self.root)
        wlk.rollback(self.root)
        self.assertFalse(os.path.lexists(self.root / 'cards.jsonl'))
        wlk.rollback(self.root)
        self.assertTrue((self.root / 'cards.jsonl').is_symlink())

    def test_failed_activation_restores_previous(self):
        first, second = self.snap('first'), self.snap('second')
        wlk.activate(first, self.root)
        previous = (self.root / 'previous').read_bytes()
        real_atomic = wlk.atomic
        def fail(path, *args, **kwargs):
            if path.name == 'cards.jsonl':
                raise OSError('simulated publication failure')
            return real_atomic(path, *args, **kwargs)
        with patch.object(wlk, 'atomic', side_effect=fail):
            with self.assertRaises(OSError):
                wlk.activate(second, self.root)
        self.assertEqual((self.root / 'previous').read_bytes(), previous)
        self.assertIn(first, os.readlink(self.root / 'cards.jsonl'))

    def test_gc_protects_active_previous_and_dry_run(self):
        ids = [self.snap(str(i)) for i in range(5)]
        wlk.activate(ids[0], self.root)
        wlk.activate(ids[1], self.root)
        rows = wlk.inventory(self.root, keep=1)
        deleted = {row['id'] for row in rows if row['delete']}
        self.assertEqual(deleted, {ids[2], ids[3]})
        self.assertTrue(all((self.root / 'snapshots' / sid).exists() for sid in ids))
        wlk.inventory(self.root, keep=1, apply=True)
        self.assertEqual({p.name for p in (self.root / 'snapshots').iterdir()}, {ids[0], ids[1], ids[4]})
        wlk.inventory(self.root, keep=0, apply=True)
        self.assertEqual({p.name for p in (self.root / 'snapshots').iterdir()}, {ids[0], ids[1]})
        with self.assertRaises(ValueError):
            wlk.inventory(self.root, keep=-1)

    def test_corruption_refused(self):
        sid = self.snap('one')
        path = self.root / 'snapshots' / sid / 'cards.jsonl'
        path.write_text(path.read_text() + '\n')
        with self.assertRaises(ValueError):
            wlk.activate(sid, self.root)
        with self.assertRaises(ValueError):
            wlk.inventory(self.root, keep=0, apply=True)
        self.assertTrue(path.exists())

    def test_snapshot_ids_traversal(self):
        self.snap('one')
        for sid in ('..', '../outside', '/tmp', 'a/b', '.', 'f' * 15, 'F' * 16, 'f' * 16 + '/../x'):
            with self.subTest(sid=sid), self.assertRaises(ValueError):
                wlk.activate(sid, self.root)
        for symbol in ('../evil', 'foo/evil', 'foo\\evil', 'foo..evil'):
            card = dict(self.card, symbol=symbol, id=f'godot.{symbol}@4.7.2')
            self.assertFalse(wlk.validate_bytes(json.dumps(card).encode())[1]['valid'])

    def test_managed_symlinks_refused(self):
        outside = self.base / 'outside'
        outside.mkdir()
        self.root.mkdir()
        for relative in ('snapshots', 'previous', '.wlk.lock'):
            with self.subTest(relative=relative):
                link = self.root / relative
                link.unlink(missing_ok=True)
                link.symlink_to(outside)
                with self.assertRaises(ValueError):
                    wlk.snapshot(self.cards, self.root) if relative != 'previous' else wlk.inventory(self.root)
                link.unlink()
        self.assertEqual(list(outside.iterdir()), [])

    def test_external_or_traversing_active_target_refused(self):
        sid = self.snap('one')
        active = self.root / 'cards.jsonl'
        for target in (str(self.cards), '../input.jsonl', f'snapshots/{sid}/../{sid}/cards.jsonl'):
            active.symlink_to(target)
            with self.assertRaises(ValueError):
                wlk.inventory(self.root, keep=0, apply=True)
            active.unlink()
        (self.root / 'previous').write_text(json.dumps('../input.jsonl'))
        with self.assertRaises(ValueError):
            wlk.rollback(self.root)

    def test_snapshot_file_symlink_and_root_alias(self):
        sid = self.snap('one')
        path = self.root / 'snapshots' / sid / 'cards.jsonl'
        path.unlink()
        path.symlink_to(self.cards)
        with self.assertRaises(ValueError):
            wlk.activate(sid, self.root)
        alias = self.base / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            wlk.inventory(alias)

    def test_input_symlink_refused(self):
        alias = self.base / 'input-alias.jsonl'
        alias.symlink_to(self.cards)
        with self.assertRaises(ValueError):
            wlk.snapshot(alias, self.root)
        self.assertNotEqual(self.cli('validate', alias).returncode, 0)

    def test_corrupt_manifest_and_previous_symlink_refused(self):
        sid = self.snap('one')
        manifest = self.root / 'snapshots' / sid / 'manifest.json'
        data = json.loads(manifest.read_text())
        data['cards'] = 100
        manifest.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            wlk.activate(sid, self.root)
        data['cards'] = 1
        manifest.write_text(json.dumps(data))
        (self.root / 'previous').symlink_to(self.cards)
        with self.assertRaises(ValueError):
            wlk.activate(sid, self.root)

    def test_cli_lifecycle(self):
        result = self.cli('snapshot', '--cards', self.cards, '--root', self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        sid = json.loads(result.stdout)['id']
        for args in [('activate', sid, '--root', self.root), ('list', '--root', self.root),
                     ('gc', '--root', self.root, '--keep', '0'), ('rollback', '--root', self.root)]:
            result = self.cli(*args)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(self.cli('activate', '../bad', '--root', self.root).returncode, 0)


if __name__ == '__main__':
    unittest.main()
