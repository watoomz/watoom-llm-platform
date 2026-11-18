"""Verified-procedure evidence, secrets, revisions and runtime boundaries."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ADMIN = Path(__file__).resolve().parents[1] / 'admin'
spec = importlib.util.spec_from_file_location('procedures', ADMIN / 'procedures.py')
procedures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(procedures)
# Script-style fallback import for the optional card validator.
sys.path.insert(0, str(ADMIN))


class ProcedureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.receipts = self.base / 'receipts'
        self.receipts.mkdir()
        self.store = self.base / 'procedures.jsonl'
        receipt = b'Exit 0; expected imported scene exists. PASS\n'
        sha = hashlib.sha256(receipt).hexdigest()
        (self.receipts / sha).write_bytes(receipt)
        self.record = {'procedure_id': 'godot.import', 'project': 'test-project',
                       'runtime': {'godot': '4.7.2', 'blender': '5.2.3'},
                       'command_template': 'godot --headless --editor --import',
                       'preconditions': ['Project exists'],
                       'verification': {'command': 'test -f scene.gltf', 'result': 'PASS', 'receipt_sha256': sha},
                       'source_card_ids': ['godot.Node.add_child@4.7.2'],
                       'created_at': '2026-11-07T00:00:00Z', 'last_verified_at': '2026-11-07T01:00:00Z',
                       'trust': 'verified_local'}

    def add(self, record=None, **kwargs):
        return procedures.add(self.record if record is None else record, self.receipts, self.store, **kwargs)

    def test_add_idempotent_append_revisions(self):
        first = self.add()
        old_bytes = self.store.read_bytes()
        self.assertEqual(first['namespace'], 'verified:godot.import')
        self.assertEqual(first['revision'], 1)
        self.assertEqual(self.add(), first)
        self.assertEqual(self.store.read_bytes(), old_bytes)
        changed = dict(self.record, command_template='godot --headless --import')
        second = self.add(changed)
        self.assertEqual(second['revision'], 2)
        self.assertEqual(second['supersedes'], first['content_sha256'])
        self.assertTrue(self.store.read_bytes().startswith(old_bytes))
        self.assertEqual(procedures.list_valid(self.store), [changed])
        self.add()  # historical content is idempotent too
        self.assertEqual(len(self.store.read_text().splitlines()), 2)

    def test_runtime_filter_is_exact_and_latest_only(self):
        self.add()
        self.assertEqual(procedures.list_valid(self.store, {'blender': '5.2.3', 'godot': '4.7.2'}), [self.record])
        self.assertEqual(procedures.list_valid(self.store, {'godot': '4.7.3', 'blender': '5.2.3'}), [])
        changed = dict(self.record, runtime={'godot': '4.7.3', 'blender': '5.2.3'})
        self.add(changed)
        self.assertEqual(procedures.list_valid(self.store, self.record['runtime']), [])
        self.assertEqual(procedures.list_valid(self.store, changed['runtime']), [changed])

    def test_missing_store_and_multiple_ids(self):
        self.assertEqual(procedures.list_valid(self.store), [])
        self.add()
        second = dict(self.record, procedure_id='verified:godot.export')
        self.add(second)
        self.assertEqual(len(procedures.list_valid(self.store)), 2)

    def test_required_fields_and_schema(self):
        for key in procedures.FIELDS:
            record = copy.deepcopy(self.record)
            del record[key]
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.add(record)
        for change in ({'trust': 'official'}, {'preconditions': 'yes'}, {'source_card_ids': [7]},
                       {'created_at': 'yesterday'}, {'last_verified_at': '2026-11-06T00:00:00Z'},
                       {'created_at': '2026-11-07T00:00:00'}, {'extra': 'unknown'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.add(dict(self.record, **change))
        self.assertFalse(self.store.exists())

    def test_verification_and_receipt_failures(self):
        for result in ('FAIL', 'pass', '', None):
            record = copy.deepcopy(self.record)
            record['verification']['result'] = result
            with self.subTest(result=result), self.assertRaises(ValueError):
                self.add(record)
        record = copy.deepcopy(self.record)
        record['verification']['receipt_sha256'] = '0' * 64
        with self.assertRaises(FileNotFoundError):
            self.add(record)
        (self.receipts / self.record['verification']['receipt_sha256']).write_bytes(b'tampered')
        with self.assertRaises(ValueError):
            self.add()
        self.assertFalse(self.store.exists())

    def test_receipt_traversal(self):
        for value in ('../outside', '/tmp/receipt', 'a' * 64 + '/../../x', 'A' * 64, ''):
            record = copy.deepcopy(self.record)
            record['verification']['receipt_sha256'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.add(record)

    def test_symlink_receipt_store_and_parent(self):
        receipt = self.receipts / self.record['verification']['receipt_sha256']
        outside = self.base / 'outside'
        outside.write_bytes(receipt.read_bytes())
        receipt.unlink()
        receipt.symlink_to(outside)
        with self.assertRaises(ValueError):
            self.add()
        receipt.unlink()
        receipt.write_bytes(outside.read_bytes())
        self.store.symlink_to(outside)
        with self.assertRaises(ValueError):
            self.add()
        with self.assertRaises(ValueError):
            procedures.list_valid(self.store)
        alias = self.base / 'alias'
        alias.symlink_to(self.receipts, target_is_directory=True)
        with self.assertRaises(ValueError):
            procedures.add(self.record, alias, self.base / 'other.jsonl')

    def test_namespace_and_id_traversal(self):
        for pid in ('reference:godot.import', 'observed:foo', '../foo', '/foo', 'verified:../foo', 'a/b', 'a\\b', 'verified:', 'a..b'):
            with self.subTest(pid=pid), self.assertRaises(ValueError):
                self.add(dict(self.record, procedure_id=pid))

    def test_secret_patterns_in_every_text_location(self):
        secrets = ['api_key=example', 'API-KEY: example', 'Authorization: Bearer example',
                   '-----BEGIN RSA PRIVATE KEY-----\nexample\n-----END RSA PRIVATE KEY-----',
                   'password = example', "'token': 'example'", 'client_secret=example',
                   'sk-exampleKey123456', 'ghp_exampleCredential12345', 'AKIAABCDEFGHIJKLMNOP',
                   'b6714d92e8c30af5761de42c9507ba83d02f19ce',
                   'aZ7xQ2mN9vR4kL8pW3sT6yH1uF0dG5jB']
        for secret in secrets:
            for key in ('command_template', 'project', 'preconditions', 'verification', 'source_card_ids'):
                record = copy.deepcopy(self.record)
                if key == 'verification':
                    record[key]['command'] = secret
                elif key in ('preconditions', 'source_card_ids'):
                    record[key] = [secret]
                else:
                    record[key] = secret
                with self.subTest(secret=secret[:16], field=key), self.assertRaises(ValueError):
                    self.add(record)
        self.assertFalse(self.store.exists())

    def test_secret_dict_field_and_transcript_limit(self):
        record = copy.deepcopy(self.record)
        record['runtime']['password'] = '4.7.2'
        with self.assertRaises(ValueError):
            self.add(record)
        for key in ('command_template', 'preconditions', 'verification'):
            record = copy.deepcopy(self.record)
            if key == 'preconditions':
                record[key] = ['x' * 2001]
            elif key == 'verification':
                record[key]['command'] = 'x' * 2001
            else:
                record[key] = 'x' * 2001
            with self.subTest(field=key), self.assertRaises(ValueError):
                self.add(record)
        self.add(dict(self.record, command_template='x' * 2000))

    def test_safe_templates_and_receipt_hash_not_flagged(self):
        record = dict(self.record, command_template='godot --headless --path {project_dir}', preconditions=['Use ${PROJECT_DIR}'])
        self.add(record)
        self.assertEqual(procedures.list_valid(self.store), [record])

    def test_exact_runtime_validation(self):
        for runtime in ({'godot': '4.x'}, {'godot': '>=4.7.2'}, {}, [], 'Godot 4.x', 'Godot latest', 'Godot 4.7.2; Blender 5.x', 'Godot 4.7.2 Blender 5.2'):
            with self.subTest(runtime=runtime), self.assertRaises(ValueError):
                self.add(dict(self.record, runtime=runtime))
        record = dict(self.record, runtime='Godot 4.7.2; Blender 5.2.3')
        self.add(record)
        self.assertEqual(procedures.list_valid(self.store, record['runtime']), [record])

    def test_fragmented_transcript_rejected(self):
        record = dict(self.record, preconditions=['short line'] * 201)
        with self.assertRaises(ValueError):
            self.add(record)

    def test_parallel_identical_add_is_one_revision(self):
        record_file = self.base / 'record.json'
        record_file.write_text(json.dumps(self.record))
        args = [sys.executable, '-B', str(ADMIN / 'procedures.py'), 'add', str(record_file),
                '--receipts-dir', str(self.receipts), '--store', str(self.store)]
        workers = [subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(4)]
        for worker in workers:
            stdout, stderr = worker.communicate(timeout=10)
            self.assertEqual(worker.returncode, 0, stderr)
            self.assertEqual(json.loads(stdout)['revision'], 1)
        self.assertEqual(len(self.store.read_text().splitlines()), 1)

    def test_optional_cards(self):
        fixture = Path(__file__).parent / 'fixtures/mini-cards.jsonl'
        self.add(cards=fixture)
        record = dict(self.record, source_card_ids=['godot.Missing@4.7.2'])
        with self.assertRaises(ValueError):
            self.add(record, cards=fixture)
        # Without --cards, provenance ids are retained but membership is not checked.
        self.add(record)

    def test_tampered_or_partial_store_refused(self):
        self.add()
        original = self.store.read_text()
        entry = json.loads(original)
        entry['record']['command_template'] = 'other command'
        self.store.write_text(json.dumps(entry) + '\n')
        with self.assertRaises(ValueError):
            procedures.list_valid(self.store)
        self.store.write_text(original + '{')
        with self.assertRaises(ValueError):
            self.add(dict(self.record, command_template='changed'))
        self.assertTrue(self.store.read_text().endswith('{'))

    def test_cli_and_secret_error_redaction(self):
        record_file = self.base / 'record.json'
        record_file.write_text(json.dumps(self.record))
        args = [sys.executable, '-B', str(ADMIN / 'procedures.py')]
        result = subprocess.run(args + ['add', str(record_file), '--receipts-dir', str(self.receipts), '--store', str(self.store), '--cards', str(Path(__file__).parent / 'fixtures/mini-cards.jsonl')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run(args + ['list', '--store', str(self.store), '--runtime', json.dumps(self.record['runtime'])], capture_output=True, text=True)
        self.assertEqual(json.loads(result.stdout), [self.record])
        record_file.write_text('{"password=private-example"')
        result = subprocess.run(args + ['add', str(record_file), '--receipts-dir', str(self.receipts), '--store', str(self.store)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('private-example', result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
