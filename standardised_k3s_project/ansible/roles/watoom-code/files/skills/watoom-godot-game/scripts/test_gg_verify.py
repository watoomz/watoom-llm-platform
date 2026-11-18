import json, os, sys, tempfile, unittest
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gg_godot, gg_log, gg_verify


def fake_run_factory(arr, code=0, fatal_text="", engine_method="forward_plus", size=None):
    def run(project, op, args, **kw):
        os.makedirs(args["out_dir"], exist_ok=True)
        files = []
        for v in args["views"] or [{"name": "default"}]:
            p = os.path.join(args["out_dir"], v["name"] + ".png")
            Image.fromarray(arr).save(p); files.append({"name": v["name"], "path": p})
        rep = gg_log.classify(fatal_text + "@@GG_DONE@@\n")
        res = {"ok": code in (0,), "engine": {"rendering_method": engine_method, "adapter": "fake"}, "data": {"files": files}}
        return gg_godot.Result(code, "fake why", res, args["out_dir"], rep, [])
    return run


def noisy(w=64, h=48):
    return np.random.RandomState(3).randint(40, 200, (h, w, 3), np.uint8)


class T(unittest.TestCase):
    def test_shot_pass_and_report(self):
        with tempfile.TemporaryDirectory() as d:
            code, rep = gg_verify.shot("P", require_selftest=False, builder="res://b.gd", out=d, views=[{"name": "hero"}], size=(64, 48), run=fake_run_factory(noisy()),
                                       targets={"targets": {"luma_p50": [0.2, 0.8]}})
            self.assertEqual(code, 0); self.assertEqual(rep["views"][0]["name"], "hero")
            self.assertTrue(os.path.exists(os.path.join(d, "verify_report.json")))

    def test_shot_target_failure_is_1_with_hint(self):
        with tempfile.TemporaryDirectory() as d:
            code, rep = gg_verify.shot("P", require_selftest=False, builder="res://b.gd", out=d, views=[{"name": "hero"}], size=(64, 48), run=fake_run_factory(noisy()),
                                       targets={"targets": {"luma_p50": [0.9, None]}, "fix_hints": {"luma_p50": {"low": "raise exposure"}}})
            self.assertEqual(code, 1); self.assertEqual(rep["views"][0]["failures"][0]["hint"], "raise exposure")

    def test_size_mismatch_names_both(self):
        with tempfile.TemporaryDirectory() as d:
            code, rep = gg_verify.shot("P", require_selftest=False, builder="res://b.gd", out=d, views=[{"name": "v"}], size=(128, 96), run=fake_run_factory(noisy()))
            self.assertEqual(code, 1)
            self.assertIn("64x48", json.dumps(rep["views"][0]["failures"])); self.assertIn("128x96", json.dumps(rep["views"][0]["failures"]))

    def test_engine_failure_passes_through_without_images(self):
        with tempfile.TemporaryDirectory() as d:
            code, rep = gg_verify.shot("P", require_selftest=False, builder="res://b.gd", out=d, views=[{"name": "v"}], size=(64, 48),
                                       run=fake_run_factory(noisy(), code=3, fatal_text="SHADER ERROR: x\n"))
            self.assertEqual(code, 3); self.assertEqual(rep["views"], []); self.assertEqual(rep["log"]["fatal"][0]["cls"], "shader_error")

    def test_renderer_mismatch_is_2(self):
        with tempfile.TemporaryDirectory() as d:
            code, rep = gg_verify.shot("P", require_selftest=False, builder="res://b.gd", out=d, views=[{"name": "v"}], size=(64, 48), renderer="forward_plus",
                                       run=fake_run_factory(noisy(), engine_method="gl_compatibility"))
            self.assertEqual(code, 2); self.assertIn("gl_compatibility", rep["why"])

    def test_needs_scene_or_builder(self):
        with self.assertRaises(gg_godot.Refused): gg_verify.shot("P", require_selftest=False, out=tempfile.mkdtemp(), run=fake_run_factory(noisy()))

    def test_selftest_detects_blind_loop(self):
        """A launcher that never reports fatal lines must make the selftest FAIL with BLIND."""
        def run(project, op, args, **kw):
            if op == "hang":
                return gg_godot.Result(0, "ok", {}, "", gg_log.classify(""), [])
            os.makedirs(args["out_dir"], exist_ok=True)
            p = os.path.join(args["out_dir"], "main.png")
            Image.fromarray(noisy(1280 // 20, 720 // 20)).save(p)
            return gg_godot.Result(0, "ok", {"ok": True, "engine": {"rendering_method": "forward_plus", "adapter": "x"}, "data": {"files": [{"name": "main", "path": p}]}},
                                   "", gg_log.classify("@@GG_DONE@@"), [])
        with tempfile.TemporaryDirectory() as w, tempfile.TemporaryDirectory() as r:
            code, rep = gg_verify.selftest(work=w, run=run, report_path=os.path.join(r, "r.json"))
            self.assertEqual(code, 1)
            bad = [s for s in rep["steps"] if not s["ok"]]
            self.assertTrue(any("BLIND" in s["detail"] for s in bad))
            self.assertTrue(any(s["n"] == 9 for s in bad))

    def test_bad_views_refused_before_launch(self):
        calls = []
        def run(*a, **k): calls.append(1)
        for bad, word in (([{"name": "a", "kind": "ortho"}], "kind"), ([{"name": "a", "pos": [0, 0, 0]}], "unknown key"),
                          ([{"name": "a"}, {"name": "a"}], "duplicate"), ([{"kind": "3d"}], "needs a name"),
                          ([{"name": "a", "position": [1, 2]}], "[x, y, z]")):
            with self.assertRaises(gg_godot.Refused) as c: gg_verify.shot("P", builder="res://b.gd", out=tempfile.mkdtemp(), views=bad, require_selftest=False, run=run)
            self.assertIn(word, str(c.exception))
        self.assertEqual(calls, [])

    def test_bad_targets_refused(self):
        for bad in ({"luma_p50": 0.4}, {"luma_p50": [0.9, 0.1]}, {"luma_p50": {"min": 0.1}}):
            with self.assertRaises(gg_godot.Refused): gg_verify.shot("P", builder="res://b.gd", out=tempfile.mkdtemp(), views=[{"name": "v"}], targets=bad, require_selftest=False, run=fake_run_factory(noisy()))

    def test_stale_png_removed_and_failed_run_marks_invalid(self):
        with tempfile.TemporaryDirectory() as d:
            Image.fromarray(noisy()).save(os.path.join(d, "v.png")); open(os.path.join(d, "verify_report.json"), "w").write("{}")
            code, rep = gg_verify.shot("P", builder="res://b.gd", out=d, views=[{"name": "v"}], size=(64, 48), require_selftest=False,
                                       run=fake_run_factory(noisy(), code=3, fatal_text="SHADER ERROR: x\n"))
            self.assertEqual(code, 3)
            self.assertFalse(os.path.exists(os.path.join(d, "v.png")))
            self.assertTrue(os.path.exists(os.path.join(d, "v.INVALID.png")))

    def test_selftest_gate(self):
        with tempfile.TemporaryDirectory() as sd:
            self.assertIn("no selftest report", gg_verify.selftest_gate("forward_plus", godot="/g", state_dir=sd))
            json.dump({"pass": False, "godot": "/g"}, open(os.path.join(sd, "selftest_forward_plus.json"), "w"))
            self.assertIn("FAILED", gg_verify.selftest_gate("forward_plus", godot="/g", state_dir=sd))
            json.dump({"pass": True, "godot": "/other"}, open(os.path.join(sd, "selftest_forward_plus.json"), "w"))
            m = gg_verify.selftest_gate("forward_plus", godot="/g", state_dir=sd)
            self.assertIn("/other", m); self.assertIn("/g", m)
            json.dump({"pass": True, "godot": "/g"}, open(os.path.join(sd, "selftest_forward_plus.json"), "w"))
            self.assertIsNone(gg_verify.selftest_gate("forward_plus", godot="/g", state_dir=sd))
            with self.assertRaises(gg_godot.Refused):
                gg_verify.shot("P", builder="res://b.gd", out=sd, views=[{"name": "v"}], run=fake_run_factory(noisy()), state_dir=os.path.join(sd, "none"))

    def test_compare_size_mismatch_and_same_file(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = os.path.join(d, "a.png"), os.path.join(d, "b.png")
            Image.fromarray(noisy(64, 48)).save(a); Image.fromarray(noisy(32, 32)).save(b)
            self.assertEqual(gg_verify.main(["compare", a, b, "--expect", "different"]), 2)
            self.assertEqual(gg_verify.main(["compare", a, a, "--expect", "same"]), 2)

    def test_cli_compare(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = os.path.join(d, "a.png"), os.path.join(d, "b.png")
            Image.fromarray(noisy()).save(a); Image.fromarray(np.clip(noisy().astype(int) + 50, 0, 255).astype(np.uint8)).save(b)
            self.assertEqual(gg_verify.main(["compare", a, b, "--expect", "brighter"]), 0)
            self.assertEqual(gg_verify.main(["compare", a, b, "--expect", "darker"]), 1)
            self.assertEqual(gg_verify.main(["compare", a, b, "--expect", "bluer"]), 2)


if __name__ == "__main__":
    unittest.main()
