import base64, json, tempfile, threading, unittest, urllib.request, urllib.error
from http.server import ThreadingHTTPServer
from server import Application


class HTTP(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Application(self.tmp.name, "fixture-password-for-tests-only", "http://localhost")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self.app.handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = "http://127.0.0.1:" + str(self.server.server_address[1])
        self.auth = "Basic " + base64.b64encode(b"admin:fixture-password-for-tests-only").decode()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def request(self, path, data=None, headers=None):
        return urllib.request.urlopen(urllib.request.Request(self.url + path, data, headers or {}), timeout=3)

    def test_auth(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.request("/api/jobs")
        self.assertEqual(e.exception.code, 401)
        with self.request("/api/session", headers={"Authorization": self.auth}) as response:
            self.assertIn("csrf", json.load(response))

    def test_csrf(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.request("/api/inspect", b"{}", {"Authorization": self.auth, "Origin": "https://evil.example"})
        self.assertEqual(e.exception.code, 403)

    def test_no_get_mutation(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.request("/api/remove", headers={"Authorization": self.auth})
        self.assertEqual(e.exception.code, 404)

    def test_maintenance_blocks_new_work(self):
        from pathlib import Path

        path = Path(self.tmp.name) / "maintenance.json"
        path.write_text("{}")
        self.app.maintenance_file = path
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.request(
                "/api/cancel",
                b'{"id":"x"}',
                {"Authorization": self.auth, "Origin": "http://localhost", "X-CSRF-Token": self.app.csrf},
            )
        self.assertEqual(e.exception.code, 503)

    def test_safe_reset_survives_reinspection(self):
        class Hub:
            def inspect(self, url):
                return {
                    "repository": "fixture/model",
                    "revision": "a" * 40,
                    "kind": "gguf",
                    "documents": {"generation_config.json": {"temperature": 0.2}},
                }

        self.app.hub = Hub()
        headers = {"Authorization": self.auth, "Origin": "http://localhost", "X-CSRF-Token": self.app.csrf}
        with self.request(
            "/api/overrides",
            json.dumps({"url": "https://huggingface.co/fixture/model", "values": {}, "safe_only": True}).encode(),
            headers,
        ) as response:
            self.assertEqual(json.load(response)["values"]["temperature"], 1)
        with self.request(
            "/api/inspect", json.dumps({"url": "https://huggingface.co/fixture/model"}).encode(), headers
        ) as response:
            self.assertEqual(json.load(response)["settings"]["values"]["temperature"], 1)

    def test_escape_ui(self):
        with self.request("/", headers={"Authorization": self.auth}) as response:
            self.assertIn("object-src 'none'", response.headers["Content-Security-Policy"])
            self.assertIn(b"Model Manager", response.read())


if __name__ == "__main__":
    unittest.main()
