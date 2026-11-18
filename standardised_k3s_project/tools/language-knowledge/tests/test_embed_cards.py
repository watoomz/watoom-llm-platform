import hashlib, http.server, json, os, sys, tempfile, threading, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "embed"))
import embed_cards

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "mini-cards.jsonl")

class Handler(http.server.BaseHTTPRequestHandler):
    calls = 0
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        Handler.calls += 1
        data = [{"index": i, "embedding": [float((sum(t.encode()) + k) % 7 + 1) for k in range(384)]} for i, t in enumerate(body["input"])]
        out = json.dumps({"data": data}).encode()
        self.send_response(200); self.send_header("content-length", str(len(out))); self.end_headers(); self.wfile.write(out)
    def log_message(self, *a): pass

class EmbedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = "http://127.0.0.1:%d" % cls.srv.server_port
    @classmethod
    def tearDownClass(cls): cls.srv.shutdown()

    def run_embed(self, out, *extra):
        embed_cards.main(["--cards", FIXTURE, "--out", out, "--url", self.url, "--batch", "2", "--delay", "0", *extra])

    def test_complete_run_and_alignment(self):
        with tempfile.TemporaryDirectory() as d:
            self.run_embed(d)
            meta = json.load(open(os.path.join(d, "vectors.json")))
            self.assertEqual((meta["dim"], meta["count"]), (384, 5))
            self.assertEqual(os.path.getsize(os.path.join(d, "vectors.i8")), 5 * 384)
            sha = hashlib.sha256(open(FIXTURE, encoding="utf-8").read().encode()).hexdigest()[:16]
            self.assertEqual(meta["cards_sha"], sha)

    def test_partial_then_resume_is_identical(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            self.run_embed(a)
            self.run_embed(b, "--limit", "3")
            self.assertFalse(os.path.exists(os.path.join(b, "vectors.json")))
            self.run_embed(b)
            self.assertEqual(open(os.path.join(a, "vectors.i8"), "rb").read(), open(os.path.join(b, "vectors.i8"), "rb").read())

if __name__ == "__main__":
    unittest.main()
