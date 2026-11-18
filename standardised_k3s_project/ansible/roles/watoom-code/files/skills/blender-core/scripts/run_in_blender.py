#!/usr/bin/env python3
"""Run a skill script in headless Blender and print only its JSON result.

Host-side launcher (Python 3.11+, no bpy). Requires the pinned worker profile,
verified external memory boundary and a 300-second stage deadline.

Usage:
  python run_in_blender.py [--blend FILE] [--user-prefs] SCRIPT.py [-- script args]
  python run_in_blender.py --expr "import bpy; print(bpy.app.version_string)"
  python run_in_blender.py --which          # print the Blender path it would use
Exit code: 0 ok, 1 script error, 2 Blender not found.
"""
import json
import os
import subprocess
import sys

MARK = "@@JSON@@"


def find_blender():
    from worker_profile import descriptor,verify_binary
    profile=descriptor()
    exe=os.environ.get('BLENDER_EXE',profile['binary'])
    if not os.path.isfile(exe):
        return None
    verify_binary(exe)
    return exe


def option(args, name):
    """Value following a flag; None when the flag is absent."""
    if name not in args:
        return None
    i = args.index(name)
    if i + 1 >= len(args):
        raise SystemExit(json.dumps({"ok": False, "error": name + " needs a value"}))
    return args[i + 1]


def main():
    a = sys.argv[1:]
    rest = []
    if "--" in a:
        i = a.index("--")
        a, rest = a[:i], a[i + 1:]
    exe = find_blender()
    if not exe:
        print(json.dumps({"ok": False, "error": "Blender not found; set BLENDER_EXE"}))
        return 2
    if "--which" in a:
        print(exe)
        return 0
    from worker_profile import verify_external
    profile=verify_external()
    cmd = [exe, "-b", "-t", str(profile["threads"])]
    blend = option(a, "--blend")
    if blend:
        cmd.append(blend)
    if "--user-prefs" not in a:
        cmd.append("--factory-startup")
    cmd += ["--python-exit-code", "1"]
    expr = option(a, "--expr")
    if expr is not None:
        cmd += ["--python-expr", expr]
    else:
        scripts = [x for x in a if x.endswith(".py") and x != blend]
        if not scripts:
            print(__doc__)
            return 1
        cmd += ["-P", scripts[0]]
    cmd += ["--"] + rest
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=profile["stage_timeout_max"])
    except subprocess.TimeoutExpired:
        print(json.dumps({"ok": False, "error": "Blender exceeded the %ss stage deadline" % profile["stage_timeout_max"]}))
        return 1
    out = [ln[len(MARK):] for ln in p.stdout.splitlines() if ln.startswith(MARK)]
    if out:
        print("\n".join(out))
    elif "--expr" in a:
        # free-form expression: show stdout minus Blender banner noise
        noise = ("Blender ", "Read prefs", "Read blend", "Blender quit", "Color management")
        print("\n".join(ln for ln in p.stdout.splitlines() if ln and not ln.startswith(noise)))
    if p.returncode != 0 and not out:
        tail = (p.stderr or p.stdout).strip().splitlines()[-15:]
        print(json.dumps({"ok": False, "returncode": p.returncode, "log_tail": tail}))
    return 0 if p.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
