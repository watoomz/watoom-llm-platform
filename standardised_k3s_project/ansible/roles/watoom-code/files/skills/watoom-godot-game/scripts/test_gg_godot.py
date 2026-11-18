import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gg_godot, gg_log


def rep(text):
    return gg_log.classify(text)


class Fake:
    """runner(argv, timeout) -> (rc, output, timed_out); optionally writes result.json like the engine."""
    def __init__(self, output="@@GG_BEGIN@@ x\n@@GG_DONE@@ ok=true\n", ok=True, write=True, timed_out=False, job_override=None, outputs=None):
        self.output, self.ok, self.write, self.timed_out, self.job_override, self.calls, self.outputs = output, ok, write, timed_out, job_override, [], outputs

    def __call__(self, argv, timeout, cwd=None):
        self.calls.append(argv)
        if "--import" in argv:
            return 0, "", False
        spec = [a for a in argv if a.startswith("--spec=")][0][7:]
        res = [a for a in argv if a.startswith("--result=")][0][9:]
        job = json.load(open(spec))["job"]
        if self.write:
            json.dump({"job": self.job_override or job, "ok": self.ok, "error": None if self.ok else "boom", "data": {}, "engine": {"rendering_method": "forward_plus"}}, open(res, "w"))
        out = self.outputs.pop(0) if self.outputs else self.output
        return 0, out, self.timed_out


class T(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        open(os.path.join(self.d, "project.godot"), "w").write("config_version=5\n")
        gg_godot.install_runtime(self.d)
        os.makedirs(os.path.join(self.d, ".godot"))

    def run_(self, fake, **kw):
        return gg_godot.run(self.d, "noop", {}, runner=fake, godot="/bin/godot", sleep=lambda s: None, **kw)

    def test_argv_render_vs_headless(self):
        a = gg_godot.build_argv("g", "P", "J", render=True, renderer="forward_plus", size=(640, 360))
        self.assertEqual(a[0], "xvfb-run"); self.assertIn("Dummy", a); self.assertIn("vulkan", a); self.assertIn("640x360", a)
        self.assertEqual(a[a.index("--") + 1], "--spec=J/spec.json")
        b = gg_godot.build_argv("g", "P", "J", render=False, renderer="x", size=(1, 1))
        self.assertEqual(b[0], "g"); self.assertIn("--headless", b); self.assertNotIn("xvfb-run", b)
        self.assertIn("opengl3", gg_godot.build_argv("g", "P", "J", render=True, renderer="gl_compatibility", size=(1, 1)))
        with self.assertRaises(gg_godot.Refused): gg_godot.build_argv("g", "P", "J", render=True, renderer="dx12", size=(1, 1))

    def test_ok(self):
        self.assertEqual(self.run_(Fake()).code, 0)

    def test_exit0_with_engine_error_is_3(self):
        r = self.run_(Fake(output="@@GG_BEGIN@@ x\nERROR: Node not inside tree.\n@@GG_DONE@@ ok=true\n"))
        self.assertEqual(r.code, 3); self.assertIn("Node not inside tree", r.why)

    def test_timeout_is_4(self):
        self.assertEqual(self.run_(Fake(timed_out=True)).code, 4)

    def test_no_result_or_no_sentinel_is_4(self):
        self.assertEqual(self.run_(Fake(write=False)).code, 4)
        self.assertEqual(self.run_(Fake(output="@@GG_BEGIN@@ x\n")).code, 4)

    def test_wrong_job_is_4(self):
        r = self.run_(Fake(job_override="other"))
        self.assertEqual(r.code, 4); self.assertIn("other", r.why)

    def test_runner_failure_is_5(self):
        self.assertEqual(self.run_(Fake(ok=False)).code, 5)

    def test_precedence(self):
        gpu = "ERROR: x VK_ERROR_OUT_OF_DEVICE_MEMORY\nERROR: plain\n@@GG_DONE@@ ok=false\n"
        self.assertEqual(self.run_(Fake(output=gpu, ok=False, outputs=[gpu, gpu]), retry_gpu=False).code, 4)
        self.assertEqual(self.run_(Fake(output="ERROR: plain\n@@GG_DONE@@ ok=false\n", ok=False)).code, 3)  # 3 beats 5

    def test_gpu_retry_once(self):
        f = Fake(outputs=["VK_ERROR_OUT_OF_DEVICE_MEMORY\n", "@@GG_BEGIN@@ x\n@@GG_DONE@@ ok=true\n"])
        r = self.run_(f)
        self.assertEqual(r.code, 0); self.assertEqual(len([c for c in f.calls if "--import" not in c]), 2)

    def test_refuses_non_project_and_missing_runtime(self):
        with tempfile.TemporaryDirectory() as e:
            with self.assertRaises(gg_godot.Refused): gg_godot.run(e, "noop", runner=Fake(), godot="/bin/godot")
            open(os.path.join(e, "project.godot"), "w").write("x")
            with self.assertRaises(gg_godot.Refused) as c: gg_godot.run(e, "noop", runner=Fake(), godot="/bin/godot")
            self.assertIn("runtime", str(c.exception))

    def test_install_runtime_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as e:
            files = gg_godot.install_runtime(e, dry_run=True)
            self.assertTrue(files); self.assertEqual(os.listdir(e), [])

    def test_import_failure_stops(self):
        os.rmdir(os.path.join(self.d, ".godot"))
        class F(Fake):
            def __call__(s, argv, timeout, cwd=None):
                return (0, "ERROR: bad import\n", False) if "--import" in argv else super().__call__(argv, timeout)
        r = self.run_(F())
        self.assertEqual(r.code, 3); self.assertIn("import", r.why)


if __name__ == "__main__":
    unittest.main()
