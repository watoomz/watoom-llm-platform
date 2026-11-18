"""T-0055 item 3: a `--heights` png is only as good as the moment it was fetched; this gives tools a way to notice it is stale.

write_fingerprint(heights_path, raw, landscape): called by ue_heights_fetch.py right after it saves the png. Writes
`<heights_path>.fingerprint.json` with the raw heights' sha256, shape, landscape label and the UTC fetch time -- nothing
that needs the editor to verify later, so it works even for a consumer with no rig access of its own (unreal_lake_smooth.py).

check_sidecar(heights_path): for a consumer with no live rig access. Reads the sidecar next to heights_path, if any, and
compares its sha256 to the heights file on disk now. Returns (status, detail):
  "missing" -- no sidecar; can't tell (an older heights_fetch, or hand-made input) -- not itself an error.
  "stale"   -- sha256 differs from what the sidecar recorded: this is not the file ue_heights_fetch.py produced (wrong
              file, or edited/truncated since) -- a real correctness problem, the caller should refuse.
  "ok"      -- matches; also returns the recorded fetchedAt so the caller can report the fingerprint's age.

check_live(call, raw, landscape, px=None): for a consumer that already holds a transport (ue_stray_check.py,
ue_foliage_buried.py). Re-reads a handful of sample pixels (corners, centre, by default) from the live landscape via
landscape.get_height_region and compares them to the same pixels in `raw`. `call` is (cat, meth, args, timeout, what) ->
parsed dict (as ue_foliage_buried.call / ue_stray_check.j+failed already provide). Returns a list of mismatches
{"x", "y", "heights_png": v, "live": v}; empty means fresh. Each sample is a single-vertex region (cheap, read-only).
"""
import hashlib
import json
import os
from datetime import datetime, timezone


def _sidecar_path(heights_path):
    return heights_path + ".fingerprint.json"


def write_fingerprint(heights_path, raw, landscape):
    fp = {
        "sha256": hashlib.sha256(raw.tobytes()).hexdigest(),
        "shape": list(raw.shape),
        "landscape": landscape,
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
    }
    with open(_sidecar_path(heights_path), "w") as f:
        json.dump(fp, f)
    return fp


def check_sidecar(heights_path):
    path = _sidecar_path(heights_path)
    if not os.path.exists(path):
        return "missing", None
    fp = json.load(open(path))
    from PIL import Image
    import numpy as np
    actual = hashlib.sha256(np.asarray(Image.open(heights_path)).tobytes()).hexdigest()
    if actual != fp.get("sha256"):
        return "stale", fp
    return "ok", fp


def default_samples(shape):
    n, m = shape
    pts = {(0, 0), (m - 1, 0), (0, n - 1), (m - 1, n - 1), (m // 2, n // 2)}
    return sorted(pts)


def check_live(call, raw, landscape, px=None):
    mismatches = []
    for x, y in px or default_samples(raw.shape):
        d = call("landscape", "get_height_region", {"actorLabel": landscape, "region": {"minX": x, "minY": y, "maxX": x, "maxY": y}}, 60,
                  "freshness check %d,%d" % (x, y))
        live = d.get("heights", [None])[0]
        want = int(raw[y, x])
        if live != want:
            mismatches.append({"x": x, "y": y, "heights_png": want, "live": live})
    return mismatches
