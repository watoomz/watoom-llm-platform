import json, os, pathlib, stat, sys, tempfile, threading, time, unittest, urllib.error, urllib.request

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import moss_image_service as svc  # noqa: E402

PRESETS = HERE.parent / "presets" / "film-camera-looks.json"


class Fixture:
    def __init__(self, gate="none", smi_free=None):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        self.log = root / "requests.jsonl"
        os.environ["FAKE_MOSS_LOG"] = str(self.log)
        if smi_free is not None:
            smi = root / "fake-smi"
            smi.write_text("#!/bin/sh\necho %d\n" % smi_free)
            smi.chmod(smi.stat().st_mode | stat.S_IXUSR)
            os.environ["MOSS_NVIDIA_SMI"] = str(smi)
        args = svc.argparse.Namespace(
            engine_dir=str(root), model_folder="/m/folder", dit="/m/dit.safetensors", text_encoder="/m/te.safetensors", vae="/m/vae.safetensors",
            tier="high", mode="min_memory", out_dir=str(root / "out"), presets=str(PRESETS), gpu_gate=gate, min_free_vram_mib=6144,
            idle_release=0, sidecar_cmd="%s %s" % (sys.executable, HERE / "fake_moss_server.py"))
        self.manager = svc.build(args)
        self.httpd = svc.ThreadingHTTPServer(("127.0.0.1", 0), svc.make_handler(self.manager))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = "http://127.0.0.1:%d" % self.httpd.server_address[1]

    def close(self):
        self.httpd.shutdown()
        self.manager.shutdown()
        os.environ.pop("MOSS_NVIDIA_SMI", None)
        self.tmp.cleanup()

    def call(self, path, body=None, headers=None, method=None):
        data = None if body is None else json.dumps(body).encode()
        h = {"Content-Type": "application/json"} if body is not None else {}
        h.update(headers or {})
        req = urllib.request.Request(self.base + path, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if r.headers["Content-Type"].startswith("application/json") else raw)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def wait(self, jid, timeout=20):
        end = time.time() + timeout
        while time.time() < end:
            _, j = self.call("/api/jobs/" + jid)
            if j["status"] not in ("queued", "running"):
                return j
            time.sleep(0.1)
        raise AssertionError("job did not finish")

    def requests(self):
        return [json.loads(l) for l in self.log.read_text().splitlines()] if self.log.exists() else []


