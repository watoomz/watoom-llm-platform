import json, pathlib, sys, tempfile, threading, time, unittest, urllib.error, urllib.request

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
import creation_studio_service as svc  # noqa: E402
from fakes import FakeMeshBridge, FakeModelManager, FakeMoss, FakeRouter  # noqa: E402


class Fixture:
    """Builds a real creation-studio HTTP server pointed at fake Model Manager / MOSS / Mesh backends."""

    def __init__(self, with_model_manager=True, with_mesh=False, glb_mode=None, glb_output=False):
        self.tmp = tempfile.TemporaryDirectory()
        self.mm = FakeModelManager() if with_model_manager else None
        self.moss = FakeMoss()
        password_file = pathlib.Path(self.tmp.name) / "password"
        password_file.write_text(self.mm.password if self.mm else "unused")
        mm_client = None
        if self.mm:
            mm_client = svc.ModelManagerClient(self.mm.base_url, self.mm.origin, self.mm.password)
        moss_client = svc.MossClient(self.moss.base_url)
        self.mesh_path = pathlib.Path(self.tmp.name) / "mesh-status.json"
        self.mesh = None
        mesh_client = None
        if with_mesh:
            mesh_socket = pathlib.Path(self.tmp.name) / "mesh-bridge.sock"
            self.mesh = FakeMeshBridge(str(mesh_socket))
            mesh_client = svc.MeshClient(str(mesh_socket))
        cfg = {"mm_origin": self.mm.base_url if self.mm else "", "moss_label": self.moss.base_url,
               "mesh_observability_path": str(self.mesh_path)}
        self.router, glb_coder = None, None
        if glb_mode:
            self.router = FakeRouter(glb_mode)
            self.glb_dir = pathlib.Path(self.tmp.name) / "glb" if glb_output else None
            glb_coder = svc.GlbCoder(self.router.base_url, output_dir=str(self.glb_dir) if self.glb_dir else "")
        self.httpd = svc.ThreadingHTTPServer(("127.0.0.1", 0), svc.make_handler(mm_client, moss_client, mesh_client, cfg, glb_coder))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = "http://127.0.0.1:%d" % self.httpd.server_address[1]

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        if self.mm:
            self.mm.close()
        if self.mesh:
            self.mesh.close()
        if self.router:
            self.router.close()
        self.moss.close()
        self.tmp.cleanup()

    def call(self, path, body=None, method=None):
        data = None if body is None else json.dumps(body).encode()
        headers = {"Content-Type": "application/json"} if body is not None else {}
        req = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                raw = r.read()
                ctype = r.headers.get("Content-Type", "")
                return r.status, (json.loads(raw) if ctype.startswith("application/json") else raw)
        except urllib.error.HTTPError as e:
            raw = e.read()
            e.close()
            try:
                return e.code, json.loads(raw or b"{}")
            except ValueError:
                return e.code, raw


class IndexPageTests(unittest.TestCase):
    def test_serves_three_pipeline_sections(self):
        f = Fixture()
        try:
            status, body = f.call("/")
            self.assertEqual(200, status)
            text = body.decode()
            for marker in ('id="sdxl"', 'id="moss"', 'id="mesh"'):
                self.assertIn(marker, text)
        finally:
            f.close()


