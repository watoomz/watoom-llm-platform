import json, os, pathlib, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import terrain_stage as T


class Init(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.old_root = T.PROJECTS_ROOT
        T.PROJECTS_ROOT = pathlib.Path(self.tmp.name)
        self.project = pathlib.Path(self.tmp.name) / 'game'; self.project.mkdir()

    def tearDown(self):
        T.PROJECTS_ROOT = self.old_root; self.tmp.cleanup()

    def test_init_writes_a_valid_pairing(self):
        self.assertEqual(T.main(['init', '--project', str(self.project), '--job', 'j1']), 0)
        req = json.loads((self.project / '.opencode/terrain-jobs/j1/request.json').read_text())
        self.assertEqual(req, {'schema': 1, 'uproject_dir': '.opencode/tmp/j1', 'uproject_file': 'Terrain.uproject',
                                'script': 'export.py', 'deadline_sec': 900, 'memory_gib': 8})
        staging = self.project / '.opencode/tmp/j1'
        uproj = json.loads((staging / 'Terrain.uproject').read_text())
        self.assertEqual({p['Name'] for p in uproj['Plugins']}, {'PythonScriptPlugin', 'GLTFExporter'})
        self.assertIn('manifest.json', (staging / 'export.py').read_text())

    def test_init_refuses_a_job_name_already_staged(self):
        T.main(['init', '--project', str(self.project), '--job', 'j1'])
        self.assertEqual(T.main(['init', '--project', str(self.project), '--job', 'j1']), 2)

    def test_init_rejects_bad_job_names_and_out_of_range_budgets(self):
        self.assertEqual(T.main(['init', '--project', str(self.project), '--job', 'bad name']), 2)
        self.assertEqual(T.main(['init', '--project', str(self.project), '--job', 'j2', '--deadline-sec', '3600']), 2)
        self.assertEqual(T.main(['init', '--project', str(self.project), '--job', 'j3', '--memory-gib', '64']), 2)

    def test_init_rejects_a_project_outside_the_approved_root(self):
        outside = pathlib.Path(self.tmp.name).parent
        self.assertEqual(T.main(['init', '--project', str(outside), '--job', 'j1']), 2)


class Adopt(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.old_root = T.PROJECTS_ROOT
        T.PROJECTS_ROOT = pathlib.Path(self.tmp.name)
        self.project = pathlib.Path(self.tmp.name) / 'game'; self.project.mkdir()
        T.main(['init', '--project', str(self.project), '--job', 'old'])

    def tearDown(self):
        T.PROJECTS_ROOT = self.old_root; self.tmp.cleanup()

    def test_adopt_copies_the_staged_files_and_inherits_budgets(self):
        (self.project / '.opencode/tmp/old/export.py').write_text('# edited by the model\n')
        (self.project / '.opencode/tmp/old/output').mkdir()
        (self.project / '.opencode/tmp/old/output/manifest.json').write_text('{"status": "SUCCESS"}')
        self.assertEqual(T.main(['adopt', '--project', str(self.project), '--from-job', 'old', '--new-job', 'new']), 0)
        new_dir = self.project / '.opencode/tmp/new'
        self.assertEqual((new_dir / 'export.py').read_text(), '# edited by the model\n')
        self.assertFalse((new_dir / 'output').exists())  # prior run's output is not carried over
        req = json.loads((self.project / '.opencode/terrain-jobs/new/request.json').read_text())
        self.assertEqual((req['deadline_sec'], req['memory_gib']), (900, 8))

    def test_adopt_can_override_budgets(self):
        T.main(['adopt', '--project', str(self.project), '--from-job', 'old', '--new-job', 'new', '--deadline-sec', '120', '--memory-gib', '4'])
        req = json.loads((self.project / '.opencode/terrain-jobs/new/request.json').read_text())
        self.assertEqual((req['deadline_sec'], req['memory_gib']), (120, 4))

    def test_adopt_refuses_an_unknown_source_job(self):
        self.assertEqual(T.main(['adopt', '--project', str(self.project), '--from-job', 'nope', '--new-job', 'new']), 2)


if __name__ == '__main__':
    unittest.main()
