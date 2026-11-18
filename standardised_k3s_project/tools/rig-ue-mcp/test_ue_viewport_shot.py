"""ue_viewport_shot.capture with a fake route session and a fake scp runner (no rig, no network)."""
import json
import os
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_viewport_shot as vs


class FakeSession:
    """Implements the two SshTransport methods the tool uses (_send, _wait); answer(method, args) -> reply text, None = no reply."""

    def __init__(self, answer):
        self.answer, self.sent, self.replies, self.closed = answer, [], {}, False

    def _send(self, msg):
        a = msg["params"]["arguments"]
        self.sent.append((a["method"], a["args"]))
        text = self.answer(a["method"], a["args"])
        self.replies[msg["id"]] = None if text is None else {"result": {"content": [{"type": "text", "text": text}]}}

    def _wait(self, ident, timeout):
        return self.replies.get(ident)

    def close(self):
        self.closed = True

    def methods(self):
        return [m for m, _ in self.sent]


def answers(throttled=True, viewport='{"success": true}', filename="F:/Proj/Saved/Screenshots/vshot.png"):
    def f(method, args):
        if method == "get_property":
            return json.dumps({"value": throttled})
        if method == "set_viewport":
            return viewport
        if method == "capture_screenshot":
            return json.dumps({"success": True, "filename": filename} if filename else {"success": True})
        return '{"success": true}'
    return f


class Scp:
    """Fails `misses` times (the file is not written yet), then writes the PNG like scp would."""

    def __init__(self, misses=1):
        self.misses, self.cmds = misses, []

    def __call__(self, cmd, **kw):
        self.cmds.append(cmd)
        if len(self.cmds) <= self.misses:
            return types.SimpleNamespace(returncode=1, stderr="scp: no such file")
        open(cmd[-1], "wb").write(b"\x89PNG")
        return types.SimpleNamespace(returncode=0, stderr="")


class Capture(unittest.TestCase):
    def setUp(self):
        self.out = os.path.join(tempfile.mkdtemp(), "shot.png")

    def shoot(self, session, scp, **kw):
        return vs.capture(self.out, key="/k", transport=session, run=scp, sleep=lambda s: None, **kw)

    def test_moves_the_camera_captures_polls_and_pulls_the_reported_file(self):
        s, scp = FakeSession(answers()), Scp(misses=2)
        self.assertEqual(self.shoot(s, scp, camera=(1, 2, 3, -30, 90)), self.out)
        self.assertEqual(s.methods()[:5], ["get_property", "set_property", "set_viewport", "capture_screenshot", "redraw_viewport"])
        self.assertEqual(s.sent[2][1], {"location": {"x": 1, "y": 2, "z": 3}, "rotation": {"pitch": -30, "yaw": 90, "roll": 0}})
        self.assertEqual(len(scp.cmds), 3)
        self.assertEqual(scp.cmds[0][-2], "migrate@10.99.1.44:/F:/Proj/Saved/Screenshots/vshot.png")
        self.assertIn("BatchMode=yes", scp.cmds[0])
        self.assertEqual(scp.cmds[0][scp.cmds[0].index("-i") + 1], "/k")

    def test_an_inline_image_is_written_without_scp_and_the_throttle_is_still_restored(self):
        s = FakeSession(answers(throttled=True))
        orig = s._send

        def send(msg):
            orig(msg)
            if msg["params"]["arguments"]["method"] == "capture_screenshot":
                s.replies[msg["id"]]["result"]["content"].append({"type": "image", "mimeType": "image/png", "data": "iVBORw=="})
        s._send = send
        scp = Scp(0)
        self.assertEqual(self.shoot(s, scp), self.out)
        self.assertEqual(scp.cmds, [])
        with open(self.out, "rb") as f:
            self.assertEqual(f.read(), b"\x89PNG")
        self.assertEqual(s.sent[2][1]["inline"], vs.INLINE_EDGE)
        self.assertEqual(s.sent[-1], ("set_property", {"objectPath": "/Script/UnrealEd.Default__EditorPerformanceSettings",
                                                      "propertyName": "bThrottleCPUWhenNotForeground", "value": True}))

    def test_the_cpu_throttle_is_switched_off_and_always_restored(self):
        s = FakeSession(answers(throttled=True))
        self.shoot(s, Scp(0))
        flips = [a["value"] for m, a in s.sent if m == "set_property"]
        self.assertEqual(flips, [False, True])
        self.assertTrue(s.closed)
        s = FakeSession(answers(throttled=False))
        self.shoot(s, Scp(0))
        self.assertNotIn("set_property", s.methods())

    def test_a_failed_camera_move_stops_before_the_capture(self):
        for bad in ('{"success": false, "message": "no viewport"}', None):
            s, scp = FakeSession(answers(viewport=bad)), Scp(0)
            with self.assertRaises(SystemExit) as e:
                self.shoot(s, scp, camera=(1, 2, 3, -30, 90))
            self.assertIn("set_viewport", str(e.exception))
            self.assertNotIn("capture_screenshot", s.methods())
            self.assertEqual(scp.cmds, [])
            self.assertEqual([a["value"] for m, a in s.sent if m == "set_property"], [False, True])   # throttle restored on the way out
            self.assertTrue(s.closed)

    def test_a_reply_without_a_path_needs_rig_dir(self):
        with self.assertRaises(SystemExit) as e:
            self.shoot(FakeSession(answers(filename=None)), Scp(0))
        self.assertIn("--rig-dir", str(e.exception))
        scp = Scp(0)
        self.shoot(FakeSession(answers(filename=None)), scp, rig_dir="F:/Proj/Saved/Screenshots/")
        self.assertRegex(scp.cmds[0][-2], r"^migrate@10\.5\.1\.44:/F:/Proj/Saved/Screenshots/vshot_\d+\.png$")

    def test_a_file_that_never_appears_is_an_error_with_the_scp_message(self):
        s = FakeSession(answers())
        with self.assertRaises(SystemExit) as e:
            self.shoot(s, Scp(misses=99), retries=3)
        self.assertIn("/F:/Proj/Saved/Screenshots/vshot.png", str(e.exception))
        self.assertIn("no such file", str(e.exception))
        self.assertFalse(os.path.exists(self.out))

    def test_remote_path_forms(self):
        self.assertEqual(vs.remote_path("F:\\P\\Saved\\Screenshots\\a.png", None, "n.png"), "/F:/P/Saved/Screenshots/a.png")
        self.assertEqual(vs.remote_path("/srv/shots/a.png", None, "n.png"), "/srv/shots/a.png")
        self.assertEqual(vs.remote_path("a.png", "F:/P/Shots", "n.png"), "/F:/P/Shots/a.png")
        self.assertEqual(vs.remote_path(None, "F:/P/Shots/", "n.png"), "/F:/P/Shots/n.png")
        with self.assertRaises(SystemExit):
            vs.remote_path("a.png", None, "n.png")

    def test_the_dead_helper_is_gone(self):
        self.assertFalse(hasattr(vs, "_unused"))


