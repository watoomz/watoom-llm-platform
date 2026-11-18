"""A failed ue-mcp reply must stop the helpers before they save or build on it (fake transport, no rig, no network)."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_route
import ue_run_phases
import ue_foliage_buried
import ue_place_assets
import ue_village_build
import ue_creek_foliage

Z0, RPC = 3677.7, 4.4387
OK, FAIL = '{"success": true}', '{"success": false, "message": "refused"}'


class Fake:
    """Stands in for ue_route.SshTransport: answer(category.method, args) -> text or (text, is_error); records every call."""

    def __init__(self, answer):
        self.answer, self.calls, self.is_error, self.closed = answer, [], False, False

    def call(self, category, method, args=None, timeout=60):
        head = "%s.%s" % (category, method)
        self.calls.append((head, args or {}))
        r = self.answer(head, args or {})
        text, self.is_error = r if isinstance(r, tuple) else (r, False)
        return text

    def close(self):
        self.closed = True

    def heads(self):
        return [h for h, _ in self.calls]


def run(module, argv, answer):
    """Run module.main(argv) against a Fake; returns (exit code, fake, printed text)."""
    fake, out = Fake(answer), io.StringIO()
    with mock.patch.object(ue_route, "SshTransport", lambda cmd: fake), mock.patch.object(ue_route, "ssh_command", lambda *a: ["fake"]), \
            contextlib.redirect_stdout(out):
        rc = module.main(argv)
    return rc, fake, out.getvalue()


def heights(z_cm, n=20):
    f = os.path.join(tempfile.mkdtemp(), "h.png")
    Image.fromarray(np.full((n, n), round((z_cm - Z0) * RPC), np.uint16)).save(f)
    return f


MAP = ["--z0", str(Z0), "--raw-per-cm", str(RPC), "--size-m", "152"]   # 20 px -> 800 cm per pixel


class Reply(unittest.TestCase):
    def test_failure_signals(self):
        self.assertTrue(ue_route.reply_failed('{"success": true}', is_error=True))
        self.assertTrue(ue_route.reply_failed("Error [level.save]: no such actor"))
        self.assertTrue(ue_route.reply_failed('{"success": false, "message": "x"}'))
        self.assertTrue(ue_route.reply_failed('{"success":false}'))
        self.assertTrue(ue_route.reply_failed('{"error": "x"}'))
        self.assertTrue(ue_route.reply_failed('note {"success": false} trailing text'))

    def test_success_and_plain_text_are_not_failures(self):
        self.assertFalse(ue_route.reply_failed('{"success": true, "note": "the old value had \\"success\\": false"}'))
        self.assertFalse(ue_route.reply_failed('{"editorConnected": true}'))
        self.assertFalse(ue_route.reply_failed("saved 3 packages"))
        self.assertFalse(ue_route.reply_failed(""))

    def test_ok_needs_an_explicit_success(self):
        self.assertTrue(ue_route.reply_ok('{"success": true}'))
        self.assertTrue(ue_route.reply_ok('{"success":true}'))
        self.assertFalse(ue_route.reply_ok('{"success": true}', is_error=True))
        self.assertFalse(ue_route.reply_ok("saved 3 packages"))
        self.assertFalse(ue_route.reply_ok('{"success": false}'))
        self.assertFalse(ue_route.reply_ok('{"error": "x"}'))


class RouteCall(unittest.TestCase):
    def test_a_failed_reply_is_a_non_zero_exit_and_the_output_is_unchanged(self):
        rc, fake, out = run(ue_route, ["call", "level.save {}", 'asset.list {"directory": "/Game"}'], lambda h, a: FAIL if h == "level.save" else OK)
        self.assertEqual(rc, 1)
        self.assertEqual(out, "[level.save] %s\n[asset.list] %s\n" % (FAIL, OK))
        self.assertEqual(fake.calls[1], ("asset.list", {"directory": "/Game"}))
        self.assertTrue(fake.closed)

    def test_the_mcp_error_flag_alone_fails_and_success_exits_zero(self):
        self.assertEqual(run(ue_route, ["call", "level.save {}"], lambda h, a: ("something went wrong", True))[0], 1)
        rc, _, out = run(ue_route, ["call", "level.save {}"], lambda h, a: OK)
        self.assertEqual((rc, out), (0, "[level.save] %s\n" % OK))


class RunPhases(unittest.TestCase):
    def calls(self):
        f = os.path.join(tempfile.mkdtemp(), "c.json")
        json.dump({"phases": [{"name": "p", "calls": [["a.one", {}], ["a.two", {}], ["a.three", {}]]}]}, open(f, "w"))
        return f

    def test_stops_at_a_failure_however_the_json_is_spaced(self):
        for bad in ('{"success":false}', '{\n  "success": false\n}', ("oops", True), '{"error": "boom"}', "Error [a.two] nope"):
            with mock.patch.object(ue_run_phases, "load1", lambda: 0.0):
                rc, fake, out = run(ue_run_phases, [self.calls()], lambda h, a, bad=bad: bad if h == "a.two" else OK)
            self.assertEqual(rc, 1, bad)
            self.assertEqual(fake.heads(), ["a.one", "a.two"], bad)
            self.assertIn("rerun with --start 1", out)

    def test_all_calls_run_when_they_succeed(self):
        with mock.patch.object(ue_run_phases, "load1", lambda: 0.0):
            rc, fake, _ = run(ue_run_phases, [self.calls()], lambda h, a: OK)
        self.assertEqual((rc, fake.heads()), (0, ["a.one", "a.two", "a.three"]))

    def height_calls(self, heights, **extra):
        import base64
        import struct
        f = os.path.join(tempfile.mkdtemp(), "c.json")
        args = dict({"actorLabel": "Land", "region": {"minX": 0, "minY": 0, "maxX": 1, "maxY": 1},
                     "heightsBase64": base64.b64encode(struct.pack("<4H", *heights)).decode()}, **extra)
        json.dump({"phases": [{"name": "heights", "calls": [["landscape.set_height_region", args]]}]}, open(f, "w"))
        return f

    def written(self, fake):
        import base64
        import struct
        args = [a for h, a in fake.calls if h == "landscape.set_height_region"][0]
        if "heights" in args:
            return list(args["heights"])
        data = base64.b64decode(args["heightsBase64"])
        return list(struct.unpack("<%dH" % (len(data) // 2), data))

    def water_answer(self, water):
        def answer(h, a):
            if h == "landscape.get_height_region":
                return json.dumps({"success": True, "heights": water})
            return OK
        return answer

    def test_a_base_write_under_a_carved_bed_subtracts_the_water_offset(self):
        # T-0049: a helper asks for visible heights; under a lake bed the Water layer adds -5000, so writing them straight into the
        # base would sink the bed by another 5000. The written base must be visible - offset; the neutral vertices stay as asked.
        with mock.patch.object(ue_run_phases, "load1", lambda: 0.0):
            rc, fake, out = run(ue_run_phases, [self.height_calls([20000, 20000, 15000, 15000])],
                                self.water_answer([32768, 32768, 27768, 27768]))
        self.assertEqual(rc, 0)
        self.assertEqual(fake.calls[0], ("landscape.get_height_region",
                                         {"actorLabel": "Land", "region": {"minX": 0, "minY": 0, "maxX": 1, "maxY": 1}, "editLayer": "Water"}))
        self.assertEqual(self.written(fake), [20000, 20000, 20000, 20000])
        self.assertIn("2 vertices under a Water-layer offset compensated", out)

    def test_neutral_water_writes_the_heights_unchanged(self):
        with mock.patch.object(ue_run_phases, "load1", lambda: 0.0):
            rc, fake, out = run(ue_run_phases, [self.height_calls([1, 2, 3, 4])], self.water_answer([32768] * 4))
        self.assertEqual((rc, self.written(fake)), (0, [1, 2, 3, 4]))
        self.assertNotIn("compensated", out)

    def test_opt_out_and_explicit_water_layer_writes_are_not_touched(self):
        with mock.patch.object(ue_run_phases, "load1", lambda: 0.0):
            rc, fake, _ = run(ue_run_phases, [self.height_calls([5, 5, 5, 5]), "--no-water-compensation"], self.water_answer([0] * 4))
        self.assertEqual((rc, fake.heads(), self.written(fake)), (0, ["landscape.set_height_region"], [5, 5, 5, 5]))
        with mock.patch.object(ue_run_phases, "load1", lambda: 0.0):
            rc, fake, _ = run(ue_run_phases, [self.height_calls([5, 5, 5, 5], editLayer="Water")], self.water_answer([0] * 4))
        self.assertEqual(fake.heads(), ["landscape.set_height_region"])

    def test_a_failed_water_read_stops_before_writing(self):
        with mock.patch.object(ue_run_phases, "load1", lambda: 0.0):
            rc, fake, out = run(ue_run_phases, [self.height_calls([1, 2, 3, 4])], lambda h, a: FAIL)
        self.assertEqual((rc, fake.heads()), (1, ["landscape.get_height_region"]))
        self.assertIn("rerun with --start 0", out)

    def test_plain_heights_lists_are_compensated_too(self):
        self.assertEqual(ue_run_phases.compensate({"heights": [100, 40000]}, [32768, 32868]), ({"heights": [100, 39900]}, 1))
        self.assertEqual(ue_run_phases.compensate({"heights": [10]}, [40000])[0]["heights"], [0])  # clamped, never negative


class Buried(unittest.TestCase):
    def answer(self, removal):
        def f(h, a):
            if h == "foliage.list_types":
                return json.dumps({"foliageTypes": [{"path": "/Game/F/FT_A.FT_A"}], "hasMore": False})
            if h == "foliage.get_instances":
                return json.dumps({"types": [{"instances": [{"index": 4, "location": {"x": 4000, "y": 4000, "z": 5000.0}}]}], "hasMore": False})
            return removal
        return f

    def test_a_failed_removal_is_reported_and_exits_non_zero(self):
        rc, fake, out = run(ue_foliage_buried, ["--heights", heights(6000.0), "--apply"] + MAP, self.answer(FAIL))
        self.assertEqual(rc, 1)
        self.assertIn("REMOVAL FAILED", out)
        self.assertIn("1 removal(s) FAILED", out)
        self.assertNotIn(", removed", out)

    def test_success_and_dry_run_are_unchanged(self):
        rc, fake, out = run(ue_foliage_buried, ["--heights", heights(6000.0), "--apply"] + MAP, self.answer(OK))
        self.assertEqual(rc, 0)
        self.assertIn("1 buried (> 80 cm below ground), removed", out)
        self.assertEqual(fake.calls[-1], ("foliage.remove_instances", {"foliageTypePath": "/Game/F/FT_A.FT_A", "instanceIndices": [4]}))
        rc, fake, out = run(ue_foliage_buried, ["--heights", heights(6000.0)] + MAP, self.answer(OK))
        self.assertEqual(rc, 0)
        self.assertNotIn("foliage.remove_instances", fake.heads())
        self.assertIn("dry run", out)

    def test_apply_writes_a_removed_instances_receipt_before_removing(self):
        with tempfile.TemporaryDirectory() as d:
            out_path = os.path.join(d, "removed.json")
            rc, fake, out = run(ue_foliage_buried, ["--heights", heights(6000.0), "--apply", "--out-removed", out_path] + MAP, self.answer(OK))
            self.assertEqual(rc, 0)
            receipt = json.load(open(out_path))
            self.assertEqual(receipt["removed"][0]["foliageTypePath"], "/Game/F/FT_A.FT_A")
            self.assertEqual(receipt["removed"][0]["instances"][0]["index"], 4)

    def test_a_failed_listing_is_a_failure_not_a_false_clean(self):
        def answer(h, a):
            if h == "foliage.list_types":
                return FAIL
            self.fail("get_instances should not be reached after list_types fails")
        rc, fake, out = run(ue_foliage_buried, ["--heights", heights(6000.0)] + MAP, answer)
        self.assertNotEqual(rc, 0)
        self.assertNotIn("0 buried", out)

    def test_zero_foliage_types_read_is_a_failure_not_an_empty_level(self):
        def answer(h, a):
            if h == "foliage.list_types":
                return json.dumps({"foliageTypes": [], "hasMore": False})
            self.fail("get_instances should not be reached with zero types")
        rc, fake, out = run(ue_foliage_buried, ["--heights", heights(6000.0)] + MAP, answer)
        self.assertNotEqual(rc, 0)

    def test_a_stale_landscape_sample_prints_a_warning_but_still_succeeds(self):
        def answer(h, a):
            if h == "landscape.get_height_region":
                return json.dumps({"heights": [99999]})     # does not match the heights png at any sample point
            return self.answer(OK)(h, a)
        rc, fake, out = run(ue_foliage_buried, ["--heights", heights(6000.0), "--landscape", "L"] + MAP, answer)
        self.assertEqual(rc, 0)
        self.assertIn("WARNING: --heights looks stale", out)

    def test_no_landscape_given_skips_the_freshness_check(self):
        rc, fake, out = run(ue_foliage_buried, ["--heights", heights(6000.0)] + MAP, self.answer(OK))
        self.assertNotIn("landscape.get_height_region", fake.heads())

    def test_a_failed_get_instances_is_a_failure_not_a_false_clean(self):
        def answer(h, a):
            if h == "foliage.list_types":
                return json.dumps({"foliageTypes": [{"path": "/Game/F/FT_A.FT_A"}], "hasMore": False})
            if h == "foliage.get_instances":
                return FAIL
            self.fail("unexpected call %s" % h)
        rc, fake, out = run(ue_foliage_buried, ["--heights", heights(6000.0)] + MAP, answer)
        self.assertNotEqual(rc, 0)
        self.assertNotIn("0 buried", out)


class PlaceAssets(unittest.TestCase):
    def manifest(self):
        f = os.path.join(tempfile.mkdtemp(), "m.json")
        json.dump([{"label": "Tower", "asset": "/Game/SM_Tower.SM_Tower", "x": 4000, "y": 4000, "clear_foliage_cm": 500}], open(f, "w"))
        return f

    def answer(self, failing=None):
        def f(h, a):
            if h == failing:
                return FAIL
            if h == "level.get_actor_details":
                return FAIL   # no such actor yet, so it is placed
            if h == "level.get_actor_bounds":
                return json.dumps({"success": True, "origin": {"x": 0, "y": 0, "z": 6200.0}, "extent": {"x": 50, "y": 50, "z": 100}})
            if h == "foliage.get_instances":
                return json.dumps({"types": [{"foliageTypePath": "/Game/F/FT_A.FT_A", "instances": [{"index": 2}]}]})
            return OK
        return f

    def test_any_failed_step_stops_before_the_save(self):
        for step in ("level.place_actor", "level.move_actor", "foliage.remove_instances"):
            rc, fake, out = run(ue_place_assets, [self.manifest(), "--heights", heights(6000.0)] + MAP, self.answer(step))
            self.assertEqual(rc, 1, step)
            self.assertNotIn("level.save", fake.heads(), step)
            self.assertNotIn("asset.save_all_dirty", fake.heads(), step)
            self.assertIn("NOT saving", out)

    def test_force_save_saves_but_still_exits_non_zero_and_a_failed_save_fails(self):
        rc, fake, _ = run(ue_place_assets, [self.manifest(), "--heights", heights(6000.0), "--force-save"] + MAP, self.answer("level.move_actor"))
        self.assertEqual(rc, 1)
        self.assertIn("level.save", fake.heads())
        rc, fake, out = run(ue_place_assets, [self.manifest(), "--heights", heights(6000.0)] + MAP, self.answer("level.save"))
        self.assertEqual(rc, 1)
        self.assertNotIn("saved\n", out)

    def test_success_places_clears_and_saves(self):
        rc, fake, out = run(ue_place_assets, [self.manifest(), "--heights", heights(6000.0)] + MAP, self.answer())
        self.assertEqual(rc, 0)
        self.assertEqual(fake.heads(), ["level.get_actor_details", "level.place_actor", "level.get_actor_bounds", "level.move_actor",
                                        "foliage.get_instances", "foliage.remove_instances", "level.save", "asset.save_all_dirty"])
        self.assertAlmostEqual(fake.calls[3][1]["location"]["z"], 6000.0 + 100 + (6000.0 - 20 - 6100.0), delta=1.0)
        self.assertIn("saved", out)


class VillageBuild(unittest.TestCase):
    def argv(self, *extra):
        f = os.path.join(tempfile.mkdtemp(), "layout.json")
        json.dump({"center": [4000, 4000], "level_z": 7000, "instances": [{"mesh": "Well", "x": 4000, "y": 4000, "yaw": 0}],
                   "existing": {"House_1": {"x": 5000, "y": 5000, "yaw": 0}}}, open(f, "w"))
        return [f, "--old-heights", heights(6000.0), "--new-heights", heights(7000.0), "--apply"] + MAP + list(extra)

    def answer(self, failing=None):
        def f(h, a):
            if h == failing:
                return FAIL
            if h == "foliage.list_types":
                return json.dumps({"foliageTypes": [{"path": "/Game/F/FT_A.FT_A"}], "hasMore": False})
            if h == "level.get_actor_details":
                return json.dumps({"success": True, "location": {"x": 1000, "y": 1000, "z": 6050.0}})
            return OK
        return f

    def test_any_failed_step_stops_before_the_save(self):
        for step in ("foliage.remove_instances", "level.move_actor", "foliage.create_type", "foliage.add_instances"):
            rc, fake, out = run(ue_village_build, self.argv(), self.answer(step))
            self.assertEqual(rc, 1, step)
            self.assertNotIn("level.save", fake.heads(), step)
            self.assertIn("NOT saving", out)

    def test_force_save_saves_and_still_exits_non_zero(self):
        rc, fake, _ = run(ue_village_build, self.argv("--force-save"), self.answer("level.move_actor"))
        self.assertEqual((rc, fake.heads()[-1]), (1, "level.save"))

    def test_success_saves_once_and_types_go_under_the_default_type_dir(self):
        rc, fake, _ = run(ue_village_build, self.argv(), self.answer())
        self.assertEqual(rc, 0)
        self.assertEqual(fake.heads().count("level.save"), 1)
        create = [a for h, a in fake.calls if h == "foliage.create_type"][0]
        self.assertEqual(create["packagePath"], ue_village_build.TYPE_DIR)
        self.assertEqual(run(ue_village_build, self.argv(), self.answer("level.save"))[0], 1)


class CreekFoliage(unittest.TestCase):
    """Two types, each with one instance hanging 150 cm over the lake shore: both are planned as remove + re-add."""

    def argv(self, *extra):
        return ["--lake", "8000,8000,7050,20", "--new-heights", heights(7000.0)] + MAP + list(extra)

    def answer(self, failing=None):
        def f(h, a):
            if h == failing:
                return FAIL
            if h == "foliage.get_instances":
                inst = {"index": 0, "location": {"x": 8000, "y": 8000, "z": 7150.0}, "rotation": {"pitch": 0, "yaw": 0, "roll": 0}, "scale": {"x": 1, "y": 1, "z": 1}}
                return json.dumps({"types": [{"foliageTypePath": "/Game/F/FT_A.FT_A", "instances": [inst]},
                                             {"foliageTypePath": "/Game/F/FT_B.FT_B", "instances": [inst]}], "hasMore": False})
            return OK
        return f

    def test_a_failed_removal_stops_without_any_re_add(self):
        rc, fake, out = run(ue_creek_foliage, self.argv("--apply"), self.answer("foliage.remove_instances"))
        self.assertEqual(rc, 1)
        self.assertEqual(fake.heads().count("foliage.remove_instances"), 1)
        self.assertNotIn("foliage.add_instances", fake.heads())
        self.assertIn("FAILED", out)

    def test_a_failed_re_add_exits_non_zero(self):
        self.assertEqual(run(ue_creek_foliage, self.argv("--apply"), self.answer("foliage.add_instances"))[0], 1)

    def test_success_removes_then_re_adds_each_type_and_the_dry_run_changes_nothing(self):
        rc, fake, _ = run(ue_creek_foliage, self.argv("--apply"), self.answer())
        self.assertEqual(rc, 0)
        changes = [h for h in fake.heads() if h != "foliage.get_instances"]
        self.assertEqual(changes, ["foliage.remove_instances", "foliage.add_instances"] * 2)
        added = [a for h, a in fake.calls if h == "foliage.add_instances"][0]["transforms"][0]
        self.assertAlmostEqual(added["location"]["z"], 7000.0, delta=1.0)
        rc, fake, out = run(ue_creek_foliage, self.argv(), self.answer())
        self.assertEqual(rc, 0)
        self.assertEqual(set(fake.heads()), {"foliage.get_instances"})
        self.assertIn("remove 2 (of which re-added 2)", out)


if __name__ == "__main__":
    unittest.main()
