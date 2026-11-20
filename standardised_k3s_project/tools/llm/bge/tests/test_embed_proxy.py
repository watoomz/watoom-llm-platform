import json, math, pathlib, sys, threading, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import embed_proxy as ep

class FakeBackend:
    """Tokens are word indexes; a window's vector encodes its first token and length."""
    def __init__(self): self.calls = []; self.lock = threading.Lock()
    def __call__(self, path, body, timeout=60):
        with self.lock: self.calls.append(path)
        if path == "/tokenize":
            return {"tokens": list(range(1000, 1000 + len(body["content"].split())))}
        data = []
        for i, toks in enumerate(body["input"]):
            assert toks[0] == 101 and toks[-1] == 102 and len(toks) <= 512, "window must be [CLS]..[SEP] within 512"
            v = [float(toks[1]), float(len(toks)), 1.0]; n = math.sqrt(sum(x * x for x in v))
            data.append({"index": i, "embedding": [x / n for x in v]})
        return {"data": data}

class ProxyTests(unittest.TestCase):
    def test_request_bounds(self):
        self.assertIsNone(ep.check_body_size(100))
        self.assertEqual(ep.check_body_size(ep.MAX_BODY_BYTES + 1)[0], 413)
        self.assertEqual(ep.check_body_size(-1)[0], 400)
        self.assertIsNone(ep.check_inputs(["ok"]))
        self.assertIsNone(ep.check_inputs(["a" * ep.MAX_TEXT_CHARS] * 100))
        self.assertEqual(ep.check_inputs(["a" * (ep.MAX_TEXT_CHARS + 1)])[0], 413)
        self.assertEqual(ep.check_inputs(["a" * ep.MAX_TEXT_CHARS] * 200)[0], 413)
        for bad in ([], [""], [1], "str", None, ["x"] * (ep.MAX_INPUTS + 1)):
            self.assertEqual(ep.check_inputs(bad)[0], 400)

    def test_windows_cover_every_token_with_overlap(self):
        toks = list(range(1200)); parts = ep.windows(toks)
        self.assertTrue(all(len(p) <= ep.WINDOW for p in parts))
        self.assertEqual(sorted(set(t for p in parts for t in p)), toks)
        self.assertEqual(parts[1][0], ep.WINDOW - ep.OVERLAP)
        self.assertEqual(ep.windows(list(range(10))), [list(range(10))])

    def test_short_input_is_one_window_and_long_input_is_combined_and_normalised(self):
        fake = FakeBackend(); e = ep.Embedder("http://x", 101, 102, post=fake)
        short, long_ = e.embed(["a b c", " ".join(["w"] * 1500)])
        self.assertAlmostEqual(sum(x * x for x in short), 1.0, places=6)
        self.assertAlmostEqual(sum(x * x for x in long_), 1.0, places=6)
        self.assertEqual(e.metrics["chunked_inputs"], 1)
        self.assertGreaterEqual(e.metrics["backend_windows"], 4)

    def test_cache_avoids_repeat_backend_work(self):
        fake = FakeBackend(); e = ep.Embedder("http://x", 101, 102, post=fake)
        first = e.embed(["same text"]); n = len(fake.calls)
        self.assertEqual(e.embed(["same text"]), first); self.assertEqual(len(fake.calls), n)
        self.assertEqual(e.metrics["cache_hits"], 1)

    def test_cache_is_bounded(self):
        e = ep.Embedder("http://x", 101, 102, cache_size=3, post=FakeBackend())
        e.embed([f"text {i}" for i in range(10)])
        self.assertEqual(len(e.cache), 3)

    def test_batches_are_paced_and_queries_are_not(self):
        e = ep.Embedder("http://x", 101, 102, post=FakeBackend(), batch_rate=200.0)
        self.assertEqual(e.pace(1), 0.0)
        self.assertEqual(e.pace(ep.INTERACTIVE_WINDOWS), 0.0)
        e.pace(40)  # reserves 0.2 s
        started = ep.time.monotonic()
        waited = e.pace(40)
        self.assertGreater(waited, 0.15)
        self.assertGreaterEqual(ep.time.monotonic() - started, 0.15)
        self.assertEqual(e.pace(2), 0.0)  # a query is not queued behind the batch
        self.assertGreater(e.metrics["paced_seconds_total"], 0.15)
        self.assertEqual(ep.Embedder("http://x", 101, 102, post=FakeBackend(), batch_rate=0).pace(500), 0.0)

    def test_batches_slow_down_while_primary_model_is_busy(self):
        import os, tempfile
        with tempfile.TemporaryDirectory() as d:
            status = os.path.join(d, "status.json")
            def write(active, age=0.0):
                with open(status, "w") as f:
                    json.dump({"activeRequests": active, "sampledAt": (ep.time.time() - age) * 1000}, f)
            write(1)
            e = ep.Embedder("http://x", 101, 102, post=FakeBackend(), batch_rate=1000.0, busy_file=status, busy_rate=100.0)
            self.assertTrue(e.busy())
            e.pace(20)
            self.assertGreater(e.pace(20), 0.15)  # 20 windows at 100/s, not 1000/s
            self.assertEqual(e.pace(2), 0.0)  # interactive queries are never paced
            self.assertEqual(e.metrics["busy_paced_batches_total"], 2)
            write(1, age=30); e.busy_seen = (-1.0, False)
            self.assertFalse(e.busy())  # stale status falls back to normal pacing
            os.remove(status); e.busy_seen = (-1.0, False)
            self.assertFalse(e.busy())
            write(0); e.busy_seen = (-1.0, False)
            self.assertFalse(e.busy())

    def test_concurrency_is_bounded(self):
        active, peak, lock = [0], [0], threading.Lock()
        fake = FakeBackend()
        def slow(path, body, timeout=60):
            with lock: active[0] += 1; peak[0] = max(peak[0], active[0])
            try:
                threading.Event().wait(0.02); return fake(path, body)
            finally:
                with lock: active[0] -= 1
        e = ep.Embedder("http://x", 101, 102, concurrency=2, post=slow)
        threads = [threading.Thread(target=e.embed, args=([f"t {i}"],)) for i in range(8)]
        [t.start() for t in threads]; [t.join() for t in threads]
        self.assertLessEqual(peak[0], 2)

    def test_overfull_pacing_queue_refuses_instead_of_sleeping_past_the_client(self):
        e = ep.Embedder("http://x", 101, 102, post=FakeBackend(), batch_rate=10.0, max_wait=1.0)
        e.pace(15)  # reserves 1.5 s
        before = e.next_free
        with self.assertRaises(ep.Busy):
            e.pace(15)  # would wait 1.5 s > 1.0 s
        self.assertEqual(e.next_free, before, "a refused batch reserves nothing")
        self.assertEqual(e.pace(2), 0.0)  # queries still pass
        self.assertEqual(e.metrics["busy_refused_batches_total"], 1)

    def test_query_is_never_blocked_by_batches_holding_slots(self):
        release, entered = threading.Event(), threading.Semaphore(0)
        fake = FakeBackend()
        def slow(path, body, timeout=60):
            if path == "/v1/embeddings" and len(body["input"]) > ep.INTERACTIVE_WINDOWS:
                entered.release(); release.wait(5)
            return fake(path, body)
        e = ep.Embedder("http://x", 101, 102, concurrency=2, post=slow, batch_rate=0)
        batches = [threading.Thread(target=e.embed, args=([f"b{j} {i}" for i in range(12)],)) for j in range(3)]
        [t.start() for t in batches]
        self.assertTrue(entered.acquire(timeout=2))
        started = ep.time.monotonic()
        self.assertEqual(len(e.embed(["recall query"])), 1)
        self.assertLess(ep.time.monotonic() - started, 1.0, "query must not wait for batch slots")
        release.set(); [t.join() for t in batches]

if __name__ == "__main__":
    unittest.main()