class Around(unittest.TestCase):
    def test_every_view_looks_at_the_subject(self):
        import math
        x, y, z = 133922.2, 100764.6, 8860.0
        for name, (ex, ey, ez, pitch, yaw) in vs.views_around(x, y, z, 4043.0):
            if name == "top":
                self.assertLess(pitch, -80)
                continue
            # rebuild the view direction from pitch/yaw and check it passes within 1 cm of the subject
            d = math.dist((ex, ey, ez), (x, y, z))
            fx = math.cos(math.radians(pitch)) * math.cos(math.radians(yaw))
            fy = math.cos(math.radians(pitch)) * math.sin(math.radians(yaw))
            fz = math.sin(math.radians(pitch))
            self.assertAlmostEqual(ex + fx * d, x, delta=1.0, msg=name)
            self.assertAlmostEqual(ey + fy * d, y, delta=1.0, msg=name)
            self.assertAlmostEqual(ez + fz * d, z, delta=1.0, msg=name)
            self.assertLess(pitch, 0, msg=name)  # every view looks down at the water, never up from below it

    def test_several_angles_and_distances(self):
        views = dict(vs.views_around(0.0, 0.0, 0.0, 4000.0))
        self.assertTrue({"top", "east", "north", "west", "south", "close_low", "far"} <= set(views))
        dists = {n: (c[0] ** 2 + c[1] ** 2 + c[2] ** 2) ** 0.5 for n, c in views.items()}
        self.assertLess(dists["close_low"], dists["east"])
        self.assertLess(dists["east"], dists["far"])

    def test_around_shoots_the_owner_view_first_and_restores_it_even_when_a_view_fails(self):
        calls = []

        class T:
            def call(self, cat, meth, args, timeout):
                calls.append((meth, args))
                return json.dumps({"location": {"x": 1, "y": 2, "z": 3}, "rotation": {"pitch": -10, "yaw": 20, "roll": 0}})

            def close(self):
                pass

        shots = []

        def shoot(path, cam):
            shots.append((path, cam))
            if path.endswith("_north.png"):
                raise SystemExit("scp: Connection closed")
            return path

        written, failed = vs.around("/tmp/l3.png", 0, 0, 0, 4000, shoot=shoot, transport_factory=T)
        self.assertEqual(shots[0], ("/tmp/l3_current.png", None))  # the owner's view, unmoved
        self.assertEqual(list(failed), ["north"])
        self.assertEqual(len(written), len(shots) - 1)
        self.assertEqual(calls[-1], ("set_viewport", {"location": {"x": 1, "y": 2, "z": 3}, "rotation": {"pitch": -10, "yaw": 20, "roll": 0}}))


if __name__ == "__main__":
    unittest.main()
