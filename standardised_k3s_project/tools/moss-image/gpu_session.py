"""GPU session for the MOSS Image service, mediated by the WatooM GPU ownership controller.

The service never touches Kubernetes or scales anything itself. A session is: wait until WatooM Code has been
quiet, `begin` (durable ownership) -> `park-cpu` (controller stops the primary LLM, starts no other deployment)
-> engine runs -> stop engine, confirm VRAM released -> `restore` (controller brings the LLM back and verifies it).
Safety rules copied from the Mesh/game-worker pattern: one stable job id ("moss-image"), never a second `begin`
after an uncertain outcome, recovery is never claimed by this service.
"""
import json
import threading
import time
import urllib.request

JOB = "moss-image"
STATES = ("idle", "waiting", "starting", "active", "ending", "error")


class SessionError(Exception):
    pass


class QuietTracker:
    """Samples `active_fn()` (True while WatooM Code work is active) and reports continuous quiet time.
    Unknown (sampler failing, or just started) counts as NOT quiet, so a restart waits the full quiet period."""

    def __init__(self, active_fn, interval=30.0, clock=time.monotonic):
        self.active_fn, self.interval, self.clock = active_fn, interval, clock
        self.quiet_since = None
        self.error = None

    def sample(self):
        try:
            busy = bool(self.active_fn())
            self.error = None
        except Exception as exc:  # fail closed: unknown == busy
            busy, self.error = True, "%s: %s" % (type(exc).__name__, exc)
        if busy:
            self.quiet_since = None
        elif self.quiet_since is None:
            self.quiet_since = self.clock()

    def quiet_for(self):
        return 0.0 if self.quiet_since is None else self.clock() - self.quiet_since


class DemandWatcher:
    """True when the LLM router has refused new requests since the last poll.

    While a MOSS session holds the GPU no LLM is loaded, so any chat request fails with 503; a rise in the router's
    rolling 503 count is therefore a request for the LLM. Reads only /performance. Errors mean "no demand" (never yield on
    guesswork); the first poll just records the baseline."""

    def __init__(self, url, timeout=3.0):
        self.url, self.timeout, self.last = url, timeout, None

    def poll(self):
        try:
            with urllib.request.urlopen(self.url, timeout=self.timeout) as r:
                levels = json.load(r)["levels"]
            n = sum(int(v.get("http_503") or 0) for v in levels.values())
        except Exception:
            return False
        prev, self.last = self.last, n
        return prev is not None and n > prev


