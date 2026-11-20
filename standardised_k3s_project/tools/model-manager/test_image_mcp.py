import base64, hashlib, json, struct, tempfile, threading, unittest, urllib.request, urllib.error, zlib
from pathlib import Path
from http.server import ThreadingHTTPServer
from server import Application


class ImageMCP(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.token = "fixture-image-token-never-production"
        self.app = Application(
            self.tmp.name, "fixture-admin-password-never-production", "http://localhost", image_mcp_token=self.token
        )
        self.app.operations = object()
        self.model = {
            "id": "a" * 64,
            "revision": "b" * 40,
            "kind": "diffusion-pipeline",
            "registered": True,
            "settings": {"width": 1024, "height": 1024},
            "repository": "fixture/sdxl",
        }
        with self.app.store.db:
            self.app.store.db.execute(
                "INSERT INTO models VALUES(?,?,?)", (self.model["id"], self.model["revision"], json.dumps(self.model))
            )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self.app.handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = "http://127.0.0.1:" + str(self.server.server_address[1]) + "/mcp"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.app.store.close()
        self.tmp.cleanup()

    def rpc(self, method, params=None, token=None, notification=False):
        request = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if not notification:
            request["id"] = 1
        headers = {
            "Authorization": "Bearer " + (self.token if token is None else token),
            "Content-Type": "application/json",
        }
        with urllib.request.urlopen(
            urllib.request.Request(self.url, json.dumps(request).encode(), headers), timeout=3
        ) as f:
            return (f.status, None if f.status == 202 else json.load(f))

    def call(self, name, args=None):
        return self.rpc("tools/call", {"name": name, "arguments": args or {}})[1]["result"]

    def submit(self, **changes):
        args = {
            "request_id": "fixture-request",
            "installation_id": self.model["id"],
            "revision": self.model["revision"],
            "prompt": "A wooden park bench on a plain background.",
        }
        args.update(changes)
        return self.call("submit_image", args)

    def test_machine_auth_and_disabled(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.rpc("tools/list", token="wrong")
        self.assertEqual(cm.exception.code, 401)
        cm.exception.close()
        self.app.image_mcp_token = None
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.rpc("tools/list")
        self.assertEqual(cm.exception.code, 404)
        cm.exception.close()

    def test_initialize_and_notification(self):
        self.assertEqual(
            self.rpc("initialize", {"protocolVersion": "2025-11-25"})[1]["result"]["protocolVersion"], "2025-11-25"
        )
        self.assertEqual(self.rpc("notifications/initialized", notification=True), (202, None))

    def test_native_client_codemode_query(self):
        self.url += "?codemode=false"
        self.assertEqual(len(self.rpc("tools/list")[1]["result"]["tools"]), 5)

    def test_narrow_catalog(self):
        tools = self.rpc("tools/list")[1]["result"]["tools"]
        self.assertEqual(
            {t["name"] for t in tools},
            {"list_image_models", "submit_image", "image_job", "image_result", "list_session_images"},
        )
        models = self.call("list_image_models")["structuredContent"]["models"]
        self.assertEqual(models[0]["id"], self.model["id"])
        self.assertNotIn("artifacts", models[0])
        self.assertTrue(self.call("remove", {})["isError"])

    def test_quality_defaults_and_dimension_overrides(self):
        result = self.submit(settings={"width": 768, "height": 512})["structuredContent"]
        self.assertEqual(result["settings"]["steps"], 30)
        self.assertEqual(result["settings"]["guidance"], 7.0)
        self.assertEqual(result["settings"]["width"], 768)
        selection = json.loads(self.app.store.jobs()[0]["selection"])
        self.assertEqual(selection["settings"]["height"], 512)

    def test_generation_settings_cannot_change_runtime_or_exceed_budget(self):
        for settings in [
            {"precision": "float32"},
            {"base_model": "arbitrary"},
            {"width": 2048},
            {"width": 513},
            {"steps": 51},
            {"steps": True},
            {"guidance": 21},
        ]:
            self.assertTrue(self.submit(settings=settings)["isError"])
        self.assertEqual(len(self.app.store.jobs()), 0)

    def test_idempotency_and_conflicting_retry(self):
        a = self.submit()["structuredContent"]
        b = self.submit()["structuredContent"]
        self.assertEqual(a["job_id"], b["job_id"])
        self.assertEqual(len(self.app.store.jobs()), 1)
        self.assertTrue(self.submit(prompt="A different benign bench.")["isError"])
        self.assertEqual(len(self.app.store.jobs()), 1)

    def test_negative_prompt_is_durable_idempotent_and_reaches_worker(self):
        from operations import Operations
        from worker import Worker

        calls = []

        def broker(action, record, request, progress=None):
            calls.append(request)
            return {"tested": True}

        self.app.operations = Operations(self.app.store, Path(self.tmp.name) / "models", broker)
        first = self.submit(negative_prompt="blur, watermark")["structuredContent"]
        self.assertEqual(first["job_id"], self.submit(negative_prompt="blur, watermark")["structuredContent"]["job_id"])
        self.assertTrue(self.submit(negative_prompt="different")["isError"])
        self.assertTrue(Worker(self.app.store, self.app.operations).once())
        self.assertEqual(calls[0]["negative_prompt"], "blur, watermark")
        self.assertEqual(self.app.store.jobs()[0]["state"], "GENERATION_VERIFIED")

    def test_negative_prompt_bounds_and_old_payload_compatibility(self):
        for value in [None, 42, "x" * 4097]:
            self.assertTrue(self.submit(negative_prompt=value)["isError"])
        self.submit()
        self.assertNotIn("negative_prompt", json.loads(self.app.store.jobs()[0]["selection"]))

    def test_explicit_three_image_batch_is_distinct_fifo_and_receipted(self):
        from image_mcp import call
        from operations import Operations
        from worker import Worker

        seen = []

        def broker(action, record, request, progress=None):
            seen.append(request["prompt"])
            return {"tested": True}

        self.app.operations = Operations(self.app.store, Path(self.tmp.name) / "models", broker)
        prompts = ["A wooden bench, front view", "A wooden bench, side view", "A wooden bench, rear view"]
        keys = []
        for i, prompt in enumerate(prompts):
            args = {
                "request_id": "batch-fixture-" + str(i),
                "installation_id": self.model["id"],
                "revision": self.model["revision"],
                "prompt": prompt,
                "negative_prompt": "blur, watermark",
            }
            keys.append(call(self.app, "submit_image", args, "ses_batchfixture")["structuredContent"]["job_id"])
        self.assertEqual(len(set(keys)), 3)
        worker = Worker(self.app.store, self.app.operations)
        for _ in prompts:
            self.assertTrue(worker.once())
        self.assertFalse(worker.once())
        self.assertEqual(seen, prompts)
        receipts = call(self.app, "list_session_images", {}, "ses_batchfixture")["structuredContent"]["jobs"]
        self.assertEqual({r["job_id"] for r in receipts}, set(keys))
        self.assertTrue(all(r["state"] == "GENERATION_VERIFIED" for r in receipts))

    def test_rejects_unregistered_nonimage_and_arbitrary_fields(self):
        self.assertTrue(self.submit(installation_id="c" * 64)["isError"])
        self.assertTrue(self.submit(path="/etc/passwd")["isError"])
        self.model["kind"] = "gguf"
        with self.app.store.db:
            self.app.store.db.execute("UPDATE models SET record=?", (json.dumps(self.model),))
        self.assertTrue(self.submit()["isError"])
        self.assertEqual(self.app.store.jobs(), [])

    def test_maintenance_blocks_only_new_work(self):
        job = self.submit()["structuredContent"]["job_id"]
        p = Path(self.tmp.name) / "maintenance"
        p.write_text("{}")
        self.app.maintenance_file = p
        self.assertTrue(self.submit(request_id="new")["isError"])
        self.assertEqual(self.call("image_job", {"job_id": job})["structuredContent"]["state"], "QUEUED")

    def test_result_requires_integrity_and_restoration(self):
        key = self.submit()["structuredContent"]["job_id"]

        def chunk(name, data):
            return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data) & 0xFFFFFFFF)

        png = (
            bytes([137, 80, 78, 71, 13, 10, 26, 10])
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\x20\x40\x60"))
            + chunk(b"IEND", b"")
        )
        result = {
            "width": 1,
            "height": 1,
            "png_base64": base64.b64encode(png).decode(),
            "sha256": hashlib.sha256(png).hexdigest(),
        }
        self.app.store.save_result(key, result)
        self.app.store.transition(key, "GENERATION_VERIFIED")
        self.assertTrue(self.call("image_result", {"job_id": key})["isError"])
        result["restoration"] = {"verified": True, "deployment": "fixture-chat"}
        self.app.store.save_result(key, result)
        out = self.call("image_result", {"job_id": key})
        self.assertEqual(out["content"][1]["type"], "image")
        result["sha256"] = "0" * 64
        self.app.store.save_result(key, result)
        self.assertTrue(self.call("image_result", {"job_id": key})["isError"])

    def test_old_release_insert_remains_compatible(self):
        self.app.store.db.execute("INSERT INTO image_requests VALUES(?,?,?)", ("old-release", "old-digest", "old-job"))
        self.assertEqual(self.app.store.db.execute("SELECT count(*) FROM image_request_sessions").fetchone()[0], 0)

    def test_native_metadata_reaches_durable_receipt(self):
        args = {
            "request_id": "http-scoped",
            "installation_id": self.model["id"],
            "revision": self.model["revision"],
            "prompt": "A wooden bench.",
        }
        self.rpc(
            "tools/call",
            {"name": "submit_image", "arguments": args, "_meta": {"ai.opencode/sessionID": "ses_fixtureHTTP"}},
        )
        result = self.rpc(
            "tools/call",
            {"name": "list_session_images", "arguments": {}, "_meta": {"ai.opencode/sessionID": "ses_fixtureHTTP"}},
        )[1]["result"]
        self.assertEqual(len(result["structuredContent"]["jobs"]), 1)

    def test_session_receipts_are_scoped_and_do_not_adopt_history(self):
        from image_mcp import call

        args = {
            "request_id": "scoped",
            "installation_id": self.model["id"],
            "revision": self.model["revision"],
            "prompt": "A park bench.",
        }
        key = call(self.app, "submit_image", args, "ses_fixtureA")["structuredContent"]["job_id"]
        self.assertEqual(
            call(self.app, "list_session_images", {}, "ses_fixtureA")["structuredContent"]["jobs"][0]["job_id"], key
        )
        self.assertEqual(call(self.app, "list_session_images", {}, "ses_fixtureB")["structuredContent"]["jobs"], [])
        with self.assertRaises(ValueError):
            call(self.app, "submit_image", args, "ses_fixtureB")
        with self.assertRaises(ValueError):
            call(self.app, "list_session_images", {})
        historical = self.submit()["structuredContent"]["job_id"]
        self.assertNotIn(
            historical,
            [
                j["job_id"]
                for j in call(self.app, "list_session_images", {}, "ses_fixtureA")["structuredContent"]["jobs"]
            ],
        )
        self.assertEqual(len(self.app.store.jobs()), 2)

    def test_cannot_read_other_manager_jobs(self):
        key = self.app.store.enqueue({"operation": "generate", "id": "other"})
        self.assertTrue(self.call("image_job", {"job_id": key})["isError"])


if __name__ == "__main__":
    unittest.main()
