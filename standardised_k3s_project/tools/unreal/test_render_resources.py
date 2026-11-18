import unittest
from render_resources import profile
class Resources(unittest.TestCase):
    def test_host_reserve_and_ceiling(self):
        gib=1024**3
        for available in range(14,33):
            p=profile(available*gib,12)
            self.assertLessEqual(p["memory_max_bytes"]+p["host_reserve_bytes"],available*gib)
            self.assertLessEqual(p["memory_max_bytes"],24*gib)
            self.assertLess(p["memory_high_bytes"],p["memory_max_bytes"])
            self.assertEqual(p["cpu_quota"],"1000000 100000")
    def test_workers_follow_measured_memory(self):
        gib=1024**3
        self.assertEqual(profile(14*gib,12)["shader_workers"],3)
        self.assertEqual(profile(20*gib,12)["shader_workers"],4)
        self.assertEqual(profile(30*gib,12)["shader_workers"],6)
    def test_low_memory_rejected(self):
        with self.assertRaises(ValueError):profile(13*1024**3,12)
    def test_cpu_reserve(self):
        self.assertEqual(profile(20*1024**3,4)["cpu_quota"],"200000 100000")
if __name__=="__main__":unittest.main()
