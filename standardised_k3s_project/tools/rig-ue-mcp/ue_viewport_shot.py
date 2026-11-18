#!/usr/bin/env python3
"""Capture the real editor viewport on the rig and pull the PNG back.

Why: `editor.capture_scene_png` ignores lighting and material edits (a sun change from 6 to 0.5 gave an identical
image), so it cannot judge them. `editor.capture_screenshot` renders the editor viewport itself, but writes the file
on the rig (`<project>/Saved/Screenshots/<name>.png`) and replies before it exists, so this tool then copies it over
scp with the key of the `migrate` maintenance account (an ADMIN account on the rig, created with
Add-RigMaintenanceAccount.ps1 -Admin; it is not a read-only key, so this tool only ever runs one scp download with it).

Usage:
  ue_viewport_shot.py OUT.png [--camera X Y Z PITCH YAW] [--key PATH] [--rig-dir "F:/.../Saved/Screenshots"]
  ue_viewport_shot.py OUT.png --around X Y Z RADIUS     the verification set: OUT_current.png (owner's view, unmoved), OUT_top,
                                                        OUT_east/north/west/south, OUT_close_low, OUT_far; the owner's view is
                                                        restored afterwards; exit 1 if any view failed
It captures whatever the viewport shows; --camera X Y Z PITCH YAW moves it first (the owner's view is not restored,
so read it with editor.get_viewport_state before and put it back afterwards).
The rig file path is the `filename` the capture reply reports; --rig-dir is only used when the reply has none (or a
bare file name). It stops with an error when the camera move or the capture call fails, or when no path is known.
The editor's CPU throttle (bThrottleCPUWhenNotForeground) is switched off for the capture and restored afterwards.

Verification practice (T-0049, 2026-11-18): take several captures from DIFFERENT angles AND distances before calling a water
body (or any carve) visually confirmed, not just one fixed camera. A single angle can hide a real defect -- the WaterZone
registration bug below looked like a clean, well-formed lake from one angle (water filling the circle correctly) and only
revealed itself as two disconnected water planes at different heights from a different angle/distance. See
[[waterbody-wrong-registration-square-unclipped]] in the watoom-texture-layering knowledge base for the specific symptom
and fix. If this tool itself starts failing at the `scp` copy step (`Connection closed`) across several retries while the
normal ue_route.py route still answers fine, that is the `migrate` maintenance account specifically, not the editor bridge
-- stop and report it rather than retrying blindly or trying to read its key file directly (that account is ADMIN-tier).
"""
import argparse
import base64
import json
import math
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_route  # noqa: E402

DEFAULT_KEY = "/data/ai/rig-migrate-ssh/key"
INLINE_EDGE = 1920   # longest edge of the inline image the bridge returns (it scales larger captures down)


def _call(transport, ident, category, method, args, wait=120):
    transport._send({"jsonrpc": "2.0", "id": ident, "method": "tools/call", "params": {
        "name": "tools", "arguments": {"action": "call", "category": category, "method": method, "args": args}}})
    return transport._wait(ident, wait)


def _text(reply):
    out = []
    for block in (reply or {}).get("result", {}).get("content", []):
        if block.get("type") == "text":
            out.append(block["text"])
    return "\n".join(out)


def remote_path(reported, rig_dir, name):
    """scp path of the screenshot on the rig: the path the reply reported, else <rig_dir>/<name>. `F:/x` becomes `/F:/x`."""
    path = (reported or "").replace("\\", "/")
    absolute = path.startswith("/") or (len(path) > 1 and path[1] == ":")
    if not absolute:
        if not rig_dir:
            raise SystemExit("capture_screenshot did not report where it wrote the file: pass --rig-dir \"F:/.../Saved/Screenshots\"")
        path = rig_dir.replace("\\", "/").rstrip("/") + "/" + (path or name)
    return "/" + path if len(path) > 1 and path[1] == ":" else path


def capture(out_path, camera=None, key=DEFAULT_KEY, ue=("10.99.1.44", 2224, "uemcp"), ssh=("migrate", "10.99.1.44", 2224),
            rig_dir=None, retries=20, transport=None, run=subprocess.run, sleep=time.sleep):
    """transport / run / sleep are injectable for the unit test (a fake route session and a fake scp runner)."""
    if transport is None:
        transport = ue_route.SshTransport(ue_route.ssh_command(ue[0], ue[1], ue[2], ue_route.DEFAULT_KEY_DIR))
    perf = "/Script/UnrealEd.Default__EditorPerformanceSettings"
    was = None
    remote, error = "?", "no attempt was made"
    try:
        # an editor that is not the foreground window throttles and never renders, so the file would not appear
        got = _text(_call(transport, 598, "editor", "get_property", {"objectPath": perf, "propertyName": "bThrottleCPUWhenNotForeground"}))
        was = json.loads(got[got.index("{"):]).get("value") if "{" in got else None
        if was:
            _call(transport, 599, "editor", "set_property", {"objectPath": perf, "propertyName": "bThrottleCPUWhenNotForeground", "value": False})
            sleep(3)
        if camera:
            x, y, z, pitch, yaw = camera
            moved = _call(transport, 601, "editor", "set_viewport", {"location": {"x": x, "y": y, "z": z},
                                                                     "rotation": {"pitch": pitch, "yaw": yaw, "roll": 0}})
            if moved is None or ue_route.reply_failed(_text(moved), bool(moved.get("result", {}).get("isError")) or "error" in moved):
                raise SystemExit("editor.set_viewport failed, so the picture would show another view: %s" % (_text(moved)[:200] or moved))
            sleep(3)
        name = "vshot_%d.png" % int(time.time())
        # inline: the bridge returns the written PNG as an image content block over the normal uemcp route, so the scp
        # copy below (migrate account) is only the fallback when no image block comes back (T-0049: migrate was refusing
        # connections pre-auth while the route still worked).
        shot = _call(transport, 603, "editor", "capture_screenshot", {"filename": name, "inline": INLINE_EDGE})
        reply = _text(shot)
        if shot is None or ue_route.reply_failed(reply, bool(shot.get("result", {}).get("isError")) or "error" in shot):
            raise SystemExit("editor.capture_screenshot failed: %s" % (reply[:200] or shot))
        image = next((b for b in shot.get("result", {}).get("content", []) if b.get("type") == "image" and b.get("data")), None)
        if image:
            with open(out_path, "wb") as f:
                f.write(base64.b64decode(image["data"]))
            return out_path
        info = json.loads(reply[reply.index("{"):]) if "{" in reply else {}
        remote = remote_path(info.get("filename"), rig_dir, name)
        for attempt in range(retries):
            # the renderer writes the file on a later frame, so keep nudging the viewport while polling
            _call(transport, 700 + attempt, "editor", "redraw_viewport", {"allViewports": True}, wait=30)
            done = run(["scp", "-q", "-i", key, "-P", str(ssh[2]), "-o", "BatchMode=yes",
                        "%s@%s:%s" % (ssh[0], ssh[1], remote), out_path], capture_output=True, text=True)
            if done.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                return out_path
            error = (done.stderr or "").strip()
            sleep(2)
    finally:
        if was:
            _call(transport, 698, "editor", "set_property", {"objectPath": perf, "propertyName": "bThrottleCPUWhenNotForeground", "value": True})
        transport.close()
    raise SystemExit("could not copy %s: %s" % (remote, error))


