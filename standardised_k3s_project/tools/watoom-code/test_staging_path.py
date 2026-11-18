import os, pathlib, tempfile, unittest
import game_godot_game as G


class StagingPath(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.p = pathlib.Path(self.tmp.name) / 'proj'
        (self.p / '.opencode/tmp').mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_plain_folder_and_not_yet_created_folder_pass(self):
        (self.p / '.opencode/tmp/a').mkdir()
        G.check_staging_path(self.p, self.p / '.opencode/tmp/a')
        G.check_staging_path(self.p, self.p / '.opencode/tmp/new/deeper')

    def test_a_link_anywhere_on_the_path_is_refused(self):
        elsewhere = pathlib.Path(self.tmp.name) / 'elsewhere'; elsewhere.mkdir()
        os.symlink(elsewhere, self.p / '.opencode/tmp/a')
        with self.assertRaisesRegex(ValueError, 'link'): G.check_staging_path(self.p, self.p / '.opencode/tmp/a')
        with self.assertRaisesRegex(ValueError, 'link'): G.check_staging_path(self.p, self.p / '.opencode/tmp/a/sub')
        (self.p / '.opencode/tmp').rename(self.p / '.opencode/real'); os.symlink(elsewhere, self.p / '.opencode/tmp')
        with self.assertRaisesRegex(ValueError, 'link|real folder'): G.check_staging_path(self.p, self.p / '.opencode/tmp/x')


if __name__ == '__main__':
    unittest.main()
