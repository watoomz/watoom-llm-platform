import json
import os
import pathlib
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import game_validation as gv  # noqa: E402


def age_file(path, seconds_old):
    """Back-date a file's mtime so it clears MANIFEST_CACHE_MIN_AGE_SEC without waiting in real time."""
    t = time.time() - seconds_old
    os.utime(path, (t, t))


class ManifestCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = pathlib.Path(self.tmp.name) / 'proj'
        self.project.mkdir()
        self.cache_root = pathlib.Path(self.tmp.name) / 'cache'
        self.patcher = patch.object(gv, 'MANIFEST_CACHE_ROOT', self.cache_root)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def test_result_matches_a_plain_hash_with_no_cache_present(self):
        (self.project / 'a.txt').write_bytes(b'hello')
        age_file(self.project / 'a.txt', 10)
        got = gv.manifest(self.project)
        import hashlib
        self.assertEqual(got, {'a.txt': hashlib.sha256(b'hello').hexdigest()})

    def test_second_call_reuses_the_cached_hash_without_rereading_the_file(self):
        f = self.project / 'a.txt'
        f.write_bytes(b'hello')
        age_file(f, 10)
        first = gv.manifest(self.project)
        # Corrupt the bytes on disk but keep size+mtime identical: a real change can never do this (writing
        # necessarily updates mtime), so this is purely to prove the second call trusts the cache and does not
        # reopen the file.
        st = f.stat()
        with f.open('wb') as fh:
            fh.write(b'HELLO')
        os.utime(f, (st.st_atime, st.st_mtime))
        second = gv.manifest(self.project)
        self.assertEqual(first, second)

    def test_a_real_change_is_never_masked_by_the_cache(self):
        f = self.project / 'a.txt'
        f.write_bytes(b'hello')
        age_file(f, 10)
        first = gv.manifest(self.project)
        f.write_bytes(b'goodbye')
        age_file(f, 10)
        second = gv.manifest(self.project)
        self.assertNotEqual(first, second)

    def test_a_file_younger_than_the_grace_period_is_always_rehashed_even_if_cache_matches(self):
        # The grace period defends against the actual race: a file written "now" (mtime == now, whatever the
        # filesystem's tick granularity is) gets cached, then a SECOND write lands within that same tick --
        # same size, same mtime_ns, different bytes. Without the grace period that second write would be
        # silently masked by the cache. (If the write were aged first, as other tests do, this race cannot
        # occur -- that is exactly why this is the one test that must NOT call age_file.)
        f = self.project / 'a.txt'
        f.write_bytes(b'hello')
        gv.manifest(self.project)  # populate cache with "hello" while the file is still young
        st = f.stat()
        f.write_bytes(b'HELLO')
        os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns))  # force the identical mtime_ns as the first write
        second = gv.manifest(self.project)
        import hashlib
        self.assertEqual(second['a.txt'], hashlib.sha256(b'HELLO').hexdigest())

    def test_deleted_file_disappears_from_cache_and_result(self):
        f = self.project / 'a.txt'
        f.write_bytes(b'hello')
        age_file(f, 10)
        gv.manifest(self.project)
        f.unlink()
        got = gv.manifest(self.project)
        self.assertEqual(got, {})
        cache = json.loads(gv._manifest_cache_path(self.project).read_text())
        self.assertEqual(cache, {})

    def test_cache_lives_outside_the_hashed_directory(self):
        f = self.project / 'a.txt'
        f.write_bytes(b'hello')
        age_file(f, 10)
        gv.manifest(self.project)
        self.assertTrue(gv._manifest_cache_path(self.project).is_relative_to(self.cache_root))
        self.assertFalse(gv._manifest_cache_path(self.project).is_relative_to(self.project))

    def test_an_unwritable_cache_directory_still_returns_a_correct_manifest(self):
        f = self.project / 'a.txt'
        f.write_bytes(b'hello')
        age_file(f, 10)
        with patch.object(gv.MANIFEST_CACHE_ROOT.__class__, 'mkdir', side_effect=OSError('read-only')):
            got = gv.manifest(self.project)
        import hashlib
        self.assertEqual(got, {'a.txt': hashlib.sha256(b'hello').hexdigest()})

    def test_symlinks_are_still_rejected_exactly_as_before(self):
        real = self.project / 'real.txt'
        real.write_bytes(b'x')
        (self.project / 'link.txt').symlink_to(real)
        with self.assertRaises(ValueError):
            gv.manifest(self.project)

    def test_two_distinct_projects_never_share_a_cache_entry(self):
        p1 = self.project
        p2 = pathlib.Path(self.tmp.name) / 'proj2'
        p2.mkdir()
        (p1 / 'a.txt').write_bytes(b'one')
        (p2 / 'a.txt').write_bytes(b'two')
        age_file(p1 / 'a.txt', 10)
        age_file(p2 / 'a.txt', 10)
        r1 = gv.manifest(p1)
        r2 = gv.manifest(p2)
        self.assertNotEqual(r1['a.txt'], r2['a.txt'])


if __name__ == '__main__':
    unittest.main()
