import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sync_rig_projects as s  # noqa: E402


class SyncRigProjects(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.main = pathlib.Path(self.tmp.name) / 'main.json'
        self.rig = pathlib.Path(self.tmp.name) / 'rig.json'

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, path, **content):
        path.write_text(json.dumps(content))

    def test_new_main_project_gets_added_to_rig(self):
        self.write(self.main, projects=['/data/ai/projects/games/a', '/data/ai/projects/games/b'])
        self.write(self.rig, enabled=True, projects=['/data/ai/projects/games/fixture'], operations=['import'])
        added = s.sync(self.main, self.rig)
        self.assertEqual(sorted(added), ['/data/ai/projects/games/a', '/data/ai/projects/games/b'])
        rig = json.loads(self.rig.read_text())
        self.assertEqual(sorted(rig['projects']), sorted(['/data/ai/projects/games/a', '/data/ai/projects/games/b', '/data/ai/projects/games/fixture']))

    def test_fixture_project_never_removed_even_if_not_in_main_list(self):
        self.write(self.main, projects=['/data/ai/projects/games/a'])
        self.write(self.rig, projects=['/data/ai/projects/games/fixture'])
        s.sync(self.main, self.rig)
        rig = json.loads(self.rig.read_text())
        self.assertIn('/data/ai/projects/games/fixture', rig['projects'])

    def test_already_in_sync_makes_no_change_and_returns_false(self):
        self.write(self.main, projects=['/data/ai/projects/games/a'])
        self.write(self.rig, projects=['/data/ai/projects/games/a'])
        mtime_before = self.rig.stat().st_mtime_ns
        result = s.sync(self.main, self.rig)
        self.assertFalse(result)
        self.assertEqual(mtime_before, self.rig.stat().st_mtime_ns)

    def test_other_rig_config_fields_are_preserved(self):
        self.write(self.main, projects=['/data/ai/projects/games/a'])
        self.write(self.rig, enabled=True, stage_only=True, application={'namespace': 'x'}, activation_ms=123,
                  operations=['import', 'capture'], projects=[])
        s.sync(self.main, self.rig)
        rig = json.loads(self.rig.read_text())
        self.assertEqual(rig['enabled'], True)
        self.assertEqual(rig['stage_only'], True)
        self.assertEqual(rig['application'], {'namespace': 'x'})
        self.assertEqual(rig['activation_ms'], 123)
        self.assertEqual(rig['operations'], ['import', 'capture'])

    def test_missing_rig_config_returns_none_and_touches_nothing(self):
        self.write(self.main, projects=['/data/ai/projects/games/a'])
        result = s.sync(self.main, self.rig)
        self.assertIsNone(result)
        self.assertFalse(self.rig.exists())


if __name__ == '__main__':
    unittest.main()
