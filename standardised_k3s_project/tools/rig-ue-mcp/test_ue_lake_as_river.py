import json
import math
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_lake_as_river as lr


class FakeSlopedLandscape:
    """A fake `call(cat, meth, args, what, timeout=...)` backing carve_lake_bank with a landscape that slopes in X,
    so a ring too thin to span a vertex step is visible as a cliff instead of a gradient. Z(x) = z0_cm - slope*x.

    base_bug_delta (default 0) simulates the real map's bad base read (T-0049, 2026-11-18): editLayer:"Layer" returned garbage
    along whole vertex lines while the merged read and the Water layer were right -- carve_lake_bank must not use the base read."""

    def __init__(self, px_cm, rpc=4.438741894094393, z0=3678.0, slope=0.1, base_bug_delta=0):
        self.px_cm, self.rpc, self.z0, self.slope = px_cm, rpc, z0, slope
        self.base_bug_delta = base_bug_delta
        self.set_calls = []

    def z_at(self, x):
        return self.z0 + 2000.0 - self.slope * x  # offset so values stay comfortably positive/realistic

    def __call__(self, cat, meth, args, what, timeout=180):
        if meth == "get_height_region":
            # base Layer: this fake has no pre-existing Water-layer content (a fresh, never-carved slope), so Water reads
            # a flat 32768 (neutral) everywhere -- base_raw == true merged, same as a real pristine landscape.
            reg = args["region"]
            vx0, vy0, vx1, vy1 = reg["minX"], reg["minY"], reg["maxX"], reg["maxY"]
            w, h = vx1 - vx0 + 1, vy1 - vy0 + 1
            edit_layer = args.get("editLayer")
            if edit_layer == "Water":
                raw = [32768] * (w * h)
            else:
                raw = []
                for i in range(h):
                    for j in range(w):
                        x = (vx0 + j) * self.px_cm
                        base = int(round((self.z_at(x) - self.z0) * self.rpc))
                        raw.append(base + self.base_bug_delta if edit_layer == "Layer" else base)
            meanraw = sum(raw) / len(raw)
            meanz = meanraw / self.rpc + self.z0
            return json.dumps({"region": {"minX": vx0, "minY": vy0, "maxX": vx1, "maxY": vy1, "width": w, "height": h},
                                "heights": raw, "rawUnitsPerWorldCm": self.rpc,
                                "height": {"meanZ": meanz, "meanRaw": meanraw}})
        if meth == "set_height_region":
            self.set_calls.append(args)
            return json.dumps({"success": True})
        if meth == "merge_edit_layers":
            return json.dumps({"success": True})
        raise AssertionError("unexpected call: %s" % meth)


