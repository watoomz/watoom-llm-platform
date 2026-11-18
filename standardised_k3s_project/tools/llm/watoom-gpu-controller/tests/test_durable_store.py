import json
import tempfile
import unittest
from pathlib import Path
from controller import State
from durable_store import DurableStore

class DurableStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/'state.json'
        self.store=DurableStore(self.path)
    def tearDown(self): self.tmp.cleanup()
    def test_initial_state(self): self.assertEqual(self.store.load(),State())
    def test_state_round_trip(self):
        s=State('mesh-active','job-123',9,False)
        self.store.save(s)
        self.assertEqual(DurableStore(self.path).load(),s)
        self.assertEqual(self.path.stat().st_mode & 0o777,0o600)
    def test_corrupt_state_fails_closed(self):
        self.path.write_text('{broken')
        with self.assertRaises(json.JSONDecodeError): self.store.load()
    def test_unknown_schema_fails_closed(self):
        self.path.write_text(json.dumps(dict(phase='qwen-ready',owner=None,generation=1,uncertain=False,extra=True)))
        with self.assertRaises(ValueError): self.store.load()
    def test_generation_persists(self):
        self.store.save(State('acquiring','job',17))
        self.assertEqual(DurableStore(self.path).load().generation,17)
