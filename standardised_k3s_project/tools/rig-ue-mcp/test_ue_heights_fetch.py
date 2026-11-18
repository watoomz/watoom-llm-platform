import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_heights_fetch as hf


class Tiles(unittest.TestCase):
    def test_tiles_cover_the_map_exactly_once(self):
        seen = set()
        for x0, y0, x1, y1 in hf.tile_ranges(505, 127):
            for y in range(y0, y1 + 1):
                for x in range(x0, x1 + 1):
                    self.assertNotIn((x, y), seen)
                    seen.add((x, y))
        self.assertEqual(len(seen), 505 * 505)


class FetchTile(unittest.TestCase):
    def test_the_png_is_the_merged_read_and_water_only_counts_offsets(self):
        # T-0049: the editLayer:"Layer" read is wrong on whole lines of this map; the merged read is the visible height
        import json
        seen = []

        def run(cmd, **kw):
            seen.append(cmd)
            blocks = "".join("[landscape.get_height_region] %s\n" % json.dumps({"success": True, "heights": h})
                             for h in ([318, 9000], [32768, 30000]))
            return type("R", (), {"stdout": blocks, "stderr": ""})()
        merged, offsets = hf.fetch_tile("Land", {"minX": 0, "minY": 0, "maxX": 1, "maxY": 0}, run=run)
        self.assertEqual((merged.tolist(), offsets), ([318, 9000], 1))
        layers = [json.loads(c[c.index("{"):]).get("editLayer") for c in seen[0][4:]]
        self.assertEqual(layers, [None, "Water"])  # never the base Layer

    def test_a_missing_block_fails_the_tile(self):
        run = lambda cmd, **kw: type("R", (), {"stdout": '[x] {"success": true, "heights": [1]}\n', "stderr": ""})()  # noqa: E731
        with self.assertRaises(SystemExit):
            hf.fetch_tile("Land", {"minX": 0, "minY": 0, "maxX": 0, "maxY": 0}, run=run)


if __name__ == "__main__":
    unittest.main()
