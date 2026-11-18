#!/usr/bin/env python3
"""Merge separately-exported animation glbs onto a character mesh's skeleton and drive an AnimationTree
state machine across them (T-0068, part of T-0065).

  gg_anim.py check --project P --mesh res://assets/library/rogue.glb \\
      --states idle=res://assets/library/anim_idle.glb,walk=res://assets/library/anim_walk.glb,... \\
      [--transitions idle-walk,walk-run,...] [--timeout 90]

No BoneMap/SkeletonProfile retargeting step is needed when the mesh and every animation glb were exported
from the SAME Unreal Skeletal Mesh (checked directly in Blender first: identical armature name and bone
names/count across the rogue's mesh and all its MM_* animation glbs) -- an animation's tracks apply straight
onto the mesh's own Skeleton3D once copied into an AnimationPlayer with matching relative node paths, which
is what ops/anim_check.gd does. `--transitions` defaults to a simple locomotion graph (idle<->walk<->run,
any->jump->fall->land->idle) if the given state names match; pass your own to override. `check` proves each
state the AnimationTree travels to is reached AND that the skeleton's pelvis bone actually moves over the
following frames, not a frozen T-pose. Exit codes (shared with the other gg_* stages): 0 pass | 1 a check
failed | 2 refused | 3 fatal engine log line | 4 no verdict | 5 runner failure.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
import gg_godot  # noqa: E402

DEFAULT_EDGES = [("idle", "walk"), ("walk", "idle"), ("walk", "run"), ("run", "walk"),
                  ("idle", "jump"), ("walk", "jump"), ("run", "jump"),
                  ("jump", "fall"), ("fall", "land"), ("land", "idle")]


def check_project(project):
    if not os.path.isfile(os.path.join(project, "project.godot")):
        raise gg_godot.Refused("%s has no project.godot: run an init stage (e.g. gg_ui.py init / gg_player.py init) first" % project)
    if not os.path.isfile(os.path.join(project, "addons", "gg", "gg_runner.gd")):
        raise gg_godot.Refused("%s has no addons/gg runtime: run gg_project.py sync-runtime first" % project)


def _parse_states(spec):
    states = {}
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise gg_godot.Refused("--states entry %r is not name=res://path" % item)
        name, path = item.split("=", 1)
        states[name.strip()] = path.strip()
    return states


def _parse_transitions(spec, states):
    if not spec:
        return [list(e) for e in DEFAULT_EDGES if e[0] in states and e[1] in states]
    edges = []
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        if "-" not in item:
            raise gg_godot.Refused("--transitions entry %r is not from-to" % item)
        a, b = item.split("-", 1)
        edges.append([a.strip(), b.strip()])
    return edges


def check(a):
    project = os.path.abspath(a.project)
    check_project(project)
    states = _parse_states(a.states)
    if not states:
        raise gg_godot.Refused("--states gave no entries")
    transitions = _parse_transitions(a.transitions, states)
    r = gg_godot.run(project, "anim_check", {"mesh": a.mesh, "states": states, "transitions": transitions}, render=False, timeout=a.timeout)
    d = (r.result or {}).get("data") or {}
    if r.code not in (0, 1, 5) or not d:
        print("gg_anim check: exit %d: %s (job %s)" % (r.code, r.why, r.job_dir))
        return r.code
    for row in d["checks"]:
        print("  [%s] %s: %s" % ("ok" if row["ok"] else "FAIL", row["name"], row["detail"]))
    ok = all(row["ok"] for row in d["checks"])
    print("gg_anim check: %s: %d check(s) (job %s)" % ("PASS" if ok else "FAIL", len(d["checks"]), r.job_dir))
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check")
    p.add_argument("--project", required=True)
    p.add_argument("--mesh", required=True, help="res:// path to the character mesh glb")
    p.add_argument("--states", required=True, help="comma-separated name=res://path entries")
    p.add_argument("--transitions", default=None, help="comma-separated from-to entries; default is a locomotion graph over whichever of idle/walk/run/jump/fall/land were given")
    p.add_argument("--timeout", type=int, default=90)
    a = ap.parse_args(argv)
    try:
        return {"check": check}[a.cmd](a)
    except gg_godot.Refused as e:
        print("refused: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