class CarveLakeBank(unittest.TestCase):
    def test_a_bank_narrower_than_one_vertex_step_is_widened_to_two_vertex_spacings(self):
        # this map's real vertex spacing (~793.65cm) is more than double the old flat 350cm bank-cm default: a ring that
        # thin has no vertex positioned inside it for most radii, so the ramp collapses into a single-vertex cliff
        # between "fully submerged" and "untouched original terrain" instead of a gradient -- harmless on flat ground,
        # a visible pit wall on sloped ground (found live, T-0049 2026-11-18). carve_lake_bank must widen it.
        px_cm = 793.6507936507936
        fake = FakeSlopedLandscape(px_cm, slope=0.0)  # flat terrain: isolates the margin/ring-width fix from slope effects
        cx, cy, water_z, r, narrow_bank_cm, submerge_cm = 50000.0, 50000.0, 5763.8, 2000.0, 350.0, 90.0
        lr.carve_lake_bank(None, fake, "Land", "/Game/Land", cx, cy, water_z, r, px_cm, narrow_bank_cm, submerge_cm)
        narrow_region = fake.set_calls[0]["region"]

        fake2 = FakeSlopedLandscape(px_cm, slope=0.0)
        effective_bank_cm = px_cm * 2.0
        lr.carve_lake_bank(None, fake2, "Land", "/Game/Land", cx, cy, water_z, r, px_cm, effective_bank_cm, submerge_cm)
        explicit_wide_region = fake2.set_calls[0]["region"]

        # the region carved with the narrow (350cm) request must match one carved with an EXPLICIT 2*px_cm request,
        # proving the narrow value was floored up to at least 2 vertex spacings rather than used as-is
        self.assertEqual(narrow_region, explicit_wide_region)
        # and that floor must be strictly wider than what the raw 350cm request would have produced
        naive_margin = r * 0.25 + narrow_bank_cm + 200.0
        naive_vx0 = max(int((cx - r - naive_margin) / px_cm) - 1, 0)
        self.assertLess(narrow_region["minX"], naive_vx0)

    def test_the_ramp_has_a_real_intermediate_step_not_a_single_vertex_cliff(self):
        px_cm = 793.6507936507936
        fake = FakeSlopedLandscape(px_cm, slope=0.0)
        cx, cy, water_z, r, submerge_cm = 50000.0, 50000.0, 5763.8, 2000.0, 90.0
        lr.carve_lake_bank(None, fake, "Land", "/Game/Land", cx, cy, water_z, r, px_cm, 350.0, submerge_cm)
        written = fake.set_calls[0]
        out, reg = written["heights"], written["region"]
        w = reg["maxX"] - reg["minX"] + 1
        row_i = int(round(cy / px_cm)) - reg["minY"]
        rpc, z0 = fake.rpc, fake.z0
        # decode through the real additive formula (base_raw == merged_raw here, see FakeSlopedLandscape): merged after the
        # write is base_raw + (written_water_raw - WATER_LAYER_MID), not the written value treated as an absolute height.
        base_row = [int(round((fake.z_at((reg["minX"] + j) * px_cm) - z0) * rpc)) for j in range(w) if (reg["minX"] + j) * px_cm >= cx]
        water_row = [out[row_i * w + j] for j in range(w) if (reg["minX"] + j) * px_cm >= cx]
        zs = [(b + (wr - lr.WATER_LAYER_MID)) / rpc + z0 for b, wr in zip(base_row, water_row)]
        submerged_floor = water_z - submerge_cm
        original_flat_z = fake.z_at(cx + r + 50.0 * px_cm)  # well outside the (widened) ring, untouched
        intermediate = [z for z in zs if submerged_floor + 1.0 < z < original_flat_z - 1.0]
        self.assertGreater(len(intermediate), 0,
                            "no intermediate ramp height -- carve jumped straight from submerged to original: %r" % zs)

    def test_writing_the_merged_raw_directly_would_have_corrupted_every_written_vertex(self):
        # regression test for the real bug (T-0049, 2026-11-18): the old code wrote the MERGED target raw straight into the
        # additive Water layer. Prove the new code does NOT do that -- for a vertex explicitly meant to be a no-op (well
        # outside the ring, untouched), the written Water raw must decode back to the ORIGINAL merged height, not merely
        # equal the original raw value re-interpreted as an absolute height.
        px_cm = 793.6507936507936
        fake = FakeSlopedLandscape(px_cm, slope=0.0)
        cx, cy, water_z, r, submerge_cm = 50000.0, 50000.0, 5763.8, 2000.0, 90.0
        lr.carve_lake_bank(None, fake, "Land", "/Game/Land", cx, cy, water_z, r, px_cm, 350.0, submerge_cm)
        written = fake.set_calls[0]
        out, reg = written["heights"], written["region"]
        w = reg["maxX"] - reg["minX"] + 1
        rpc, z0 = fake.rpc, fake.z0
        # a corner of the write region, far outside the circle+ring: must be an exact no-op
        j, i = 0, 0
        x = (reg["minX"] + j) * px_cm
        base_raw = int(round((fake.z_at(x) - z0) * rpc))
        water_raw = out[i * w + j]
        merged_raw_after = base_raw + (water_raw - lr.WATER_LAYER_MID)
        self.assertEqual(merged_raw_after, base_raw,
                          "a vertex outside the carve ring must round-trip to its original height, not drift")
        # and the naive (buggy) write -- using the merged/original raw AS the new Water raw -- would NOT have been a no-op,
        # proving this is a real regression test and not a tautology
        self.assertNotEqual(base_raw, base_raw + (base_raw - lr.WATER_LAYER_MID))

    def test_a_garbage_base_layer_read_does_not_change_the_carve(self):
        # T-0049 (2026-11-18): editLayer:"Layer" read 32549 / 53850 on flat ground whose real height was 318 (lines x=126, y=126),
        # while the merged read and the Water layer were right. The carve must use merged + Water only.
        px_cm = 793.6507936507936
        cx, cy, water_z, r, submerge_cm = 50000.0, 50000.0, 5763.8, 2000.0, 90.0

        clean = FakeSlopedLandscape(px_cm, slope=0.0)
        lr.carve_lake_bank(None, clean, "Land", "/Game/Land", cx, cy, water_z, r, px_cm, 350.0, submerge_cm)

        buggy = FakeSlopedLandscape(px_cm, slope=0.0, base_bug_delta=20000)
        lr.carve_lake_bank(None, buggy, "Land", "/Game/Land", cx, cy, water_z, r, px_cm, 350.0, submerge_cm)

        self.assertEqual(clean.set_calls[0]["heights"], buggy.set_calls[0]["heights"],
                          "a wrong base read changed the carve -- it must be built from the merged and Water reads only")

    def test_an_explicitly_wider_bank_is_left_alone(self):
        px_cm = 793.6507936507936
        fake = FakeSlopedLandscape(px_cm)
        lr.carve_lake_bank(None, fake, "Land", "/Game/Land", 50000.0, 50000.0, 5763.8, 2000.0, px_cm, 5000.0, 90.0)
        written = fake.set_calls[0]
        reg = written["region"]
        # margin uses the (unchanged, already-wide-enough) caller bank_cm of 5000, not the 2*px_cm floor
        expected_margin = 2000.0 * 0.25 + 5000.0 + 200.0
        expected_vx0 = max(int((50000.0 - 2000.0 - expected_margin) / px_cm) - 1, 0)
        self.assertEqual(reg["minX"], expected_vx0)