class PresetTests(unittest.TestCase):
    def test_presets_file_is_valid_and_complete(self):
        doc = svc.load_presets(PRESETS)
        self.assertEqual(52, len(doc["presets"]))
        cats = {}
        for p in doc["presets"]:
            cats[p["category"]] = cats.get(p["category"], 0) + 1
        self.assertEqual({"Film stocks": 18, "Cameras": 16, "General looks": 11, "Broken film": 7}, cats)

    def test_compose_says_the_look_twice_and_adds_negatives(self):
        preset = {"prompt_look": "Black and white 35mm film photo.", "negative_extra": "color, colorful"}
        prompt, neg = svc.compose("  a woman at a window ", preset, "blur")
        self.assertEqual("Black and white 35mm film photo. a woman at a window Black and white 35mm film photo.", prompt)
        self.assertEqual(svc.USUAL_NEGATIVE + ", color, colorful, blur", neg)
        self.assertEqual(("a cat", svc.USUAL_NEGATIVE), svc.compose("a cat", None))


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()

    def tearDown(self):
        self.f.close()

    def test_page_and_presets_served(self):
        st, page = self.f.call("/")
        self.assertEqual(200, st)
        self.assertIn(b"MOSS Image Studio", page)
        st, doc = self.f.call("/api/presets")
        self.assertEqual(52, len(doc["presets"]))

    def test_generate_with_preset_end_to_end(self):
        st, job = self.f.call("/api/generate", {"scene": "a woman by a shutter", "preset_id": "kodak-tri-x-400", "seed": 7})
        self.assertEqual(202, st)
        done = self.f.wait(job["id"])
        self.assertEqual("done", done["status"], done)
        self.assertEqual(["fake warning"], done["warnings"])
        st, png = self.f.call("/api/images/" + done["image"])
        self.assertEqual(200, st)
        self.assertTrue(png.startswith(b"\x89PNG"))
        gen = [r for r in self.f.requests() if r["method"] == "generate"][0]["params"]
        look = [p for p in svc.load_presets(PRESETS)["presets"] if p["id"] == "kodak-tri-x-400"][0]
        self.assertTrue(gen["prompt"].startswith(look["prompt_look"]) and gen["prompt"].endswith(look["prompt_look"]))
        self.assertIn(look["negative_extra"], gen["negative_prompt"])
        self.assertEqual((1216, 832, 25, 2.5, "er_sde", 7), (gen["width"], gen["height"], gen["steps"], gen["cfg"], gen["sampler"], gen["seed"]))
        load = [r for r in self.f.requests() if r["method"] == "load"][0]["params"]
        self.assertEqual("high", load["tier"])
        self.assertEqual("/m/dit.safetensors", load["dit_file"])
        _, gallery = self.f.call("/api/gallery")
        self.assertEqual([done["image"]], [i["image"] for i in gallery["items"]])
        _, one = self.f.call("/api/gallery?limit=1")
        self.assertEqual(1, len(one["items"]))

    def test_metrics_count_completed_generations(self):
        st, raw = self.f.call("/metrics")
        self.assertEqual(200, st)
        self.assertIn(b"watoom_moss_up 1", raw)
        _, job = self.f.call("/api/generate", {"scene": "a lamp", "preset_id": "kodak-tri-x-400", "seed": 3})
        self.assertEqual("done", self.f.wait(job["id"])["status"])
        for _ in range(50):  # the worker counts just after the job flips to done
            _, raw = self.f.call("/metrics")
            if b'watoom_moss_jobs_total{status="done"} 1' in raw:
                break
            time.sleep(0.1)
        text = raw.decode()
        self.assertIn('watoom_moss_jobs_total{status="done"} 1', text)
        self.assertIn("watoom_moss_generation_seconds_count 1", text)
        self.assertIn("watoom_moss_steps_total 25", text)
        self.assertIn("watoom_moss_pixels_total %d" % (1216 * 832), text)
        self.assertNotIn("a lamp", text)

    def test_hide_removes_from_recent_without_deleting_files_and_is_reversible(self):
        _, job = self.f.call("/api/generate", {"scene": "a harbour at dawn", "seed": 3})
        done = self.f.wait(job["id"])
        img = done["image"]
        ident = img[:-4]
        out = pathlib.Path(self.f.manager.cfg["out_dir"])
        status, res = self.f.call("/api/gallery/" + ident + "/hide", {})
        self.assertEqual((200, True), (status, res.get("hidden")), res)
        self.assertEqual([], self.f.call("/api/gallery")[1]["items"])
        _, hid = self.f.call("/api/gallery?hidden=1")
        self.assertEqual([img], [i["image"] for i in hid["items"]])
        self.assertNotIn("scene", hid["items"][0])   # the prompt text of a hidden image is not returned
        self.assertTrue((out / img).is_file() and (out / (ident + ".json")).is_file())
        self.f.call("/api/gallery/" + ident + "/unhide", {})
        self.assertEqual([img], [i["image"] for i in self.f.call("/api/gallery")[1]["items"]])
        self.assertEqual([], self.f.call("/api/gallery?hidden=1")[1]["items"])
        status, _ = self.f.call("/api/gallery/" + "0" * 32 + "/hide", {})
        self.assertEqual(404, status)

    def test_engine_error_is_reported(self):
        _, job = self.f.call("/api/generate", {"scene": "FAIL this"})
        done = self.f.wait(job["id"])
        self.assertEqual("error", done["status"])
        self.assertEqual("out_of_memory", done["error"]["code"])

    def test_cancel_running_job(self):
        _, job = self.f.call("/api/generate", {"scene": "SLOW one"})
        for _ in range(100):
            _, j = self.f.call("/api/jobs/" + job["id"])
            if j["status"] == "running" and j["fraction"] > 0:
                break
            time.sleep(0.1)
        self.f.call("/api/jobs/" + job["id"] + "/cancel", {})
        self.assertEqual("cancelled", self.f.wait(job["id"])["status"])

    def test_validation_rejects_bad_input(self):
        bad = [{"scene": ""}, {"scene": "x", "width": 1000}, {"scene": "x", "width": 4096, "height": 4096}, {"scene": "x", "steps": 0},
               {"scene": "x", "steps": 1.5}, {"scene": "x", "preset_id": "nope"}, {"scene": "x", "sampler": "bogus"},
               {"scene": "x", "seed": "abc"}, {"scene": "x", "cfg": True}, {"scene": "x" * 5000}]
        for body in bad:
            st, r = self.f.call("/api/generate", body)
            self.assertEqual(400, st, body)
            self.assertEqual("invalid_params", r["error"]["code"])

    def test_post_guards(self):
        st, _ = self.f.call("/api/generate", {"scene": "x"}, headers={"Origin": "http://evil.example"})
        self.assertEqual(403, st)
        req = urllib.request.Request(self.f.base + "/api/generate", data=b"scene=x", headers={"Content-Type": "text/plain"})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(415, cm.exception.code)

    def test_image_paths_are_confined(self):
        for p in ("/api/images/../etc/passwd", "/api/images/%2e%2e%2fsecret.png", "/api/images/" + "a" * 32 + ".png", "/api/jobs/zz"):
            st, _ = self.f.call(p)
            self.assertEqual(404, st, p)