class GpuSession:
    def __init__(self, client, quiet, stop_engine, free_mib, *, min_free_mib=6144, release_max_mib=1500,
                 quiet_required=1800.0, idle_timeout=600.0, max_session=7200.0, busy=lambda: False, demand=lambda: False,
                 last_used=time.monotonic, sleep=time.sleep, clock=time.monotonic, poll=5.0, release_wait=60.0):
        self.client, self.quiet, self.stop_engine, self.free_mib = client, quiet, stop_engine, free_mib
        self.min_free_mib, self.release_max_mib = min_free_mib, release_max_mib
        self.quiet_required, self.idle_timeout, self.max_session = quiet_required, idle_timeout, max_session
        self.release_wait = release_wait
        self.demand, self.llm_wanted = demand, False
        self.busy, self.last_used, self.sleep, self.clock, self.poll = busy, last_used, sleep, clock, poll
        self.mu = threading.Lock()
        self.state, self.detail, self.generation = "idle", "", None
        self.started_at = None
        self.want_end = threading.Event()
        self.stopping = threading.Event()
        self.thread = None

    # -- API
    def snapshot(self):
        left = None
        if self.state == "active" and not self.busy():
            left = max(0.0, self.idle_timeout - (self.clock() - max(self.last_used(), self.started_at)))
        return {"state": self.state, "detail": self.detail, "generation": self.generation,
                "quiet_seconds": round(self.quiet.quiet_for()), "quiet_required": self.quiet_required,
                "idle_timeout": self.idle_timeout, "idle_seconds_left": None if left is None else round(left),
                "native_check_error": self.quiet.error}

    def active(self):
        return self.state == "active"

    def start(self):
        with self.mu:
            if self.state in ("waiting", "starting", "active", "ending"):
                return self.snapshot()
            if self.state == "error":
                raise SessionError("session is in an error state; the GPU controller must be reconciled by the operator")
            self.state, self.detail = "waiting", "waiting for WatooM Code to be quiet"
            self.want_end.clear()
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()
        return self.snapshot()

    def end(self):
        self.want_end.set()
        return self.snapshot()

    def shutdown(self):
        self.stopping.set()
        self.want_end.set()
        if self.thread:
            self.thread.join(timeout=30)

    # -- lifecycle (single thread per session)
    def _wait(self, secs):
        end = self.clock() + secs
        while self.clock() < end and not self.want_end.is_set() and not self.stopping.is_set():
            self.sleep(min(self.poll, 0.2) if self.poll < 1 else 1.0)

    def _run(self):
        try:
            if not self._await_quiet():
                self.state, self.detail = "idle", "cancelled before the GPU was taken"
                return
            self._acquire()
            self._hold()
        except SessionError as exc:
            if self.state != "error":
                self.state, self.detail = "idle", str(exc)
        except Exception as exc:
            self._fail("%s: %s" % (type(exc).__name__, exc))

    def _await_quiet(self):
        while not self.want_end.is_set():
            self.quiet.sample()
            if self.quiet.quiet_for() >= self.quiet_required:
                return True
            self.detail = "waiting for WatooM Code to be quiet (%ds of %ds)" % (self.quiet.quiet_for(), self.quiet_required)
            self._wait(self.poll)
        return False

    def _acquire(self):
        self.state, self.detail = "starting", "asking the GPU controller to pause the LLM"
        st = self.client.call("status")
        if st.get("phase") != "qwen-ready" or st.get("owner") or st.get("uncertain"):
            raise SessionError("GPU controller is not idle (phase=%s owner=%s uncertain=%s)"
                               % (st.get("phase"), st.get("owner"), st.get("uncertain")))
        self.generation = self.client.call("begin", job=JOB)["generation"]
        try:
            self.client.call("park-cpu", job=JOB, generation=self.generation)
            free = self.free_mib()
            if free is None or free < self.min_free_mib:
                raise SessionError("LLM paused but only %s MiB VRAM is free (need %d)" % (free, self.min_free_mib))
        except BaseException as exc:
            self.state, self.detail = "ending", "start failed: %s; restoring the LLM" % exc
            self._restore()
            raise SessionError("session start failed: %s" % exc)
        self.started_at = self.clock()
        self.llm_wanted = False
        self.demand()  # baseline: only requests made from now on count as a request for the LLM
        self.state, self.detail = "active", "GPU session active"

    def _hold(self):
        while not self.want_end.is_set():
            now = self.clock()
            if now - self.started_at > self.max_session:
                self.detail = "maximum session length reached"
                break
            if not self.busy() and now - max(self.last_used(), self.started_at) > self.idle_timeout:
                self.detail = "idle timeout"
                break
            self.llm_wanted = self.demand() or self.llm_wanted  # latched: a running job finishes first
            if self.llm_wanted and not self.busy():
                self.detail = "LLM requested while MOSS was idle; returning the GPU to Qwen"
                break
            self._wait(self.poll)
        self.state = "ending"
        self.detail = self.detail if self.detail != "GPU session active" else "ending"
        self._release()

    def _release(self):
        try:
            self.stop_engine()
        except Exception as exc:
            self._fail("engine did not stop cleanly: %s" % exc)
            return
        self._restore()

    def _restore(self):
        """Wait for VRAM to be released, then ask the controller to restore the LLM. Never retried with a new job."""
        try:
            deadline = self.clock() + self.release_wait
            while True:
                used_ok = self.free_mib()
                if used_ok is not None and used_ok >= self.min_free_mib:
                    break
                if self.clock() > deadline:
                    break
                self.sleep(1.0)
            self.client.call("restore", job=JOB, generation=self.generation)
            st = self.client.call("status")
            if st.get("phase") != "qwen-ready" or st.get("owner") or st.get("uncertain"):
                raise SessionError("controller did not return to qwen-ready (phase=%s)" % st.get("phase"))
        except Exception as exc:
            self._fail("restore not confirmed: %s" % exc)
            raise SessionError("restore not confirmed: %s" % exc)
        self.state, self.detail, self.generation = "idle", "LLM restored", None

    def _fail(self, message):
        self.state, self.detail = "error", message + " (operator: reconcile the GPU controller; the service will not retry)"
