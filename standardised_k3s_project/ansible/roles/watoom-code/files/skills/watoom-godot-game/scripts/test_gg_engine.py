"""Real-engine test: the selftest end to end. Skipped when godot or xvfb-run is missing (or GG_SKIP_ENGINE=1)."""
import os, shutil, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gg_godot, gg_verify

OK = gg_godot.find_godot() and shutil.which("xvfb-run") and not os.environ.get("GG_SKIP_ENGINE")


@unittest.skipUnless(OK, "godot/xvfb-run not available")
class T(unittest.TestCase):
    def test_selftest_each_renderer(self):
        for r in ("gl_compatibility", "forward_plus"):
            with tempfile.TemporaryDirectory() as rp:
                code, rep = gg_verify.selftest(renderer=r, report_path=os.path.join(rp, "r.json"))
                self.assertEqual(code, 0, [s for s in rep["steps"] if not s["ok"]])


@unittest.skipUnless(OK, "godot/xvfb-run not available")
class StageB(unittest.TestCase):
    """init a real low-poly project, probe passes, a different preset's targets fail, validate catches a broken profile."""
    def test_init_probe_flip_validate(self):
        import argparse, json, gg_project, gg_style
        if gg_verify.selftest_gate("gl_compatibility"):
            self.skipTest("run gg_verify.py selftest first")
        with tempfile.TemporaryDirectory() as d:
            a = argparse.Namespace(project=os.path.join(d, "g"), name="g", dimension="3d", view=None, style="low-poly", size_m=[256.0, 256.0], cell_m=None, seed=1, dry_run=False, adopt=False)
            self.assertEqual(gg_project.init(a), 0)
            self.assertEqual(gg_style.main(["probe", "--project", a.project, "--out", os.path.join(d, "o1")]), 0)
            self.assertEqual(gg_style.main(["probe", "--project", a.project, "--out", os.path.join(d, "o2"), "--against", "realistic"]), 1)
            self.assertEqual(gg_project.main(["validate", "--project", a.project]), 0)
            pj = os.path.join(a.project, "gg_project.json"); p = json.load(open(pj)); p["view"] = "fly"; json.dump(p, open(pj, "w"))
            self.assertEqual(gg_project.main(["validate", "--project", a.project]), 2)


if __name__ == "__main__":
    unittest.main()