def look_at(eye, target):
    """(pitch, yaw) in degrees for a camera at eye looking at target. UE: yaw 0 = +X, 90 = +Y; negative pitch looks down."""
    dx, dy, dz = target[0] - eye[0], target[1] - eye[1], target[2] - eye[2]
    return math.degrees(math.atan2(dz, math.hypot(dx, dy))), math.degrees(math.atan2(dy, dx))


def views_around(x, y, z, radius):
    """The standard verification set around a subject (centre x, y, z; size radius, all cm): straight down, four compass obliques,
    a close low shot at the edge and a far shot -- several angles AND distances, because one angle hid a broken lake (T-0049).
    Returns [(name, (x, y, z, pitch, yaw))]."""
    r = max(radius, 500.0)
    target = (x, y, z)
    out = [("top", (x, y, z + max(3.0 * r, 4000.0), -89.0, 0.0))]
    for name, ang in (("east", 0.0), ("north", 90.0), ("west", 180.0), ("south", 270.0)):
        d = max(2.5 * r, 3000.0)
        eye = (x + d * math.cos(math.radians(ang)), y + d * math.sin(math.radians(ang)), z + max(r, 1500.0))
        out.append((name, eye + look_at(eye, target)))
    d = max(1.2 * r, 1500.0)
    eye = (x - d * 0.7071, y - d * 0.7071, z + 400.0)
    out.append(("close_low", eye + look_at(eye, target)))
    d = max(6.0 * r, 10000.0)
    eye = (x, y - d, z + max(2.5 * r, 4000.0))
    out.append(("far", eye + look_at(eye, target)))
    return out


def shot_path(out, name):
    stem, ext = os.path.splitext(out)
    return "%s_%s%s" % (stem, name, ext or ".png")


def around(out, x, y, z, radius, key=DEFAULT_KEY, rig_dir=None, shoot=None, transport_factory=None):
    """Capture the owner's current view (unmoved) and every views_around() view, then put the owner's camera back.
    One failed view does not stop the rest. Returns (written paths, {name: error})."""
    shoot = shoot or (lambda path, cam: capture(path, cam, key, rig_dir=rig_dir))
    transport_factory = transport_factory or (lambda: ue_route.SshTransport(ue_route.ssh_command("10.99.1.44", 2224, "uemcp", ue_route.DEFAULT_KEY_DIR)))
    t = transport_factory()
    try:
        reply = t.call("editor", "get_viewport_state", {}, 60)
        state = json.loads(reply[reply.index("{"):])
    finally:
        t.close()
    written, failed = [], {}
    try:
        for name, cam in [("current", None)] + views_around(x, y, z, radius):
            try:
                written.append(shoot(shot_path(out, name), cam))
            except SystemExit as e:
                failed[name] = str(e)
    finally:
        t = transport_factory()
        try:
            t.call("editor", "set_viewport", {"location": state["location"], "rotation": state["rotation"]}, 60)
        finally:
            t.close()
    return written, failed


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--camera", nargs=5, type=float, metavar=("X", "Y", "Z", "PITCH", "YAW"),
                    help="move the viewport camera first (cm, degrees); the owner's view is not restored")
    ap.add_argument("--around", nargs=4, type=float, metavar=("X", "Y", "Z", "RADIUS"),
                    help="capture the owner's view plus top/compass/close/far views of this subject to OUT_<view>.png, then restore the owner's view")
    ap.add_argument("--key", default=DEFAULT_KEY)
    ap.add_argument("--rig-dir")
    args = ap.parse_args(argv)
    if args.around and args.camera:
        ap.error("--around and --camera are exclusive")
    if args.around:
        written, failed = around(args.out, *args.around, key=args.key, rig_dir=args.rig_dir)
        for p in written:
            print(p)
        for name, err in failed.items():
            print("FAILED %s: %s" % (name, err))
        return 1 if failed else 0
    print(capture(args.out, args.camera, args.key, rig_dir=args.rig_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
