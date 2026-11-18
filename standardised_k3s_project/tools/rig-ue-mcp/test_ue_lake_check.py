import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_lake_check as lc
from ue_lake_as_river import WATER_LAYER_MID, lake_region

PX = 793.6507936507936
RPC = 4.438741894094393
Z0 = 3678.0
LAKE = {"label": "L", "x": 20 * PX, "y": 20 * PX, "water_z": 8860.0, "radius_cm": 4043.0}


def raw(z):
    return int(round((z - Z0) * RPC))


def build(base_z, water_fn=None, base_read_fn=None):
    """Layers over the padded carve rectangle: base from base_z(vx, vy), Water from water_fn(vx, vy, base_raw) (default neutral)."""
    carve, bank = lake_region(LAKE["x"], LAKE["y"], LAKE["radius_cm"], PX, 350.0)
    read = lc.padded(carve, 2)
    w, h = read["maxX"] - read["minX"] + 1, read["maxY"] - read["minY"] + 1
    base, water, merged, computed = [], [], [], []
    for i in range(h):
        for j in range(w):
            vx, vy = read["minX"] + j, read["minY"] + i
            b = raw(base_z(vx, vy))
            wr = water_fn(vx, vy, b) if water_fn else WATER_LAYER_MID
            m = max(0, min(65535, b + wr - WATER_LAYER_MID))
            br = base_read_fn(b) if base_read_fn else b  # what the (sometimes wrong) base-layer read returned
            base.append(br)
            water.append(wr)
            merged.append(m)
            computed.append(max(0, min(65535, br + wr - WATER_LAYER_MID)))
    lay = {"w": w, "h": h, "rpc": RPC, "z0": Z0, "base": base, "water": water, "merged": merged, "computed": computed}
    return carve, read, lay, bank


def dist(vx, vy):
    return math.hypot(vx * PX - LAKE["x"], vy * PX - LAKE["y"])


def carved(vx, vy, b):
    """A correct carve: bed at water - 90cm inside the circle, ramp across the bank, untouched beyond -- like carve_lake_bank."""
    bank = 2 * PX
    target = LAKE["water_z"] - 90.0
    d = dist(vx, vy)
    oz = b / RPC + Z0
    if d <= LAKE["radius_cm"]:
        tz = min(oz, target)
    elif d <= LAKE["radius_cm"] + bank:
        tz = target + (oz - target) * (d - LAKE["radius_cm"]) / bank
    else:
        return WATER_LAYER_MID
    return WATER_LAYER_MID + raw(tz) - b


class Analyse(unittest.TestCase):
    def run_check(self, *a, **kw):
        carve, read, lay, bank = build(*a, **kw)
        return lc.analyse(LAKE, carve, read, lay, PX, bank)

    def test_a_correct_carve_on_gentle_ground_has_no_findings(self):
        res = self.run_check(lambda vx, vy: 9300.0 + 2.0 * vx, carved)
        self.assertEqual(res["findings"], {}, res)

    def test_the_live_corruption_is_caught_as_sea_clamp_and_seam(self):
        # T-0049 Lake_3/Lake_4: base fine, Water dragging the whole carve rectangle's middle to raw 0, so the "0 of N changed" carve
        # looked clean while the bed was at sea level with a cliff at the rectangle's edge
        carve, _ = lake_region(LAKE["x"], LAKE["y"], LAKE["radius_cm"], PX, 350.0)

        def corrupt(vx, vy, b):
            inner = carve["minX"] + 2 <= vx <= carve["maxX"] - 2 and carve["minY"] + 2 <= vy <= carve["maxY"] - 2
            return 7794 if inner else (18000 if carve["minX"] <= vx <= carve["maxX"] and carve["minY"] <= vy <= carve["maxY"] else WATER_LAYER_MID)
        res = self.run_check(lambda vx, vy: 9300.0, corrupt)
        self.assertIn("sea_clamp", res["findings"])
        self.assertIn("seam", res["findings"])
        self.assertIn("water_outside_ring", res["findings"])  # the rectangle's corners lie beyond radius + bank

    def test_leftover_water_offset_outside_the_ring_is_a_finding(self):
        res = self.run_check(lambda vx, vy: 9300.0, lambda vx, vy, b: WATER_LAYER_MID - 5 if dist(vx, vy) > 9000 else carved(vx, vy, b))
        self.assertIn("water_outside_ring", res["findings"])

    def test_ground_above_water_inside_the_circle_is_dry_inside(self):
        res = self.run_check(lambda vx, vy: 9300.0)  # never carved: bed 4.4 m above the water
        self.assertIn("dry_inside", res["findings"])

    def test_a_garbage_base_read_is_only_a_warning_and_changes_no_finding(self):
        # T-0049: editLayer:"Layer" read 53850 where the ground was 318; checks use the merged read, so nothing else may change
        res = self.run_check(lambda vx, vy: 9300.0, carved, base_read_fn=lambda b: 53850)
        self.assertEqual(res["findings"], {})
        self.assertIn("layer_read_mismatch", res["warnings"])

    def test_steep_natural_ground_is_not_called_a_seam(self):
        # a real hillside: big steps everywhere, including just outside the rectangle, so the border step is not exceptional
        res = self.run_check(lambda vx, vy: 9300.0 + 600.0 * vx, carved)
        self.assertNotIn("seam", res["findings"])


class CheckLake(unittest.TestCase):
    def fake(self, actor_reply):
        import json

        def call(cat, meth, args, what, timeout=180, fail_ok=False):
            if meth == "get_actor_details":
                return actor_reply
            reg = args["region"]
            w, h = reg["maxX"] - reg["minX"] + 1, reg["maxY"] - reg["minY"] + 1
            heights = [WATER_LAYER_MID] * (w * h) if args.get("editLayer") == "Water" else [raw(8000.0)] * (w * h)
            return json.dumps({"region": dict(reg, width=w, height=h), "heights": heights, "rawUnitsPerWorldCm": RPC,
                               "height": {"meanZ": 8000.0, "meanRaw": raw(8000.0)}})
        return call

    def test_a_missing_water_body_is_a_finding(self):
        res = lc.check_lake(self.fake('{"success": false, "error": "no actor"}'), "Land", LAKE, PX, 350.0, 2)
        self.assertIn("missing_actor", res["findings"])

    def test_a_present_water_body_lake_is_not(self):
        res = lc.check_lake(self.fake('{"success": true, "class": "WaterBodyLake"}'), "Land", LAKE, PX, 350.0, 2)
        self.assertNotIn("missing_actor", res["findings"])
        self.assertEqual(res["findings"], {})  # flat ground 8.6 m below the water: a filled bowl, nothing wrong


class LakeArgs(unittest.TestCase):
    def test_parse_lake(self):
        self.assertEqual(lc.parse_lake("ZAS_LakeBody_3,1,2,3,4"),
                         {"label": "ZAS_LakeBody_3", "x": 1.0, "y": 2.0, "water_z": 3.0, "radius_cm": 4.0})
        with self.assertRaises(ValueError):
            lc.parse_lake("1,2,3,4")

    def test_padded_clamps_to_the_map(self):
        self.assertEqual(lc.padded({"minX": 1, "minY": 0, "maxX": 503, "maxY": 504}, 2),
                         {"minX": 0, "minY": 0, "maxX": 504, "maxY": 504})


if __name__ == "__main__":
    unittest.main()
