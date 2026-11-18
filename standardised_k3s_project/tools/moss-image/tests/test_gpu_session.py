import pathlib
import sys
import threading
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import gpu_session as gs  # noqa: E402


class Client:
    def __init__(self, phase="qwen-ready", fail=None):
        self.calls, self.phase, self.fail = [], phase, fail

    def call(self, action, **kw):
        self.calls.append((action, kw))
        if self.fail == action:
            raise RuntimeError("boom")
        if action == "status":
            return {"phase": self.phase, "owner": None, "uncertain": False, "generation": 3}
        if action == "begin":
            return {"generation": 4}
        return {"ok": True}


def make(client, free=20000, quiet_ok=True, **kw):
    q = gs.QuietTracker(lambda: not quiet_ok, interval=0.01)
    stopped = []
    t0 = time.monotonic()
    s = gs.GpuSession(client, q, lambda: stopped.append(1), lambda: free, quiet_required=0.0 if quiet_ok else 999,
                      idle_timeout=kw.pop("idle_timeout", 0.3), max_session=kw.pop("max_session", 30), poll=0.01, release_wait=0.3, last_used=lambda: t0, **kw)
    return s, stopped


def wait_for(fn, t=5):
    end = time.time() + t
    while time.time() < end:
        if fn():
            return True
        time.sleep(0.01)
    return False


class SessionTests(unittest.TestCase):
    def test_idle_session_yields_to_llm_demand(self):
        c = Client()
        hits = iter([False, False, True])  # first call is the baseline at session start
        s, stopped = make(c, idle_timeout=999, demand=lambda: next(hits, False))
        s.start()
        self.assertTrue(wait_for(lambda: s.state == "idle" and s.detail == "LLM restored"))
        self.assertEqual(1, len(stopped))
        self.assertIn("restore", [a for a, _ in c.calls])

    def test_demand_waits_for_a_running_job(self):
        c = Client()
        busy = {"v": True}
        s, stopped = make(c, idle_timeout=999, demand=lambda: True, busy=lambda: busy["v"])
        s.start()
        self.assertTrue(wait_for(s.active))
        time.sleep(0.15)
        self.assertTrue(s.active() and not stopped)  # busy: do not interrupt generation
        busy["v"] = False
        self.assertTrue(wait_for(lambda: s.state == "idle" and bool(stopped)))

    def test_demand_watcher_counts_only_new_503s(self):
        import io, json as j, unittest.mock as m
        seq = iter([3, 3, 4, 2])
        def fake(url, timeout=0):
            return io.BytesIO(j.dumps({"levels": {"low": {"http_503": next(seq)}, "high": {"http_503": 0}}}).encode())
        w = gs.DemandWatcher("http://x/performance")
        with m.patch("urllib.request.urlopen", fake):
            self.assertEqual([False, False, True, False], [w.poll() for _ in range(4)])
        self.assertFalse(gs.DemandWatcher("http://127.0.0.1:1/x", timeout=0.2).poll())

    def test_full_cycle_order(self):
        c = Client()
        s, stopped = make(c)
        s.start()
        self.assertTrue(wait_for(s.active))
        self.assertEqual([a for a, _ in c.calls][:3], ["status", "begin", "park-cpu"])
        self.assertTrue(wait_for(lambda: s.state == "idle"))  # idle timeout ends it
        acts = [a for a, _ in c.calls]
        self.assertEqual(acts[-2:], ["restore", "status"])
        self.assertEqual(stopped, [1])
        self.assertEqual(c.calls[-2][1], {"job": "moss-image", "generation": 4})

    def test_not_quiet_never_calls_controller(self):
        c = Client()
        s, _ = make(c, quiet_ok=False)
        s.start()
        time.sleep(0.2)
        self.assertEqual(s.state, "waiting")
        self.assertEqual(c.calls, [])
        s.end()
        self.assertTrue(wait_for(lambda: s.state == "idle"))
        self.assertEqual(c.calls, [])

    def test_native_probe_failure_fails_closed(self):
        q = gs.QuietTracker(lambda: 1 / 0)
        q.sample()
        self.assertEqual(q.quiet_for(), 0.0)
        self.assertIn("ZeroDivisionError", q.error)

    def test_controller_busy_refuses(self):
        c = Client(phase="mesh-active")
        s, _ = make(c)
        s.start()
        self.assertTrue(wait_for(lambda: s.state == "idle"))
        self.assertNotIn("begin", [a for a, _ in c.calls])
        self.assertIn("not idle", s.detail)

    def test_park_failure_restores_and_does_not_retry(self):
        c = Client(fail="park-cpu")
        s, _ = make(c)
        s.start()
        self.assertTrue(wait_for(lambda: s.state in ("idle", "error")))
        acts = [a for a, _ in c.calls]
        self.assertEqual(acts.count("begin"), 1)
        self.assertIn("restore", acts)

    def test_restore_failure_latches_error(self):
        c = Client(fail="restore")
        s, _ = make(c)
        s.start()
        self.assertTrue(wait_for(lambda: s.state == "error", 8))
        with self.assertRaises(gs.SessionError):
            s.start()
        self.assertEqual([a for a, _ in c.calls].count("begin"), 1)

    def test_insufficient_vram_after_park_restores(self):
        c = Client()
        s, _ = make(c, free=1000)
        s.start()
        self.assertTrue(wait_for(lambda: "restore" in [a for a, _ in c.calls]))

    def test_idle_clock_starts_at_session_start_not_service_start(self):
        c = Client()
        q = gs.QuietTracker(lambda: False, interval=0.01)
        old = time.monotonic() - 10_000  # service started long ago, nothing generated yet
        s = gs.GpuSession(c, q, lambda: None, lambda: 20000, quiet_required=0.0, idle_timeout=5.0, max_session=30,
                          poll=0.01, release_wait=0.3, last_used=lambda: old)
        s.start()
        self.assertTrue(wait_for(s.active))
        time.sleep(0.3)
        self.assertTrue(s.active())  # must not have ended immediately
        s.end()
        self.assertTrue(wait_for(lambda: s.state == "idle"))

    def test_end_button_releases(self):
        c = Client()
        s, stopped = make(c, idle_timeout=999)
        s.start()
        self.assertTrue(wait_for(s.active))
        s.end()
        self.assertTrue(wait_for(lambda: s.state == "idle"))
        self.assertEqual(stopped, [1])


if __name__ == "__main__":
    unittest.main()
