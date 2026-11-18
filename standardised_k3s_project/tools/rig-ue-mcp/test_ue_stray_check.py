import json, os, sys, tempfile, unittest
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_stray_check as sc
from test_route_failures import run

Z0, RPC, PX, SEA = 3677.7, 4.4387, 800.0, 4849.26


def raw_of(z):
    return np.round((np.asarray(z, float) - Z0) * RPC).astype(np.uint16)


def island():
    """20 px map: sea floor (4700) on the left 4 columns, land at 6000, an inland bowl below sea level at 9..11."""
    z = np.full((20, 20), 6000.0)
    z[:, :4] = 4700.0
    z[9:12, 9:12] = 4700.0
    return raw_of(z)


def box(x, y, z, half=100.0):
    return {"x": x, "y": y, "z": z}, {"x": half, "y": half, "z": half}


class Foliage(unittest.TestCase):
    def setUp(self):
        self.raw = island()
        self.mask = sc.fb.sea_mask(self.raw, Z0, RPC, SEA)

    def test_floating_needs_more_than_float_cm_above_the_ground(self):
        ins = [{"index": 0, "x": 12000, "y": 4000, "z": 6000.0}, {"index": 1, "x": 12000, "y": 4000, "z": 6400.0}, {"index": 2, "x": 12000, "y": 4000, "z": 6600.0}]
        self.assertEqual(sc.find_floating(ins, self.raw, Z0, RPC, PX, 500.0), [2])
        self.assertEqual(sc.find_floating(ins, self.raw, Z0, RPC, PX, 300.0), [1, 2])

    def test_over_the_sea_floating_is_measured_from_the_sea_surface(self):
        ins = [{"index": 0, "x": 800, "y": 8000, "z": SEA + 400.0}, {"index": 1, "x": 800, "y": 8000, "z": SEA + 600.0}]
        self.assertEqual(sc.find_floating(ins, self.raw, Z0, RPC, PX, 500.0), [0, 1])            # no sea level known: from the sea floor
        self.assertEqual(sc.find_floating(ins, self.raw, Z0, RPC, PX, 500.0, sea_cm=SEA), [1])

    def test_classify_gives_one_verdict_per_stray_and_none_for_a_plant_on_the_ground(self):
        ins = [{"index": 0, "x": 12000, "y": 4000, "z": 6000.0},     # on the ground
               {"index": 1, "x": 12000, "y": 4000, "z": 9000.0},     # failed trace, high up
               {"index": 2, "x": 12000, "y": 4000, "z": 5800.0},     # sunk
               {"index": 3, "x": 800, "y": 8000, "z": 4700.0},       # on the sea floor
               {"index": 4, "x": 800, "y": 8000, "z": 9000.0},       # above the sea
               {"index": 5, "x": 8000, "y": 8000, "z": 4700.0}]      # in the inland bowl
        got = sc.classify_foliage(ins, self.raw, Z0, RPC, PX, sea_cm=SEA, mask=self.mask)
        self.assertEqual(got, {1: "sky", 2: "buried", 3: "ocean", 4: "sky"})
        self.assertEqual(sc.classify_foliage(ins, self.raw, Z0, RPC, PX, sea_cm=SEA)[5], "ocean")   # --inland-low: no mask
        self.assertEqual(sc.classify_foliage(ins, self.raw, Z0, RPC, PX), {1: "sky", 2: "buried", 4: "sky"})   # no sea level: no ocean check


