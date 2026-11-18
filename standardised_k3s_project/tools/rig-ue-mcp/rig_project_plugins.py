#!/usr/bin/env python3
"""Keep the rig project's plugin switches (the .uproject "Plugins" list) as code: project_plugins.json is the source of truth.

  rig_project_plugins.py                 show the differences between project_plugins.json and the rig's .uproject
  rig_project_plugins.py --apply         write them (the project's editor must be stopped; a .uproject backup is kept)

Only the plugins NAMED in project_plugins.json are touched: each gets exactly the "Enabled" value given (missing entries are
added); every other entry of the .uproject is left as it is. Each entry carries a "why" so the next reader knows the reason.

Why (T-0061, 2026-11-19): every foliage add (bridge foliage.add_instances AND Python InstancedFoliageActor.add_instances, any
foliage type, any level) crashed the editor with an access violation in FoliageEdit. Bisected on the rig: with only the
experimental MeshPartitionWater plugin disabled the add works; enabled, it crashes. The fix lived in a hand-edited .uproject on
the rig, which no tool would restore; this keeps it in the repo. Uses the `migrate` maintenance account (admin; key only).
"""
import argparse
import base64
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rig_build_plugin as rb  # noqa: E402

UPROJECT = "F:/Documents/Unreal Projects/WatooM_UEMCP_Test/WatooM_UEMCP_Test.uproject"
SPEC = os.path.join(HERE, "project_plugins.json")


def wanted(spec):
    return {p["name"]: bool(p["enabled"]) for p in spec["plugins"]}


def diff(uproject, want):
    """-> [(name, current or None, wanted)] for every named plugin whose switch differs."""
    have = {p.get("Name"): bool(p.get("Enabled")) for p in uproject.get("Plugins", [])}
    return [(n, have.get(n), v) for n, v in sorted(want.items()) if have.get(n) != v]


def patched(uproject, want):
    out = json.loads(json.dumps(uproject))
    plugins = out.setdefault("Plugins", [])
    for p in plugins:
        if p.get("Name") in want:
            p["Enabled"] = want[p["Name"]]
    for n in sorted(set(want) - {p.get("Name") for p in plugins}):
        plugins.append({"Name": n, "Enabled": want[n]})
    return out


def read_ps(path=UPROJECT):
    return "Get-Content '%s' -Raw" % path.replace("/", "\\")


def write_ps(text, path=UPROJECT):
    w = path.replace("/", "\\")
    b64 = base64.b64encode(text.encode("utf-8")).decode()
    return (rb.editor_running_ps(os.path.dirname(path)).replace("else { 'STOPPED' }", "else { '' }") + "\n"
            "if ($e) { 'EDITOR RUNNING - not written'; exit 3 }\n"
            "Copy-Item '%s' '%s.bak' -Force\n"
            "[IO.File]::WriteAllText('%s', [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('%s')))\n"
            "'WRITTEN'" % (w, w, w, b64))


def main(argv=None, run=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--spec", default=SPEC)
    a = ap.parse_args(argv)
    kw = {"run": run} if run else {}
    with open(a.spec) as f:
        want = wanted(json.load(f))
    code, out = rb.rig(read_ps(), 120, **kw)
    up = json.loads(out[out.index("{"):out.rindex("}") + 1])
    d = diff(up, want)
    for n, cur, v in d:
        print("%s: %s -> %s" % (n, "absent" if cur is None else ("enabled" if cur else "disabled"), "enabled" if v else "disabled"))
    if not d:
        print("rig .uproject matches project_plugins.json")
        return 0
    if not a.apply:
        print("(dry run; --apply writes it with the editor stopped)")
        return 0
    code, out = rb.rig(write_ps(json.dumps(patched(up, want), indent="\t")), 120, **kw)
    print(out.strip().splitlines()[-1] if out.strip() else out)
    return 0 if "WRITTEN" in out else 1


if __name__ == "__main__":
    sys.exit(main())
