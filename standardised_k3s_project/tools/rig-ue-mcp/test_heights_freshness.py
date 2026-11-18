import json
import os
import tempfile
import unittest

import numpy as np
from PIL import Image

import heights_freshness as hfr


class Fingerprint(unittest.TestCase):
    def test_write_then_check_sidecar_matches(self):
        d = tempfile.mkdtemp()
        raw = np.array([[1, 2], [3, 4]], np.uint16)
        path = os.path.join(d, "h.png")
        Image.fromarray(raw).save(path)
        fp = hfr.write_fingerprint(path, raw, "ZAS_Landscape")
        self.assertEqual(fp["landscape"], "ZAS_Landscape")
        status, got = hfr.check_sidecar(path)
        self.assertEqual(status, "ok")
        self.assertEqual(got["sha256"], fp["sha256"])

    def test_missing_sidecar_is_reported_not_an_error(self):
        d = tempfile.mkdtemp()
        raw = np.array([[1, 2], [3, 4]], np.uint16)
        path = os.path.join(d, "h.png")
        Image.fromarray(raw).save(path)
        status, detail = hfr.check_sidecar(path)
        self.assertEqual(status, "missing")
        self.assertIsNone(detail)

    def test_an_edited_heights_file_fails_the_sidecar_check(self):
        d = tempfile.mkdtemp()
        raw = np.array([[1, 2], [3, 4]], np.uint16)
        path = os.path.join(d, "h.png")
        Image.fromarray(raw).save(path)
        hfr.write_fingerprint(path, raw, "ZAS_Landscape")
        Image.fromarray(raw + 1).save(path)        # heights changed after the fingerprint was recorded
        status, fp = hfr.check_sidecar(path)
        self.assertEqual(status, "stale")
        self.assertIsNotNone(fp)


class LiveCheck(unittest.TestCase):
    def fake_call(self, live):
        """live: {(x, y): value}; returns a `call` matching heights_freshness.check_live's contract."""
        def call(cat, meth, args, timeout, what):
            self.assertEqual((cat, meth), ("landscape", "get_height_region"))
            r = args["region"]
            self.assertEqual((r["minX"], r["maxX"], r["minY"], r["maxY"]), (r["minX"], r["minX"], r["minY"], r["minY"]))
            return {"heights": [live[(r["minX"], r["minY"])]]}
        return call

    def test_matching_live_samples_report_no_mismatch(self):
        raw = np.array([[1, 2], [3, 4]], np.uint16)
        pts = hfr.default_samples(raw.shape)
        live = {(x, y): int(raw[y, x]) for x, y in pts}
        self.assertEqual(hfr.check_live(self.fake_call(live), raw, "ZAS_Landscape"), [])

    def test_a_changed_live_pixel_is_reported_as_a_mismatch(self):
        raw = np.array([[1, 2], [3, 4]], np.uint16)
        pts = hfr.default_samples(raw.shape)
        live = {(x, y): int(raw[y, x]) for x, y in pts}
        cx, cy = pts[0]
        live[(cx, cy)] = int(raw[cy, cx]) + 500            # the landscape moved since the png was fetched
        mismatches = hfr.check_live(self.fake_call(live), raw, "ZAS_Landscape")
        self.assertEqual(len(mismatches), 1)
        self.assertEqual((mismatches[0]["x"], mismatches[0]["y"]), (cx, cy))

    def test_default_samples_are_corners_and_centre_deduplicated_for_a_1x1_map(self):
        self.assertEqual(hfr.default_samples((1, 1)), [(0, 0)])


if __name__ == "__main__":
    unittest.main()
