"""Use the existing durable native admission contract; never alter networking."""

import contextlib, json, os, subprocess
from pathlib import Path
from maintenance_guard import Maintenance
import release_guard
from admission_errors import AdmissionBusy


def check_native_idle(api):
    # Read-only preflight: nothing is fenced or started yet, so a dropped exec/HTTP
    # transport keeps the image queued instead of failing it. Contract errors still fail.
    try:
        status = api.request("/api/session/deployment-guard").get("data", {})
        active = (
            None if status.get("held") or status.get("leases", 0) else api.request("/api/session/active").get("data")
        )
    except subprocess.TimeoutExpired:
        raise AdmissionBusy("Native admission probe timed out; image remains queued until idle")
    except release_guard.UnsafeRelease as error:
        if not str(error).startswith("Maintenance command failed"):
            raise
        raise AdmissionBusy("Native admission probe transport failed; image remains queued until idle")
    if status.get("version") != 1 or status.get("supported") is not True:
        raise release_guard.UnsafeRelease("Verified native admission is unavailable")
    if status.get("held") or status.get("leases", 0) or active:
        raise AdmissionBusy("Native work or maintenance is active; image remains queued until idle")


@contextlib.contextmanager
def hold(evidence, clearance):
    evidence = Path(evidence)
    evidence.mkdir(parents=True, exist_ok=True, mode=0o700)
    api = Maintenance("watoom-code", "watoom-code", evidence, True, True)

    def save(owner):
        with (evidence / "native-owner.json").open("w") as f:
            json.dump({"owner": owner}, f)
            f.flush()
            os.fsync(f.fileno())

    def check():
        release_guard.durable_clearance(Path("/data/ai/watoom-code/application.sqlite"))
        clearance()

    check_native_idle(api)
    try:
        token = release_guard.acquire(api.request, api.request, save, check)
    except Exception:
        # Only a proven new native execution with no held fence is a safe admission race.
        status = api.request("/api/session/deployment-guard").get("data", {})
        if status.get("held") is False and api.request("/api/session/active").get("data"):
            raise AdmissionBusy("Native work won admission; image remains queued until idle")
        raise
    try:
        yield
    finally:
        clearance()  # An uncertain GPU outcome retains the durable native fence for recovery.
        release_guard.release(api.request, api.request, token)