class CircleSpline(unittest.TestCase):
    def test_every_point_sits_exactly_on_the_circle(self):
        cx, cy, z, r, n = 177777.78, 167460.32, 8607.86, 12250.0, 32
        text = lr.circle_spline_text(cx, cy, z, r, n)
        pos_block = text[text.index("Position=") : text.index("Rotation=")]
        pts = re.findall(r"OutVal=\(X=([\d.\-]+),Y=([\d.\-]+),Z=([\d.\-]+)\)", pos_block)
        self.assertEqual(len(pts), n)
        for x, y, zz in pts:
            d = math.hypot(float(x) - cx, float(y) - cy)
            self.assertAlmostEqual(d, r, places=3)
            self.assertAlmostEqual(float(zz), z, places=3)

    def test_point_zero_has_no_invalprefix_the_rest_do(self):
        text = lr.circle_spline_text(0, 0, 0, 1000, 8)
        pos_block = text[text.index("Position=") : text.index("Rotation=")]
        self.assertTrue(pos_block.startswith("Position=(Points=((OutVal="))
        self.assertEqual(pos_block.count("InVal="), 7)  # points 1..7, not point 0

    def test_tangents_wrap_around_with_no_clamping(self):
        # a closed loop: point 0's tangent uses point (n-1) and point 1, not a clamped end
        text = lr.circle_spline_text(0, 0, 0, 1000, 4)
        first_tangent = re.search(r"ArriveTangent=\(X=([\d.\-]+),Y=([\d.\-]+)", text)
        tx, ty = float(first_tangent.group(1)), float(first_tangent.group(2))
        self.assertFalse(tx == 0 and ty == 0)


class WidthDepthCurve(unittest.TestCase):
    def test_one_point_per_spline_point_flat_value(self):
        text = lr.curve(26000.0, 5)
        self.assertEqual(text.count("OutVal=26000.0"), 5)
        self.assertEqual(text.count("InVal="), 4)  # points 1..4

class OldRiverRecipeRefused(unittest.TestCase):
    def test_main_refuses_the_flooding_river_recipe_without_the_explicit_flag(self):
        # T-0027: the closed-loop WaterBodyRiver lake flooded the forest; nothing may reach the rig unless the caller insists
        from unittest import mock
        with mock.patch.object(lr.ue_route, "SshTransport", side_effect=AssertionError("must not connect")), mock.patch("sys.stdout"):
            rc = lr.main(["--label", "L", "--center-x", "0", "--center-y", "0", "--water-z", "0", "--radius-cm", "100", "--material", "/Game/M"])
        self.assertEqual(rc, 2)


class Region(unittest.TestCase):
    def test_lake_region_matches_what_carve_lake_bank_writes(self):
        px_cm = 793.6507936507936
        fake = FakeSlopedLandscape(px_cm, slope=0.0)
        lr.carve_lake_bank(None, fake, "Land", "/Game/Land", 50000.0, 50000.0, 5763.8, 2000.0, px_cm, 350.0, 90.0)
        region, bank = lr.lake_region(50000.0, 50000.0, 2000.0, px_cm, 350.0)
        self.assertEqual(fake.set_calls[0]["region"], region)
        self.assertEqual(bank, 2 * px_cm)

    def test_clear_water_region_writes_neutral_over_the_whole_rectangle_then_merges(self):
        seen = []
        n = lr.clear_water_region(lambda c, m, a, w: seen.append((m, a)) or "{}", "Land", "/Game/Land",
                                  {"minX": 2, "minY": 3, "maxX": 4, "maxY": 3})
        self.assertEqual(n, 3)
        self.assertEqual(seen[0][1]["heights"], [lr.WATER_LAYER_MID] * 3)
        self.assertEqual(seen[0][1]["editLayer"], "Water")
        self.assertEqual(seen[1][0], "merge_edit_layers")


class Revert(unittest.TestCase):
    def test_revert_restores_the_water_values_read_before_any_write(self):
        import tempfile
        px_cm = 793.65
        fake = FakeSlopedLandscape(px_cm)
        region, _ = lr.lake_region(50000.0, 50000.0, 2000.0, px_cm, 350.0)
        path = os.path.join(tempfile.mkdtemp(), "rev.json")
        n = lr.write_water_revert(fake, "Land", "/Game/Land", region, path)
        self.assertEqual(fake.set_calls, [])                      # reading only; nothing written to the landscape
        with open(path) as f:
            calls = json.load(f)["phases"][0]["calls"]
        (m1, a1), (m2, a2) = calls
        self.assertEqual((m1, a1["editLayer"], a1["heightSpace"], a1["region"]), ("landscape.set_height_region", "Water", "raw", region))
        self.assertEqual(len(a1["heights"]), n)
        self.assertEqual(set(a1["heights"]), {32768})             # the fake's current Water values, restored verbatim
        self.assertEqual(m2, "landscape.merge_edit_layers")


if __name__ == "__main__":
    unittest.main()
