import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import terrain_spec  # noqa: E402


class TerrainSpec(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = pathlib.Path(self.tmp.name) / 'proj'
        self.staging = self.project / '.opencode/tmp/terrain'
        self.staging.mkdir(parents=True)
        (self.staging / 'Game.uproject').write_text('{"FileVersion":3}')
        (self.staging / 'extract.py').write_text('print("hi")')
        self.jobdir = self.project / '.opencode/terrain-jobs/t1'
        self.jobdir.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def write_request(self, **overrides):
        req = {'schema': 1, 'uproject_dir': '.opencode/tmp/terrain', 'uproject_file': 'Game.uproject', 'script': 'extract.py'}
        req.update(overrides)
        (self.jobdir / 'request.json').write_text(json.dumps(req))

    def test_valid_request_loads_with_defaults(self):
        self.write_request()
        spec = terrain_spec.load(self.project, 't1')
        self.assertEqual(spec['deadline_sec'], 900)
        self.assertEqual(spec['memory_gib'], 8)
        self.assertEqual(spec['directory'], '.opencode/tmp/terrain')
        self.assertIn('terrain_spec_sha256', spec)

    def test_deadline_sec_out_of_range_rejected(self):
        self.write_request(deadline_sec=3000)
        with self.assertRaises(ValueError):
            terrain_spec.load(self.project, 't1')

    def test_memory_gib_out_of_range_rejected(self):
        self.write_request(memory_gib=32)
        with self.assertRaises(ValueError):
            terrain_spec.load(self.project, 't1')

    def test_uproject_dir_outside_opencode_tmp_rejected(self):
        self.write_request(uproject_dir='scenes/terrain')
        with self.assertRaises(ValueError):
            terrain_spec.load(self.project, 't1')

    def test_uproject_dir_traversal_rejected(self):
        self.write_request(uproject_dir='.opencode/tmp/../../etc')
        with self.assertRaises(ValueError):
            terrain_spec.load(self.project, 't1')

    def test_script_with_path_separator_rejected(self):
        self.write_request(script='../../etc/passwd.py')
        with self.assertRaises(ValueError):
            terrain_spec.load(self.project, 't1')

    def test_script_wrong_extension_rejected(self):
        self.write_request(script='extract.sh')
        with self.assertRaises(ValueError):
            terrain_spec.load(self.project, 't1')

    def test_missing_script_file_rejected(self):
        self.write_request(script='missing.py')
        with self.assertRaises(ValueError):
            terrain_spec.load(self.project, 't1')

    def test_unknown_extra_key_rejected(self):
        self.write_request()
        req = json.loads((self.jobdir / 'request.json').read_text())
        req['extra'] = 'nope'
        (self.jobdir / 'request.json').write_text(json.dumps(req))
        with self.assertRaises(ValueError):
            terrain_spec.load(self.project, 't1')

    def test_symlinked_uproject_dir_rejected(self):
        real = self.project / '.opencode/tmp/real'
        real.mkdir(parents=True)
        (real / 'Game.uproject').write_text('{}')
        (real / 'extract.py').write_text('pass')
        link = self.project / '.opencode/tmp/terrain2'
        link.symlink_to(real)
        self.write_request(uproject_dir='.opencode/tmp/terrain2')
        with self.assertRaises(ValueError):
            terrain_spec.load(self.project, 't1')

    def test_changing_the_script_changes_the_sha(self):
        self.write_request()
        first = terrain_spec.load(self.project, 't1')['terrain_spec_sha256']
        (self.staging / 'extract.py').write_text('print("different")')
        second = terrain_spec.load(self.project, 't1')['terrain_spec_sha256']
        self.assertNotEqual(first, second)

    def test_invalid_job_name_rejected(self):
        with self.assertRaises(ValueError):
            terrain_spec.load(self.project, '../etc')

    def test_revision_changes_when_spec_changes(self):
        self.write_request()
        r1 = terrain_spec.revision(self.project, 't1')
        (self.staging / 'extract.py').write_text('print("edited")')
        r2 = terrain_spec.revision(self.project, 't1')
        self.assertNotEqual(r1, r2)

    def test_revision_unaffected_by_unrelated_project_files(self):
        self.write_request()
        r1 = terrain_spec.revision(self.project, 't1')
        (self.project / 'unrelated_scene.tscn').write_text('irrelevant Godot source')
        r2 = terrain_spec.revision(self.project, 't1')
        self.assertEqual(r1, r2)


if __name__ == '__main__':
    unittest.main()
