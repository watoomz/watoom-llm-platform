import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_creek_foliage as cf  # noqa: E402


class Receipt(unittest.TestCase):
    def test_receipt_holds_every_removed_instance_with_its_transform(self):
        insts = [{"type": "/T/A", "index": 0, "x": 1, "y": 2, "z": 3, "rotation": {"yaw": 9}, "scale": {"x": 1}},
                 {"type": "/T/A", "index": 1, "x": 4, "y": 5, "z": 6, "rotation": {"yaw": 0}, "scale": {"x": 2}},
                 {"type": "/T/B", "index": 0, "x": 7, "y": 8, "z": 9, "rotation": {}, "scale": {}}]
        path = os.path.join(tempfile.mkdtemp(), "r.json")
        n = cf.write_receipt(path, insts, [{"type": "/T/A", "index": 1}, {"type": "/T/B", "index": 0}])
        self.assertEqual(n, 2)
        rows = json.load(open(path))["removed"]
        self.assertEqual(rows[0], {"type": "/T/A", "index": 1, "location": {"x": 4, "y": 5, "z": 6}, "rotation": {"yaw": 0}, "scale": {"x": 2}})
        self.assertEqual(rows[1]["type"], "/T/B")


class Batches(unittest.TestCase):
    def test_adds_are_split_so_no_call_carries_thousands(self):
        self.assertEqual([len(b) for b in cf.batches(list(range(2031)), 200)], [200] * 10 + [31])

    def test_empty_gives_no_call(self):
        self.assertEqual(cf.batches([], 200), [])


if __name__ == "__main__":
    unittest.main()
