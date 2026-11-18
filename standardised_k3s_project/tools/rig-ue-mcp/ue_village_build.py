#!/usr/bin/env python3
"""Build the village from a unreal_village.py layout: clear foliage on the pad, move the existing village actors, add the new pieces as foliage instances.

  ue_village_build.py layout.json --old-heights live_before.png --new-heights pad.png --z0 3677.7 --raw-per-cm 4.4387 --size-m 4000 [--clear-m 115] [--apply]

Run the pad heights first (ue_run_phases.py on unreal_creek_profile.calls_for(old, new)). Without --apply it only prints the plan. Steps: (1) foliage.remove_instances
{center, radius} for every foliage type; (2) level.move_actor for each `existing` label, keeping its height above the old ground; (3) one foliage type per mesh
(`foliage.create_type`, <type-dir>/FT_V_<mesh>; --type-dir defaults to <content_root>/Foliage/Village from the --project profile, /Game/Foliage/Village
without one) and foliage.add_instances with explicit transforms on the new ground. Finish with level.save. If any clear, move, create_type or add
step failed it does NOT save and exits 1 (--force-save saves anyway); a failed save exits 1.
The layout and both heights files go through ue_asset_check.py first (also without --apply): a missing key (`existing` is read only after the
foliage is cleared), a NaN, a bad mesh name or heights that are not 16-bit PNGs of one size exit 1 before anything is sent to the editor.
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SKILL = os.path.join(HERE, "..", "..", "ansible", "roles", "watoom-code", "files", "skills", "watoom-texture-layering", "scripts")
sys.path.insert(0, SKILL)
import ue_project  # noqa: E402
import ue_asset_check  # noqa: E402
from ue_foliage_buried import ground_z  # noqa: E402

MESH_DIR = "/Game/AdvancedVillagePack/Meshes"  # the pack the layout meshes come from; override with --mesh-dir
TYPE_DIR = "/Game/Foliage/Village"  # foliage types are created here; override with --type-dir or content_root in the --project profile


def transforms(instances, raw, z0, rpc, px_cm):
    """{mesh: [transform, ...]} with Z on the ground (minus each instance's sink)."""
    out = {}
    for i in instances:
        z = ground_z(raw, z0, rpc, px_cm, i["x"], i["y"]) - i.get("sink", 8.0)
        out.setdefault(i["mesh"], []).append({"location": {"x": i["x"], "y": i["y"], "z": round(z, 1)}, "rotation": {"pitch": 0, "yaw": i["yaw"], "roll": 0},
                                              "scale": {"x": 1, "y": 1, "z": 1}})
    return out


def moves(existing, old_actor_pos, raw_old, raw_new, z0, rpc, px_cm):
    """New location per existing actor label: same height above the ground as before."""
    out = {}
    for lab, e in existing.items():
        ox, oy, oz = old_actor_pos[lab]
        above = oz - ground_z(raw_old, z0, rpc, px_cm, ox, oy)
        out[lab] = {"x": e["x"], "y": e["y"], "z": round(ground_z(raw_new, z0, rpc, px_cm, e["x"], e["y"]) + max(above, 0.0), 1), "yaw": e["yaw"]}
    return out


def main(argv=None):
    import ue_route
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("layout")
    ap.add_argument("--old-heights", required=True)
    ap.add_argument("--new-heights", required=True)
    ap.add_argument("--z0", type=float, required=True)
    ap.add_argument("--raw-per-cm", type=float, required=True)
    ap.add_argument("--size-m", type=float, required=True)
    ap.add_argument("--clear-m", type=float, default=115.0)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--force-save", action="store_true", help="save the level even when a step failed (default: stop before saving and exit 1)")
    ap.add_argument("--host", default="10.99.1.44")
    ap.add_argument("--port", type=int, default=2224)
    ap.add_argument("--user", default="uemcp")
    ap.add_argument("--key-dir", default=ue_route.DEFAULT_KEY_DIR)
    ap.add_argument("--mesh-dir", default=MESH_DIR)
    ap.add_argument("--type-dir", default=None, help="default <content_root>/Foliage/Village")
    ue_project.apply(ap, argv)
    a = ap.parse_args(argv)
    type_dir = a.type_dir or (ue_project.get("content_root", "/Game").rstrip("/") + "/Foliage/Village")
    if ue_asset_check.gate(ue_asset_check.check_layout(a.layout, mesh_dir=a.mesh_dir) + ue_asset_check.check_heights(a.old_heights, a.new_heights), a.layout):
        return 1
    lay = json.load(open(a.layout))
    old, new = np.asarray(Image.open(a.old_heights)), np.asarray(Image.open(a.new_heights))
    px_cm = a.size_m * 100.0 / (new.shape[0] - 1)
    tf = transforms(lay["instances"], new, a.z0, a.raw_per_cm, px_cm)
    print("instances per mesh:", {k: len(v) for k, v in tf.items()})
    if not a.apply:
        return 0

    def j(text):
        return json.loads(text[text.index("{"):])
    t = ue_route.SshTransport(ue_route.ssh_command(a.host, a.port, a.user, a.key_dir))
    failures = []

    def ok(r, what):
        good = ue_route.reply_ok(r, getattr(t, "is_error", False))
        if not good:
            failures.append(what)
        return good
    try:
        cx, cy = lay["center"]
        types, cur = [], None
        while True:
            d = j(t.call("foliage", "list_types", dict({"limit": 100}, **({"cursor": cur} if cur else {})), 120))
            types += [x["path"] for x in d.get("foliageTypes", [])]
            cur = d.get("nextCursor")
            if not d.get("hasMore") or not cur:
                break
        for ty in types:
            r = t.call("foliage", "remove_instances", {"foliageTypePath": ty, "center": {"x": cx, "y": cy, "z": lay["level_z"]}, "radius": a.clear_m * 100.0}, 300)
            print("cleared", ty.split("/")[-1], "ok" if ok(r, "clear " + ty.split("/")[-1]) else r[:120], flush=True)
        old_pos = {}
        for lab in lay["existing"]:
            d = j(t.call("level", "get_actor_details", {"actorLabel": lab}, 60))
            loc = d["location"]
            old_pos[lab] = (loc["x"], loc["y"], loc["z"])
        for lab, m in moves(lay["existing"], old_pos, old, new, a.z0, a.raw_per_cm, px_cm).items():
            r = t.call("level", "move_actor", {"actorLabel": lab, "location": {"x": m["x"], "y": m["y"], "z": m["z"]}, "rotation": {"pitch": 0, "yaw": m["yaw"], "roll": 0}}, 60)
            print("moved", lab, "ok" if ok(r, "move " + lab) else r[:120], flush=True)
        for mesh, trs in tf.items():
            path = "%s/FT_V_%s.FT_V_%s" % (type_dir, mesh, mesh)
            r = t.call("foliage", "create_type", {"meshPath": "%s/SM_%s.SM_%s" % (a.mesh_dir, mesh, mesh), "name": "FT_V_" + mesh, "packagePath": type_dir, "onConflict": "skip"}, 120)
            if not ue_route.reply_ok(r, getattr(t, "is_error", False)) and "exist" not in r.lower():
                failures.append("create_type " + mesh)
                print("create_type FAILED", mesh, r[:200], flush=True)
                continue
            for k in range(0, len(trs), 150):
                r = t.call("foliage", "add_instances", {"foliageTypePath": path, "transforms": trs[k:k + 150], "projectToGround": False, "applyTypeRules": False, "skipCollision": True}, 300)
                print("added", mesh, len(trs[k:k + 150]), "ok" if ok(r, "add " + mesh) else r[:160], flush=True)
        if failures and not a.force_save:
            print("NOT saving: %d step(s) failed (%s). The level is changed but unsaved; note this build is not re-runnable on top of itself." % (len(failures), ", ".join(failures[:6])))
            return 1
        r = t.call("level", "save", {}, 300)
        print(r[:60])
        if ue_route.reply_failed(r, getattr(t, "is_error", False)):
            print("level.save FAILED")
            return 1
        if failures:
            return 1   # saved on request (--force-save) but steps failed
    finally:
        t.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