class Actors(unittest.TestCase):
    def setUp(self):
        self.raw = island()
        self.mask = sc.fb.sea_mask(self.raw, Z0, RPC, SEA)

    def verdict(self, o, e, **kw):
        return sc.classify_actor(o, e, self.raw, Z0, RPC, PX, sea_cm=SEA, mask=self.mask, **kw)

    def test_an_actor_standing_on_the_ground_is_fine(self):
        v, ref, delta = self.verdict(*box(12000, 4000, 6100.0))
        self.assertIsNone(v)
        self.assertAlmostEqual(ref, 6000.0, delta=0.5)
        self.assertAlmostEqual(delta, 0.0, delta=0.5)

    def test_sky_is_the_lowest_point_of_the_bounds_far_above_the_ground(self):
        v, ref, delta = self.verdict(*box(12000, 4000, 7000.0))
        self.assertEqual(v, "sky")
        self.assertAlmostEqual(delta, 900.0, delta=0.5)
        self.assertIsNone(self.verdict(*box(12000, 4000, 6500.0))[0])                    # bottom 400 above: inside --float-cm
        self.assertEqual(self.verdict(*box(12000, 4000, 6500.0), float_cm=300.0)[0], "sky")

    def test_a_big_mesh_with_a_high_pivot_that_still_crosses_the_ground_is_not_a_stray(self):
        self.assertIsNone(self.verdict({"x": 8000, "y": 4000, "z": 20000.0}, {"x": 5e5, "y": 5e5, "z": 5e5})[0])

    def test_buried_is_the_highest_point_far_below_the_ground(self):
        v, ref, delta = self.verdict(*box(12000, 4000, 5700.0))
        self.assertEqual(v, "buried")
        self.assertAlmostEqual(delta, -200.0, delta=0.5)
        self.assertIsNone(self.verdict(*box(12000, 4000, 5850.0))[0])                    # top 50 below: inside --sink-cm

    def test_ocean_is_fully_under_the_sea_surface_over_edge_connected_sea_only(self):
        v, ref, delta = self.verdict(*box(800, 8000, 4600.0))
        self.assertEqual((v, ref), ("ocean", SEA))
        self.assertAlmostEqual(delta, 4700.0 - SEA, delta=0.5)
        self.assertIsNone(self.verdict(*box(800, 8000, 4800.0))[0])                      # pokes out of the water (a rock, a jetty)
        self.assertIsNone(self.verdict(*box(800, 8000, SEA + 150.0))[0])                 # floats on the sea: measured from the surface, not the floor
        self.assertEqual(self.verdict(*box(800, 8000, SEA + 900.0))[0], "sky")
        self.assertEqual(self.verdict(*box(8000, 8000, 4800.0))[0], None)                # inland bowl: not the sea, and it stands on the bowl floor
        self.assertEqual(sc.classify_actor(*box(8000, 8000, 4600.0), self.raw, Z0, RPC, PX, sea_cm=SEA)[0], "ocean")   # --inland-low

    def test_off_map_and_empty_bounds_are_named_not_measured(self):
        self.assertEqual(self.verdict(*box(-5000, 4000, 6100.0))[0], "off-map")
        self.assertEqual(self.verdict(*box(4000, 19 * PX + 1, 6100.0))[0], "off-map")
        self.assertEqual(self.verdict({"x": 12000, "y": 4000, "z": 9000.0}, {"x": 0, "y": 0, "z": 0})[0], "no-bounds")

    def test_actor_rows_reads_labels_and_locations_from_either_listing_shape(self):
        loc = {"x": 1, "y": 2, "z": 3}
        self.assertEqual(sc.actor_rows({"success": True, "actors": [{"label": "A", "class": "StaticMeshActor", "location": loc}, {"actorLabel": "B"}]}),
                         [{"label": "A", "location": loc}, {"label": "B", "location": None}])
        self.assertEqual(sc.actor_rows({"success": True, "actors": []}), [])


