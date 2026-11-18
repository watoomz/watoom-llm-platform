import unittest
from animation_sampling import loop_frame
class Tests(unittest.TestCase):
 def test_repeated_motion_at_source_speed(self):
  values=[loop_frame(f,1,10,30,1,31) for f in range(1,31)]
  self.assertEqual(values[:10],values[10:20]);self.assertEqual(values[:10],values[20:]);self.assertEqual(values[1],4)
 def test_fractional_sampling(self):self.assertAlmostEqual(loop_frame(2,1,24,30,1,31),2.25)
 def test_invalid_action(self):
  with self.assertRaises(ValueError):loop_frame(1,1,30,30,1,1)
if __name__=='__main__':unittest.main()