class GateTests(unittest.TestCase):
    def test_gate_refuses_when_gpu_busy(self):
        f = Fixture(gate="vram", smi_free=1900)
        try:
            _, job = f.call("/api/generate", {"scene": "a cat"})
            done = f.wait(job["id"])
            self.assertEqual("error", done["status"])
            self.assertEqual("gpu_busy", done["error"]["code"])
            self.assertEqual([], f.requests(), "engine must not even be started")
        finally:
            f.close()

    def test_gate_allows_when_gpu_free(self):
        f = Fixture(gate="vram", smi_free=12000)
        try:
            _, job = f.call("/api/generate", {"scene": "a cat"})
            self.assertEqual("done", f.wait(job["id"])["status"])
        finally:
            f.close()


if __name__ == "__main__":
    unittest.main()


class FakeSession:
    def __init__(self):
        self.state, self.calls = "idle", []

    def active(self):
        return self.state == "active"

    def snapshot(self):
        return {"state": self.state}

    def start(self):
        self.calls.append("start")
        self.state = "active"
        return self.snapshot()

    def end(self):
        self.calls.append("end")
        self.state = "idle"
        return self.snapshot()

    def shutdown(self):
        pass


class SessionApiTests(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()
        self.f.manager.session = FakeSession()

    def tearDown(self):
        self.f.close()

    def test_generate_requires_an_active_session(self):
        st, r = self.f.call("/api/generate", {"scene": "a cat"})
        self.assertEqual((409, "gpu_session_required"), (st, r["error"]["code"]))
        self.assertEqual([], self.f.requests())  # the engine was never started

    def test_session_endpoints_then_generate(self):
        st, r = self.f.call("/api/session/start", {})
        self.assertEqual((202, "active"), (st, r["state"]))
        st, job = self.f.call("/api/generate", {"scene": "a cat"})
        self.assertEqual(202, st)
        self.assertEqual("done", self.f.wait(job["id"])["status"])
        self.assertEqual("active", self.f.call("/api/status")[1]["session"]["state"])
        st, r = self.f.call("/api/session/end", {})
        self.assertEqual("idle", r["state"])

    def test_session_post_guards(self):
        st, _ = self.f.call("/api/session/start", {}, headers={"Origin": "http://evil.example"})
        self.assertEqual(403, st)
        self.assertEqual([], self.f.manager.session.calls)