class Main(unittest.TestCase):
    """main() against the fake transport of test_route_failures (no rig)."""

    def argv(self, *extra):
        f = os.path.join(tempfile.mkdtemp(), "h.png")
        Image.fromarray(island()).save(f)
        return ["--heights", f, "--z0", str(Z0), "--raw-per-cm", str(RPC), "--size-m", str(19 * PX / 100.0), "--sea-cm", str(SEA)] + list(extra)

    def answer(self, move="ok"):
        bounds = {"Tower": (12000, 4000, 7000.0), "Hut": (12000, 4000, 6100.0), "Wreck": (800, 8000, 4600.0), "Lake_1": (12000, 12000, 7000.0)}

        def f(h, args):
            if h == "foliage.list_types":
                return json.dumps({"foliageTypes": [{"path": "/Game/F/FT_Tree.FT_Tree"}]})
            if h == "foliage.get_instances":
                return json.dumps({"types": [{"instances": [{"index": 0, "location": {"x": 12000, "y": 4000, "z": 6000.0}},
                                                            {"index": 1, "location": {"x": 12000, "y": 4000, "z": 9000.0}}]}]})
            if h == "level.get_actors_by_class":
                return json.dumps({"success": True, "actors": [{"label": k, "location": {"x": x, "y": y, "z": z - 100}} for k, (x, y, z) in bounds.items()]
                                   if args["className"] == "StaticMeshActor" else []})
            if h == "level.get_actor_bounds":
                x, y, z = bounds[args["actorLabel"]]
                return json.dumps({"success": True, "origin": {"x": x, "y": y, "z": z}, "extent": {"x": 100, "y": 100, "z": 100}})
            if h == "level.move_actor" and move != "ok":
                return '{"success": false, "message": "refused"}'
            return '{"success": true}'
        return f

    def test_dry_run_reports_and_changes_nothing(self):
        rc, fake, out = run(sc, self.argv(), self.answer())
        self.assertEqual(rc, 0)
        self.assertFalse([h for h in fake.heads() if h in ("foliage.remove_instances", "level.move_actor", "level.delete_actors", "level.save")])
        self.assertIn("FT_Tree #1", out)
        self.assertRegex(out, r"Tower .* sky")
        self.assertRegex(out, r"Wreck .* ocean")
        self.assertNotIn("Hut", out)
        self.assertNotIn("Lake_1", out)                                   # a water disc hangs over its bowl on purpose
        self.assertIn("sky 2, ocean 1, buried 0", out)
        self.assertIn("dry run", out)

    def test_apply_removes_foliage_seats_sky_actors_and_never_deletes_or_moves_an_ocean_actor(self):
        rc, fake, out = run(sc, self.argv("--apply"), self.answer())
        self.assertEqual(rc, 0)
        removed = [a for h, a in fake.calls if h == "foliage.remove_instances"]
        self.assertEqual(removed, [{"foliageTypePath": "/Game/F/FT_Tree.FT_Tree", "instanceIndices": [1]}])
        moves = [a for h, a in fake.calls if h == "level.move_actor"]
        self.assertEqual([m["actorLabel"] for m in moves], ["Tower"])
        self.assertEqual((moves[0]["location"]["x"], moves[0]["location"]["y"]), (12000, 4000))
        self.assertAlmostEqual(moves[0]["location"]["z"], 6900.0 + (6000.0 - 20.0 - 6900.0), delta=1.0)   # pivot z 6900, bottom 6900 -> 20 below ground
        self.assertFalse([h for h in fake.heads() if "delete" in h or h == "level.save"])

    def test_a_failed_move_exits_1(self):
        rc, fake, out = run(sc, self.argv("--apply"), self.answer(move="refused"))
        self.assertEqual(rc, 1)
        self.assertIn("MOVE FAILED", out)

    def test_no_actors_and_no_foliage_skip_their_pass(self):
        _, fake, _ = run(sc, self.argv("--no-actors"), self.answer())
        self.assertNotIn("level.get_actors_by_class", fake.heads())
        _, fake, _ = run(sc, self.argv("--no-foliage"), self.answer())
        self.assertNotIn("foliage.list_types", fake.heads())

    def test_a_stale_landscape_sample_prints_a_warning_but_still_succeeds(self):
        base = self.answer()

        def answer(h, a):
            if h == "landscape.get_height_region":
                return json.dumps({"heights": [99999]})
            return base(h, a)
        rc, fake, out = run(sc, self.argv("--no-actors", "--landscape", "L"), answer)
        self.assertEqual(rc, 0)
        self.assertIn("WARNING: --heights looks stale", out)

    def test_no_landscape_given_skips_the_freshness_check(self):
        rc, fake, out = run(sc, self.argv("--no-actors"), self.answer())
        self.assertNotIn("landscape.get_height_region", fake.heads())

    def test_a_failed_landscape_sample_is_a_note_not_a_failure(self):
        base = self.answer()

        def answer(h, a):
            if h == "landscape.get_height_region":
                return '{"success": false, "message": "refused"}'
            return base(h, a)
        rc, fake, out = run(sc, self.argv("--no-actors", "--landscape", "L"), answer)
        self.assertEqual(rc, 0)
        self.assertIn("NOTE: freshness check could not run", out)

    def test_a_failed_list_types_is_a_failure_not_a_silent_zero_strays(self):
        def answer(h, a):
            if h == "foliage.list_types":
                return '{"success": false, "message": "refused"}'
            self.fail("get_instances should not be reached after list_types fails")
        rc, fake, out = run(sc, self.argv("--no-actors"), answer)
        self.assertEqual(rc, 1)
        self.assertIn("LISTING foliage types FAILED", out)
        self.assertIn("read(s) FAILED", out)

    def test_zero_foliage_types_is_a_failure_not_an_empty_level(self):
        def answer(h, a):
            if h == "foliage.list_types":
                return json.dumps({"foliageTypes": []})
            self.fail("get_instances should not be reached with zero types")
        rc, fake, out = run(sc, self.argv("--no-actors"), answer)
        self.assertEqual(rc, 1)
        self.assertIn("read zero types", out)

    def test_a_failed_get_instances_is_a_failure_and_skips_that_type(self):
        def answer(h, a):
            if h == "foliage.list_types":
                return json.dumps({"foliageTypes": [{"path": "/Game/F/FT_Tree.FT_Tree"}]})
            if h == "foliage.get_instances":
                return '{"success": false, "message": "refused"}'
            self.fail("unexpected call %s" % h)
        rc, fake, out = run(sc, self.argv("--no-actors"), answer)
        self.assertEqual(rc, 1)
        self.assertIn("LISTING /Game/F/FT_Tree.FT_Tree instances FAILED", out)

    def test_apply_writes_a_removed_instances_receipt_for_foliage(self):
        with tempfile.TemporaryDirectory() as d:
            out_path = os.path.join(d, "removed.json")
            rc, fake, out = run(sc, self.argv("--apply", "--no-actors", "--out-removed", out_path), self.answer())
            self.assertEqual(rc, 0)
            receipt = json.load(open(out_path))
            self.assertEqual(receipt["removed"][0]["foliageTypePath"], "/Game/F/FT_Tree.FT_Tree")
            self.assertEqual(receipt["removed"][0]["instances"][0]["index"], 1)


class Underground(unittest.TestCase):
    def test_profile_names_the_actors_that_belong_underground(self):
        import argparse, json, tempfile
        import ue_project
        prof = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump({"underground_label_prefixes": "ZAS_Dgn_"}, prof)
        prof.close()
        ap = argparse.ArgumentParser()
        ap.add_argument("--underground-prefixes", default="")
        ue_project.apply(ap, ["--project", prof.name])
        self.assertEqual(ap.parse_args(["--project", prof.name]).underground_prefixes, "ZAS_Dgn_")


if __name__ == "__main__":
    unittest.main()
