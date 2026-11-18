#!/usr/bin/env python3
"""Run the phases of a helper's calls json (unreal_coast.py, unreal_creek_profile.py, unreal_ocean_depth.py ...) through the ue-mcp route.

  ue_run_phases.py calls.json [--phase heights] [--start 0] [--max-load 8] [--dry-run]

calls.json is {"phases": [{"name": ..., "calls": [["category.method", {args}], ...]}]}. Calls run one after another in one session;
before each call it waits while the lab server's 1-minute load average is above --max-load (the server is shared with the models),
and it stops at the first failed call (prints which index to --start from again). stdlib only; reuses ue_route.SshTransport.

Water-layer compensation (T-0049, 2026-11-18): every terrain helper computes its heights from the VISIBLE heights (ue_heights_fetch.py)
and its `landscape.set_height_region` calls carry no editLayer, so they land in the base `Layer`. Where the additive `Water` layer holds
an offset (a carved lake bed), writing a visible height into the base applies that offset a second time: the bed sinks, and because a
call rewrites its whole tile, even untouched vertices around a lake drop. Before each such call this tool reads the Water layer of the
same region and writes base = clamp(height - (water - 32768)) instead, so the visible result is the height the helper asked for.
--no-water-compensation writes the heights as given (only for a calls json that really holds base-layer heights).
"""
import argparse
import base64
import json
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_route  # noqa: E402

WATER_MID = 32768  # the Water edit layer's neutral value (ue_lake_as_river.WATER_LAYER_MID)


def load1():
    return float(open("/proc/loadavg").read().split()[0])


def is_base_height_write(head, args):
    return head == "landscape.set_height_region" and args.get("editLayer") in (None, "Layer") \
        and args.get("heightSpace", "raw") == "raw" and ("heights" in args or "heightsBase64" in args)


def heights_of(args):
    if "heights" in args:
        return list(args["heights"])
    data = base64.b64decode(args["heightsBase64"])
    return list(struct.unpack("<%dH" % (len(data) // 2), data))


def compensate(args, water):
    """Return (new args, vertices changed): the requested visible heights turned into base-layer values under `water`."""
    heights = heights_of(args)
    if len(heights) != len(water):
        raise ValueError("Water read has %d values for %d heights" % (len(water), len(heights)))
    base = [max(0, min(65535, h - (w - WATER_MID))) for h, w in zip(heights, water)]
    changed = sum(1 for h, b in zip(heights, base) if h != b)
    out = dict(args)
    if "heights" in args:
        out["heights"] = base
    else:
        out["heightsBase64"] = base64.b64encode(struct.pack("<%dH" % len(base), *base)).decode()
    return out, changed


def read_water(t, args):
    target = {"actorLabel": args["actorLabel"]} if "actorLabel" in args else {"actorPath": args["actorPath"]}
    text = t.call("landscape", "get_height_region", dict(target, region=args["region"], editLayer="Water"), 300)
    if ue_route.reply_failed(text, getattr(t, "is_error", False)) or "{" not in text:
        raise RuntimeError("could not read the Water layer for %r: %s" % (args["region"], text[:200]))
    return json.loads(text[text.index("{"):])["heights"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("calls")
    ap.add_argument("--phase", default=None)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--max-load", type=float, default=8.0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-water-compensation", action="store_true", help="write base-layer heights as given (see above)")
    ap.add_argument("--host", default="10.99.1.44")
    ap.add_argument("--port", type=int, default=2224)
    ap.add_argument("--user", default="uemcp")
    ap.add_argument("--key-dir", default=ue_route.DEFAULT_KEY_DIR)
    a = ap.parse_args(argv)
    phases = [p for p in json.load(open(a.calls))["phases"] if a.phase in (None, p["name"])]
    calls = [(p["name"], i, c) for p in phases for i, c in enumerate(p["calls"])][a.start:]
    print("%d calls in %s" % (len(calls), ", ".join(p["name"] for p in phases)))
    if a.dry_run:
        return 0
    t = ue_route.SshTransport(ue_route.ssh_command(a.host, a.port, a.user, a.key_dir))
    try:
        for k, (name, i, (head, args)) in enumerate(calls, a.start):
            while load1() > a.max_load:
                time.sleep(5)
            cat, meth = head.split(".", 1)
            note = ""
            if not a.no_water_compensation and is_base_height_write(head, args):
                try:
                    args, changed = compensate(args, read_water(t, args))
                except (RuntimeError, ValueError, KeyError) as e:
                    print("[%d] %s %s FAILED before writing: %s" % (k, name, head, e), flush=True)
                    print("stopped: rerun with --start %d" % k)
                    return 1
                if changed:
                    note = " (%d vertices under a Water-layer offset compensated)" % changed
            text = t.call(cat, meth, args, 300)
            ok = not ue_route.reply_failed(text, getattr(t, "is_error", False)) and "Error [" not in text[:60]
            print("[%d] %s %s %s%s" % (k, name, head, "ok" if ok else "FAILED: " + text[:300], note), flush=True)
            if not ok:
                print("stopped: rerun with --start %d" % k)
                return 1
    finally:
        t.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
