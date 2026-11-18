import argparse, json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gg_godot, gg_project, gg_verify


def args(project, **kw):
    d = dict(project=project, name="demo", dimension="3d", view=None, style="low-poly", size_m=None, cell_m=None, seed=1, dry_run=False, adopt=False)
    d.update(kw)
    return argparse.Namespace(**d)


def snapshot(d):
    out = {}
    for b, _, fs in os.walk(d):
        for f in fs:
            out[os.path.join(b, f)] = os.path.getsize(os.path.join(b, f))
    return out


class FakeRun:
    def __init__(self, mismatch=None):
        self.ops, self.mismatch = [], mismatch or []

    def __call__(self, project, op, args=None, **kw):
        self.ops.append(op)
        import gg_log
        data = {"mismatches": self.mismatch} if op == "project_dump" else {"nodes": 20}
        return gg_godot.Result(0, "ok", {"ok": True, "data": data, "engine": {"rendering_method": "gl_compatibility"}}, project, gg_log.classify("@@GG_DONE@@"), [])


class T(unittest.TestCase):
    def gate(self, sd, renderer="gl_compatibility"):
        json.dump({"pass": True, "godot": gg_godot.find_godot()}, open(os.path.join(sd, "selftest_%s.json" % renderer), "w"))

    def test_init_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            before = snapshot(d)
            self.assertEqual(gg_project.init(args(os.path.join(d, "g"), dry_run=True), run=FakeRun(), state_dir=d), 0)
            self.assertEqual(snapshot(d), before); self.assertFalse(os.path.exists(os.path.join(d, "g")))

    def test_init_refusals(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "stuff.txt"), "w").write("x")
            with self.assertRaises(gg_godot.Refused) as c: gg_project.init(args(d), run=FakeRun(), state_dir=d)
            self.assertIn("not empty", str(c.exception))
            os.remove(os.path.join(d, "stuff.txt")); open(os.path.join(d, "project.godot"), "w").write("x")
            with self.assertRaises(gg_godot.Refused) as c: gg_project.init(args(d), run=FakeRun(), state_dir=d)
            self.assertIn("--adopt", str(c.exception))
            with self.assertRaises(gg_godot.Refused) as c: gg_project.init(args(os.path.join(d, "new")), run=FakeRun(), state_dir=d)
            self.assertIn("selftest", str(c.exception))
            with self.assertRaises(gg_godot.Refused) as c: gg_project.init(args(os.path.join(d, "n2"), dimension="2d"), run=FakeRun(), state_dir=d)
            self.assertIn("3d", str(c.exception)); self.assertIn("2d", str(c.exception))
            with self.assertRaises(gg_godot.Refused): gg_project.init(args(os.path.join(d, "n3"), name="Bad Name"), run=FakeRun(), state_dir=d)

    def test_existing_gg_project_refused(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "gg_project.json"), "w").write("{}")
            with self.assertRaises(gg_godot.Refused) as c: gg_project.check_dir(d, False)
            self.assertIn("already", str(c.exception))

    def test_apply_style_op_order_and_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            prof, _ = gg_project.build_profile(args(d))
            json.dump(prof, open(os.path.join(d, "gg_project.json"), "w"))
            f = FakeRun()
            self.assertEqual(gg_project.apply_style(d, run=f), 0)
            self.assertEqual(f.ops, ["project_apply", "project_dump", "build_boot", "project_apply", "project_dump"])  # main scene is set only after the scene exists
            f2 = FakeRun(mismatch=[{"key": "display/window/size/viewport_width", "want": "1280", "got": "1024"}])
            self.assertEqual(gg_project.apply_style(d, run=f2), 1)
            self.assertNotIn("build_boot", f2.ops)  # stop before building when the settings did not stick

    def test_apply_dry_run_runs_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            prof, _ = gg_project.build_profile(args(d)); json.dump(prof, open(os.path.join(d, "gg_project.json"), "w"))
            f = FakeRun(); self.assertEqual(gg_project.apply_style(d, dry_run=True, run=f), 0); self.assertEqual(f.ops, [])

    def test_profile_validation_messages(self):
        p, _ = gg_project.build_profile(args("/x"))
        self.assertEqual(gg_project.profile_errors(p), [])
        for mut, frag in ((lambda q: q["world"].update(size_m=[8, 400]), "size_m"), (lambda q: q.update(view="fly"), "view"),
                          (lambda q: q["world"].update(sea_level_m=500.0), "sea_level_m"), (lambda q: q["world"].update(height_range_m=[5.0, 1.0]), "height_range_m"),
                          (lambda q: q.update(godot_version="3.5"), "godot_version"), (lambda q: q.update(extra=1), "unknown key"),
                          (lambda q: q["capture"]["views"].append({"name": "hero"}), "duplicate")):
            q = json.loads(json.dumps(p)); mut(q)
            self.assertIn(frag, "\n".join(gg_project.profile_errors(q)))

    def test_2d_view_rule(self):
        p, _ = gg_project.build_profile(args("/x", dimension="2d", style="pixel-art"))
        self.assertEqual(p["view"], "top_down"); self.assertEqual(p["capture"]["views"][0]["kind"], "2d")
        p["view"] = "first_person"
        self.assertTrue(any("2d project" in e for e in gg_project.profile_errors(p)))

    def test_gradient_not_in_presets(self):
        import gg_style
        for n in gg_style.list_presets():
            self.assertNotEqual(gg_style.load_preset(n)["lighting"]["sky"]["kind"], "gradient")

    def test_runtime_drift_detected(self):
        with tempfile.TemporaryDirectory() as d:
            gg_godot.install_runtime(d)
            self.assertEqual(gg_godot.runtime_drift(d), [])
            with open(os.path.join(d, "addons", "gg", "gg_runner.gd"), "a") as f: f.write("# hand edit\n")
            m = gg_godot.runtime_drift(d)
            self.assertTrue(m and "gg_runner.gd" in m[0])
            open(os.path.join(d, "project.godot"), "w").write("x")
            with self.assertRaises(gg_godot.Refused) as c: gg_godot.run(d, "noop", godot="/bin/true")
            self.assertIn("sync-runtime", str(c.exception))

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(gg_project.main(["validate", "--project", d]), 2)
            self.assertEqual(gg_project.main(["show", "--project", d]), 2)


if __name__ == "__main__":
    unittest.main()