class SdxlProxyTests(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()

    def tearDown(self):
        self.f.close()

    def test_models_are_proxied_from_model_manager(self):
        status, body = self.f.call("/api/sdxl/models")
        self.assertEqual(200, status)
        self.assertEqual("stabilityai/stable-diffusion-xl-base-1.0", body[0]["repository"])

    def test_generate_requires_all_fields(self):
        status, body = self.f.call("/api/sdxl/generate", {"id": "m1"}, method="POST")
        self.assertEqual(400, status)
        self.assertEqual("invalid_params", body["error"]["code"])

    def test_generate_logs_in_then_calls_model_manager_generate_with_csrf(self):
        status, body = self.f.call("/api/sdxl/generate", {"id": "m1", "revision": "r1", "prompt": "a blue cube"}, method="POST")
        self.assertEqual(202, status)
        job = body["job"]
        self.assertTrue(job.startswith("deadbeef"))
        methods_paths = [(m, p) for m, p, *_ in self.f.mm.requests]
        self.assertIn(("POST", "/login"), methods_paths)
        self.assertIn(("GET", "/api/session"), methods_paths)
        self.assertIn(("POST", "/api/generate"), methods_paths)
        # the real generate call carried the CSRF token and JSON body creation_studio_service built
        generate_call = next(c for c in self.f.mm.requests if c[0] == "POST" and c[1] == "/api/generate")
        self.assertEqual("fixture-csrf-token", generate_call[2]["X-CSRF-Token"])
        self.assertEqual({"id": "m1", "revision": "r1", "prompt": "a blue cube"}, json.loads(generate_call[3]))

    def test_result_is_proxied_after_generation(self):
        _, body = self.f.call("/api/sdxl/generate", {"id": "m1", "revision": "r1", "prompt": "hello"}, method="POST")
        status, result = self.f.call("/api/sdxl/result?id=" + body["job"])
        self.assertEqual(200, status)
        self.assertEqual("generated: hello", result["text"])

    def test_model_manager_rejecting_login_surfaces_as_upstream_error(self):
        self.f.mm.password = "a-different-password-entirely"
        status, body = self.f.call("/api/sdxl/generate", {"id": "m1", "revision": "r1", "prompt": "x"}, method="POST")
        self.assertEqual(502, status)
        self.assertEqual("model_manager_login_failed", body["error"]["code"])


class SdxlDisabledTests(unittest.TestCase):
    def test_sdxl_routes_refuse_cleanly_when_model_manager_is_not_configured(self):
        f = Fixture(with_model_manager=False)
        try:
            status, body = f.call("/api/sdxl/models")
            self.assertEqual(503, status)
            self.assertEqual("model_manager_disabled", body["error"]["code"])
        finally:
            f.close()


class MossProxyTests(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()

    def tearDown(self):
        self.f.close()

    def test_presets_are_proxied(self):
        status, body = self.f.call("/api/moss/presets")
        self.assertEqual(200, status)
        self.assertEqual("Kodak Portra 400", body["presets"][0]["name"])

    def test_generate_proxies_scene_and_preset_untouched(self):
        status, body = self.f.call("/api/moss/generate", {"scene": "a cat", "preset_id": "kodak-portra-400"}, method="POST")
        self.assertEqual(202, status)
        self.assertTrue(JOB := body["id"])
        posted = next(c for c in self.f.moss.requests if c[0] == "POST" and c[1] == "/api/generate")
        self.assertEqual({"scene": "a cat", "preset_id": "kodak-portra-400"}, posted[2])
        status, job = self.f.call("/api/moss/jobs/" + JOB)
        self.assertEqual("done", job["status"])

    def test_image_bytes_are_proxied(self):
        status, raw = self.f.call("/api/moss/images/" + "f" * 32 + ".png")
        self.assertEqual(200, status)
        self.assertTrue(raw.startswith(b"\x89PNG"))

    def test_paths_outside_the_allow_list_are_refused(self):
        status, body = self.f.call("/api/moss/metrics")
        self.assertEqual(404, status)
        self.assertEqual("not_found", body["error"]["code"])
        self.assertNotIn(("GET", "/metrics"), [c[:2] for c in self.f.moss.requests])

    def test_moss_unreachable_is_reported_as_service_error_not_crash(self):
        self.f.moss.close()
        status, body = self.f.call("/api/moss/presets")
        self.assertEqual(503, status)
        self.assertEqual("moss_unreachable", body["error"]["code"])


class MeshNotConfiguredTests(unittest.TestCase):
    """No --mesh-bridge-socket given: generation refuses cleanly, status says wired=False."""

    def setUp(self):
        self.f = Fixture()

    def tearDown(self):
        self.f.close()

    def test_generate_refuses_with_a_clear_not_configured_error(self):
        status, body = self.f.call("/api/mesh/generate", {"prompt": "a simple cube"}, method="POST")
        self.assertEqual(503, status)
        self.assertEqual("mesh_not_configured", body["error"]["code"])
        self.assertIn("opencode_mesh_bridge", body["error"]["message"])

    def test_status_without_observability_file_reports_unavailable(self):
        status, body = self.f.call("/api/mesh/status")
        self.assertEqual(200, status)
        self.assertFalse(body["telemetry_available"])
        self.assertFalse(body["wired"])

    def test_status_reads_real_observability_snapshot(self):
        self.f.mesh_path.write_text(json.dumps({"schema": "watoom.gpu-observation.v1", "sampledAt": int(time.time() * 1000),
                                                 "phase": "mesh-ready", "owner": "20261012T120132Z-04c4b829", "generation": 9,
                                                 "uncertain": False, "primary": "swift-qwen38-coder", "activeRequests": 0}))
        status, body = self.f.call("/api/mesh/status")
        self.assertEqual(200, status)
        self.assertTrue(body["telemetry_available"])
        self.assertEqual("mesh-ready", body["phase"])
        self.assertTrue(body["mesh_owns_gpu"])
        self.assertFalse(body["wired"])

    def test_malformed_observability_file_fails_closed_not_crash(self):
        self.f.mesh_path.write_text("not json")
        status, body = self.f.call("/api/mesh/status")
        self.assertEqual(200, status)
        self.assertFalse(body["telemetry_available"])


class MeshWiredTests(unittest.TestCase):
    """--mesh-bridge-socket given (a fake bridge stands in for opencode_mesh_bridge.py): the real
    submit/list/status/retrieve operations are proxied over the socket, not refused."""

    def setUp(self):
        self.f = Fixture(with_mesh=True)

    def tearDown(self):
        self.f.close()

    def test_status_reports_wired_true(self):
        status, body = self.f.call("/api/mesh/status")
        self.assertEqual(200, status)
        self.assertTrue(body["wired"])
        self.assertIsNone(body["blocker"])

    def test_generate_submits_over_the_bridge_socket(self):
        status, body = self.f.call("/api/mesh/generate", {"prompt": "a simple cube"}, method="POST")
        self.assertEqual(202, status)
        self.assertEqual("pending", body["state"])
        self.assertEqual(1, len(self.f.mesh.requests))
        self.assertEqual("submit", self.f.mesh.requests[0]["operation"])
        self.assertEqual("a simple cube", self.f.mesh.requests[0]["prompt"])

    def test_generate_requires_a_prompt(self):
        status, body = self.f.call("/api/mesh/generate", {}, method="POST")
        self.assertEqual(400, status)
        self.assertEqual("invalid_params", body["error"]["code"])
        self.assertEqual(0, len(self.f.mesh.requests))

    def test_jobs_and_result_are_proxied_after_a_submit(self):
        status, body = self.f.call("/api/mesh/generate", {"prompt": "a torch"}, method="POST")
        job_id = body["job_id"]
        status, body = self.f.call("/api/mesh/jobs")
        self.assertEqual(200, status)
        self.assertEqual([job_id], [j["job_id"] for j in body["jobs"]])
        status, body = self.f.call("/api/mesh/job?id=" + job_id)
        self.assertEqual(200, status)
        self.assertTrue(body["completion"])
        status, body = self.f.call("/api/mesh/result?id=" + job_id)
        self.assertEqual(200, status)
        self.assertEqual("/assets/fixture.glb", body["artifacts"]["glb"])

    def test_unknown_job_surfaces_as_a_clean_upstream_error_not_a_crash(self):
        status, body = self.f.call("/api/mesh/job?id=does-not-exist")
        self.assertEqual(502, status)
        self.assertEqual("mesh_rejected", body["error"]["code"])


class GlbCoderTests(unittest.TestCase):
    def wait(self, fx, job_id, states=("done", "failed", "cancelled")):
        deadline = time.time() + 10
        while time.time() < deadline:
            status, job = fx.call("/api/glb/job?id=" + job_id)
            if job["state"] in states:
                return job
            time.sleep(0.05)
        self.fail("job did not reach %s: %s" % (states, job))

    def test_config_has_all_card_domains_system_prompt_and_sampling(self):
        fx = Fixture(glb_mode="ok")
        try:
            status, cfg = fx.call("/api/glb/config")
            self.assertEqual(200, status)
            self.assertEqual(25, len(cfg["domains"]))
            self.assertEqual("Characters and NPCs", cfg["domains"][0]["domain"])
            self.assertEqual("Create a glowing rune sequence console with three stone buttons.", cfg["domains"][-1]["prompt"])
            self.assertEqual(6, len(cfg["gallery"]))
            self.assertEqual({"temperature": 0.8, "top_k": 40, "top_p": 0.95, "min_p": 0.0, "repeat_penalty": 1.0}, cfg["sampling"])
            self.assertTrue(cfg["system_prompt"].startswith("Create game assets for the Godot editor"))
        finally:
            fx.close()

    def test_generate_streams_card_settings_and_serves_a_sandboxed_page(self):
        fx = Fixture(glb_mode="ok", glb_output=True)
        try:
            status, job = fx.call("/api/glb/generate", {"prompt": "  Create a short iron sword.  "})
            self.assertEqual(202, status)
            job = self.wait(fx, job["id"])
            self.assertEqual("done", job["state"], job)
            self.assertTrue(job["has_html"])
            self.assertEqual(len("I will build a sword."), job["reasoning_chars"])
            self.assertEqual(321, job["usage"]["completion_tokens"])
            path, headers, body = fx.router.requests[0]
            self.assertEqual("/v1/chat/completions", path)
            self.assertEqual("glb-3d-coder", body["model"])
            self.assertTrue(body["stream"])
            self.assertNotIn("max_tokens", body)  # the card: no output cap
            self.assertEqual(0.8, body["temperature"]); self.assertEqual(40, body["top_k"])
            self.assertEqual(0.95, body["top_p"]); self.assertEqual(0.0, body["min_p"]); self.assertEqual(1.0, body["repeat_penalty"])
            self.assertTrue(body["chat_template_kwargs"]["enable_thinking"])
            self.assertEqual([svc.GLB_SYSTEM_PROMPT, "Create a short iron sword."], [m["content"] for m in body["messages"]])
            self.assertEqual("creation-studio-glb-" + job["id"], headers["X-Watoom-Request-Id"])
            req = urllib.request.Request(fx.base + "/api/glb/page?id=" + job["id"])
            with urllib.request.urlopen(req, timeout=10) as r:
                page = r.read().decode()
                csp = r.headers["Content-Security-Policy"]
            self.assertTrue(page.startswith("<!DOCTYPE html>") and page.endswith("</html>"))
            # T-0103: the preview reports the page's own JS errors; the download is the model's page unchanged
            self.assertIn(svc.GLB_ERROR_REPORTER.decode(), page)
            self.assertLess(page.index("glb-page-error"), page.index("</head>") if "</head>" in page else len(page))
            with urllib.request.urlopen(fx.base + "/api/glb/page?id=" + job["id"] + "&download=1", timeout=10) as r:
                self.assertNotIn(b"glb-page-error", r.read())
            self.assertTrue(csp.startswith("sandbox allow-scripts allow-downloads"))
            self.assertNotIn("allow-same-origin", csp)
            self.assertIn("https://cdn.jsdelivr.net", csp)
            self.assertTrue((fx.glb_dir / (job["id"] + ".html")).is_file())
            # a restart reloads finished jobs from the output directory
            again = svc.GlbCoder(fx.router.base_url, output_dir=str(fx.glb_dir))
            self.assertEqual("done", again.status(job["id"])["state"])
            self.assertTrue(again.html(job["id"]).startswith(b"<!DOCTYPE html>"))
        finally:
            fx.close()

    def test_error_reporter_goes_first_in_head(self):
        self.assertEqual(b"<html><head lang=x>" + svc.GLB_ERROR_REPORTER + b"<title>t</title></head></html>",
                         svc.with_error_reporter(b"<html><head lang=x><title>t</title></head></html>"))
        self.assertEqual(svc.GLB_ERROR_REPORTER + b"<p>no head</p>", svc.with_error_reporter(b"<p>no head</p>"))

    def test_repair_sends_the_page_back_with_its_error(self):
        fx = Fixture(glb_mode="ok", glb_output=True)
        try:
            status, first = fx.call("/api/glb/generate", {"prompt": "Create a short iron sword."})
            first = self.wait(fx, first["id"])
            page = svc.GlbCoder(fx.router.base_url, output_dir=str(fx.glb_dir)).html(first["id"]).decode()
            error = "Uncaught SyntaxError: Identifier 'bandWidth' has already been declared (line 753)"
            status, job = fx.call("/api/glb/repair", {"id": first["id"], "error": error})
            self.assertEqual(202, status, job)
            self.assertEqual(first["id"], job["repair_of"]); self.assertEqual(error, job["repair_error"])
            self.assertEqual("Create a short iron sword.", job["prompt"])
            job = self.wait(fx, job["id"])
            self.assertEqual("done", job["state"], job)
            body = fx.router.requests[-1][2]
            self.assertEqual(["system", "user", "assistant", "user"], [m["role"] for m in body["messages"]])
            self.assertEqual([svc.GLB_SYSTEM_PROMPT, "Create a short iron sword.", page], [m["content"] for m in body["messages"][:3]])
            self.assertIn(error, body["messages"][3]["content"])
            self.assertIn("complete corrected HTML file", body["messages"][3]["content"])
            self.assertNotIn("looked at the rendered asset", body["messages"][3]["content"])
            self.assertEqual(0.8, body["temperature"]); self.assertTrue(body["chat_template_kwargs"]["enable_thinking"])
            # the link to the source survives a restart (it is kept in the job record)
            again = svc.GlbCoder(fx.router.base_url, output_dir=str(fx.glb_dir))
            self.assertEqual(first["id"], again.status(job["id"])["repair_of"])
        finally:
            fx.close()

    def test_revise_with_notes_only(self):
        fx = Fixture(glb_mode="ok", glb_output=True)
        try:
            status, first = fx.call("/api/glb/generate", {"prompt": "Create a treasure chest."})
            first = self.wait(fx, first["id"])
            notes = "The left and right walls are missing; make all four walls and the bottom solid."
            status, job = fx.call("/api/glb/repair", {"id": first["id"], "notes": notes})
            self.assertEqual(202, status, job)
            self.assertIsNone(job["repair_error"]); self.assertEqual(notes, job["repair_notes"])
            self.wait(fx, job["id"])
            text = fx.router.requests[-1][2]["messages"][3]["content"]
            self.assertIn(notes, text); self.assertIn("closed, solid geometry", text)
            self.assertNotIn("JavaScript error", text); self.assertTrue(text.endswith("complete corrected HTML file."))
        finally:
            fx.close()

    def test_repeating_block_catches_a_loop_but_not_ordinary_repetition(self):
        loop = ("Actual ExtrudeGeometry creates group material 0 for front/back, 1 for sides, but only if material array "
                "supplied. We can pass [interior, interior] maybe. ")
        self.assertEqual(len(loop), svc.repeating_block("Some real thinking first. " * 3 + loop * 12))
        self.assertEqual(0, svc.repeating_block("Some real thinking first. " * 3 + loop * 5))  # under the 1500-char span
        self.assertEqual(0, svc.repeating_block("    positions.push(0.0, 0.0, 0.0, 1.0);\n" * 8))  # code repeating a line
        self.assertEqual(0, svc.repeating_block("".join("const part%d = makePart(%d, 0.5, 1.25);\n" % (i, i) for i in range(200))))

    def test_repair_refuses_without_error_page_or_job(self):
        fx = Fixture(glb_mode="error")
        try:
            status, failed = fx.call("/api/glb/generate", {"prompt": "Create a pine tree."})
            failed = self.wait(fx, failed["id"])
            self.assertEqual(400, fx.call("/api/glb/repair", {"id": failed["id"], "error": " "})[0])
            self.assertEqual(400, fx.call("/api/glb/repair", {"id": failed["id"], "error": "", "notes": "  "})[0])
            self.assertEqual(404, fx.call("/api/glb/repair", {"id": failed["id"], "error": "x"})[0])  # no page to repair
            self.assertEqual(404, fx.call("/api/glb/repair", {"id": "0" * 32, "error": "x"})[0])
            self.assertEqual(400, fx.call("/api/glb/repair", {"id": "../etc", "error": "x"})[0])
            self.assertEqual(400, fx.call("/api/glb/repair", {"error": "x"})[0])
        finally:
            fx.close()

    def test_router_error_fails_the_job_with_its_message(self):
        fx = Fixture(glb_mode="error")
        try:
            status, job = fx.call("/api/glb/generate", {"prompt": "Create a pine tree."})
            job = self.wait(fx, job["id"])
            self.assertEqual("failed", job["state"])
            self.assertIn("GPU owned or controller unavailable", job["error"])
            status, body = fx.call("/api/glb/page?id=" + job["id"])
            self.assertEqual(404, status)
        finally:
            fx.close()

    def test_one_job_at_a_time_and_cancel(self):
        fx = Fixture(glb_mode="slow")
        try:
            status, job = fx.call("/api/glb/generate", {"prompt": "Create a pine tree."})
            self.wait(fx, job["id"], states=("thinking",))
            status, body = fx.call("/api/glb/generate", {"prompt": "Create another."})
            self.assertEqual(409, status)
            self.assertEqual("busy", body["error"]["code"])
            status, body = fx.call("/api/glb/cancel?id=" + job["id"], {})
            self.assertEqual(200, status)
            self.assertEqual("cancelled", self.wait(fx, job["id"])["state"])
        finally:
            fx.close()

    def test_rejects_bad_input_and_reports_not_configured(self):
        fx = Fixture(glb_mode="ok")
        try:
            self.assertEqual(400, fx.call("/api/glb/generate", {"prompt": "   "})[0])
            self.assertEqual(400, fx.call("/api/glb/job?id=../../etc")[0])
            self.assertEqual(404, fx.call("/api/glb/job?id=" + "0" * 32)[0])
        finally:
            fx.close()
        fx = Fixture()
        try:
            status, body = fx.call("/api/glb/config")
            self.assertEqual(503, status)
            self.assertEqual("glb_not_configured", body["error"]["code"])
        finally:
            fx.close()

    def test_extract_html(self):
        self.assertIsNone(svc.extract_html("no page"))
        self.assertEqual("<html><body></body></html>", svc.extract_html("text <html><body></body></html> more"))


class MeshStatusUnitTests(unittest.TestCase):
    def test_wrong_schema_is_treated_as_unavailable(self):
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / "status.json"
            path.write_text(json.dumps({"schema": "something.else", "phase": "qwen-ready"}))
            result = svc.mesh_status(str(path), wired=False)
            self.assertFalse(result["telemetry_available"])


if __name__ == "__main__":
    unittest.main()
