import base64, json, os, sys, tempfile, unittest
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unreal_lake_smooth as ls

Z0, RPC, PX = 3677.7, 4.4387, 800.0
N, CY, CX, R, WATER = 80, 30, 30, 8.0, 5800.0
LAKE = {"x": CX * PX, "y": CY * PX, "z": WATER, "radius_m": R * PX / 100.0}


def raw_of(cm):
    return np.round((np.asarray(cm, float) - Z0) * RPC).astype(np.uint16)


def zc(raw):
    return raw.astype(float) / RPC + Z0


def max_step(z):
    """Largest height difference between 4-neighbours (cm)."""
    return max(np.abs(np.diff(z, axis=0)).max(), np.abs(np.diff(z, axis=1)).max())


class LakeSmooth(unittest.TestCase):
    def setUp(self):
        yy, xx = np.mgrid[0:N, 0:N]
        self.d = np.hypot(yy - CY, xx - CX)
        z = 6000.0 + 3.0 * xx                                    # gently sloping land
        z[self.d <= R] = 5500.0 - 200.0 * (1 - (self.d[self.d <= R] / R) ** 2)   # a bowl cut straight in: a 500 cm+ wall at the shore
        z[60:70, 60:70] = 7000.0                                 # a sharp-edged block far from the lake
        self.z, self.raw = z, raw_of(z)
        self.new, self.w, self.missed = ls.smooth(self.raw, [LAKE], Z0, RPC, PX, band_cm=2400.0)

    def test_the_sharp_lake_edge_is_smoothed(self):
        win = (slice(CY - 14, CY + 15), slice(CX - 14, CX + 15))
        before, after = max_step(zc(self.raw)[win]), max_step(zc(self.new)[win])
        self.assertGreater(before, 500.0)
        self.assertLess(after, 0.6 * before)
        self.assertEqual(self.missed, [])

    def test_more_passes_smooth_more(self):
        win = (slice(CY - 14, CY + 15), slice(CX - 14, CX + 15))
        four = ls.smooth(self.raw, [LAKE], Z0, RPC, PX, band_cm=2400.0, passes=4)[0]
        self.assertLess(max_step(zc(four)[win]), max_step(zc(self.new)[win]))

    def test_terrain_away_from_the_lake_is_untouched(self):
        far = self.d > R + 3 + 1.5                               # beyond the 3 px band (plus the half pixel of the waterline)
        self.assertTrue((self.new[far] == self.raw[far]).all())
        self.assertTrue((self.new[58:72, 58:72] == self.raw[58:72, 58:72]).all())   # the far block keeps its sharp edges
        self.assertTrue((self.w[far] == 0).all())
        self.assertTrue((self.new != self.raw).any())

    def test_the_lake_keeps_its_depth_level_and_shape(self):
        core = self.d <= R - 3 - 1.5
        self.assertTrue(core.sum() > 20)
        self.assertTrue((self.new[core] == self.raw[core]).all())                   # the middle of the bowl is bit-identical
        self.assertAlmostEqual(zc(self.new).min(), zc(self.raw).min(), delta=0.5)   # deepest point unchanged
        wet0, wet1 = (zc(self.raw) < WATER) & (self.d < 2 * R), (zc(self.new) < WATER) & (self.d < 2 * R)
        self.assertLess(abs(int(wet1.sum()) - int(wet0.sum())), 0.12 * wet0.sum())  # the waterline stays about where it was
        self.assertLess(np.abs(zc(self.new)[wet0].mean() - zc(self.raw)[wet0].mean()), 80.0)   # not flattened into the terrain
        self.assertTrue((zc(self.new)[self.d <= R - 2] < WATER - 150.0).all())      # still a lake two pixels in from the shore

    def test_a_small_lake_keeps_its_middle(self):
        yy, xx = np.mgrid[0:40, 0:40]
        d = np.hypot(yy - 20, xx - 20)
        z = np.full((40, 40), 6000.0)
        z[d <= 4] = 5400.0
        raw = raw_of(z)
        new, _, _ = ls.smooth(raw, [{"x": 20 * PX, "y": 20 * PX, "z": 5800.0, "radius_m": 32.0}], Z0, RPC, PX, band_cm=4000.0)
        self.assertTrue((new[d <= 1.5] == raw[d <= 1.5]).all())                     # the water-side fade is capped at half the radius
        self.assertTrue((new != raw).any())

    def test_low_ground_outside_the_reach_is_not_the_lake(self):
        z = self.z.copy()
        z[CY - 2:CY + 3, CX:] = 5700.0                           # a channel below the water level running from the lake to the map edge
        raw = raw_of(z)
        water = ls.lake_water(zc(raw), CX, CY, R, WATER, reach=1.5)
        self.assertTrue(water[CY, CX + 10] and not water[CY, CX + 14])
        new, w, _ = ls.smooth(raw, [LAKE], Z0, RPC, PX)
        self.assertTrue((new[:, CX + 20:] == raw[:, CX + 20:]).all())

    def test_a_lake_with_no_water_at_its_centre_is_reported_and_changes_nothing(self):
        dry = dict(LAKE, x=70 * PX, y=10 * PX)
        new, w, missed = ls.smooth(self.raw, [dry], Z0, RPC, PX)
        self.assertEqual(missed, [dry])
        self.assertTrue((new == self.raw).all())

    def test_lake_specs(self):
        self.assertEqual(ls.parse_lake("148000,212000,6120,56"), {"x": 148000.0, "y": 212000.0, "z": 6120.0, "radius_m": 56.0})
        self.assertEqual(ls.parse_lake("1,2,3,4,700")["radius_m"], 4.0)          # unreal_creek_profile.py's five-field form
        self.assertRaises(ValueError, ls.parse_lake, "1,2,3")
        d = tempfile.mkdtemp()
        json.dump({"pixel_cm": 800.0, "lakes": [{"creek": 1, "px": [30, 40], "radius_px": 6.0, "depth_cm": 500.0, "water_cm": 6100.0}], "phases": []}, open(d + "/creeks.json", "w"))
        self.assertEqual(ls.load_lakes(d + "/creeks.json"), [{"x": 32000.0, "y": 24000.0, "z": 6100.0, "radius_m": 48.0}])
        json.dump([{"x": 1, "y": 2, "z": 3, "radius_m": 4}], open(d + "/list.json", "w"))
        self.assertEqual(ls.load_lakes(d + "/list.json"), [{"x": 1.0, "y": 2.0, "z": 3.0, "radius_m": 4.0}])

    def test_main_writes_the_heights_the_changed_tiles_and_a_revert(self):
        d = tempfile.mkdtemp()
        Image.fromarray(self.raw).save(d + "/h.png")
        rc = ls.main(["--heights", d + "/h.png", "--lake", "%d,%d,%d,%d" % (LAKE["x"], LAKE["y"], WATER, LAKE["radius_m"]), "--z0", str(Z0), "--raw-per-cm", str(RPC),
                      "--size-m", str((N - 1) * PX / 100.0), "--landscape", "L", "--out", d + "/c.json", "--out-heights", d + "/o.png", "--out-revert", d + "/r.json"])
        self.assertEqual(rc, 0)
        self.assertTrue((np.asarray(Image.open(d + "/o.png")) == self.new).all())
        phases = json.load(open(d + "/c.json"))["phases"]
        self.assertEqual([p["name"] for p in phases], ["heights"])
        self.assertEqual(len(phases[0]["calls"]), 1)                                # the lake is inside the first 127 px tile
        head, args = phases[0]["calls"][0]
        self.assertEqual((head, args["actorLabel"]), ("landscape.set_height_region", "L"))
        reg = args["region"]
        blk = np.frombuffer(base64.b64decode(args["heightsBase64"]), "<u2").reshape(reg["maxY"] - reg["minY"] + 1, reg["maxX"] - reg["minX"] + 1)
        self.assertTrue((blk == self.new[reg["minY"]:reg["maxY"] + 1, reg["minX"]:reg["maxX"] + 1]).all())
        back = json.load(open(d + "/r.json"))["phases"][0]["calls"][0][1]
        old = np.frombuffer(base64.b64decode(back["heightsBase64"]), "<u2").reshape(blk.shape)
        self.assertTrue((old == self.raw[reg["minY"]:reg["maxY"] + 1, reg["minX"]:reg["maxX"] + 1]).all())

    def main_argv(self, d, heights_path, **extra):
        a = {"--heights": heights_path, "--lake": "%d,%d,%d,%d" % (LAKE["x"], LAKE["y"], WATER, LAKE["radius_m"]), "--z0": str(Z0),
             "--raw-per-cm": str(RPC), "--size-m": str((N - 1) * PX / 100.0), "--landscape": "L", "--out": d + "/c.json", "--out-heights": d + "/o.png"}
        a.update(extra)
        argv = []
        for k, v in a.items():
            argv += [k, v]
        return argv

    def test_an_8bit_heightmap_is_refused_not_silently_misread(self):
        d = tempfile.mkdtemp()
        Image.fromarray((self.raw // 256).astype(np.uint8)).save(d + "/h8.png")
        rc = ls.main(self.main_argv(d, d + "/h8.png"))
        self.assertEqual(rc, 1)
        self.assertFalse(os.path.exists(d + "/o.png"))
        self.assertFalse(os.path.exists(d + "/c.json"))

    def test_a_non_square_heightmap_is_refused(self):
        d = tempfile.mkdtemp()
        Image.fromarray(self.raw[:, :-5]).save(d + "/hwide.png")
        rc = ls.main(self.main_argv(d, d + "/hwide.png"))
        self.assertEqual(rc, 1)
        self.assertFalse(os.path.exists(d + "/o.png"))

    def test_raw_per_cm_must_be_positive(self):
        d = tempfile.mkdtemp()
        Image.fromarray(self.raw).save(d + "/h.png")
        rc = ls.main(self.main_argv(d, d + "/h.png", **{"--raw-per-cm": "0"}))
        self.assertEqual(rc, 1)
        self.assertFalse(os.path.exists(d + "/o.png"))

    def test_a_lake_outside_the_map_is_refused(self):
        d = tempfile.mkdtemp()
        Image.fromarray(self.raw).save(d + "/h.png")
        far = "%d,%d,%d,%d" % (999999999, 999999999, WATER, LAKE["radius_m"])
        rc = ls.main(self.main_argv(d, d + "/h.png", **{"--lake": far}))
        self.assertEqual(rc, 1)
        self.assertFalse(os.path.exists(d + "/o.png"))

    def fingerprint(self, path, raw):
        import hashlib
        json.dump({"sha256": hashlib.sha256(raw.tobytes()).hexdigest(), "landscape": "L", "fetchedAt": "2026-01-01T00:00:00+00:00"},
                  open(path + ".fingerprint.json", "w"))

    def test_a_heights_file_edited_after_its_fingerprint_is_refused(self):
        d = tempfile.mkdtemp()
        path = d + "/h.png"
        Image.fromarray(self.raw).save(path)
        self.fingerprint(path, self.raw)
        Image.fromarray(self.raw + 1).save(path)           # changed after the fingerprint was written
        rc = ls.main(self.main_argv(d, path))
        self.assertEqual(rc, 1)
        self.assertFalse(os.path.exists(d + "/o.png"))

    def test_a_heights_file_matching_its_fingerprint_is_not_refused(self):
        d = tempfile.mkdtemp()
        path = d + "/h.png"
        Image.fromarray(self.raw).save(path)
        self.fingerprint(path, self.raw)
        rc = ls.main(self.main_argv(d, path))
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.exists(d + "/o.png"))

    def test_every_lake_missed_does_not_write_output_files(self):
        d = tempfile.mkdtemp()
        Image.fromarray(self.raw).save(d + "/h.png")
        dry = "%d,%d,%d,%d" % (70 * PX, 10 * PX, WATER, LAKE["radius_m"])
        rc = ls.main(self.main_argv(d, d + "/h.png", **{"--lake": dry}))
        self.assertEqual(rc, 1)
        self.assertFalse(os.path.exists(d + "/o.png"))
        self.assertFalse(os.path.exists(d + "/c.json"))


if __name__ == "__main__":
    unittest.main()
