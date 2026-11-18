import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import game_terrain_export as gte  # noqa: E402


class DirectoryHashes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_plain_files_are_hashed(self):
        (self.root / 'a.uproject').write_text('{}')
        (self.root / 'script.py').write_text('pass')
        got = gte.directory_hashes(self.root)
        self.assertEqual(set(got), {'a.uproject', 'script.py'})

    def test_ue_generated_dirs_are_excluded(self):
        (self.root / 'a.uproject').write_text('{}')
        for d in ('Saved', 'Intermediate', 'DerivedDataCache', 'output'):
            sub = self.root / d
            sub.mkdir()
            (sub / 'junk.bin').write_bytes(b'x')
        got = gte.directory_hashes(self.root)
        self.assertEqual(set(got), {'a.uproject'})

    def test_excluded_dirs_nested_deeper_are_also_skipped(self):
        nested = self.root / 'Content' / 'Saved' / 'inner'
        nested.mkdir(parents=True)
        (nested / 'x.bin').write_bytes(b'x')
        (self.root / 'keep.py').write_text('pass')
        got = gte.directory_hashes(self.root)
        self.assertEqual(set(got), {'keep.py'})

    def test_a_real_content_file_under_content_is_kept(self):
        content = self.root / 'Content'
        content.mkdir()
        (content / 'Landscape.uasset').write_bytes(b'fake-uasset')
        got = gte.directory_hashes(self.root)
        self.assertIn('Content/Landscape.uasset', got)

    def test_changing_a_tracked_file_changes_its_hash(self):
        f = self.root / 'a.uproject'
        f.write_text('{"v":1}')
        first = gte.directory_hashes(self.root)
        f.write_text('{"v":2}')
        second = gte.directory_hashes(self.root)
        self.assertNotEqual(first['a.uproject'], second['a.uproject'])

    def test_symlink_inside_the_tree_is_rejected(self):
        real = self.root / 'real.py'
        real.write_text('pass')
        (self.root / 'link.py').symlink_to(real)
        with self.assertRaises(ValueError):
            gte.directory_hashes(self.root)

    def test_empty_directory_yields_empty_hashes(self):
        self.assertEqual(gte.directory_hashes(self.root), {})


if __name__ == '__main__':
    unittest.main()
