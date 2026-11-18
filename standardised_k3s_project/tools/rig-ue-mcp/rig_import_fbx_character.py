#!/usr/bin/env python3
"""Bring a rigged FBX character (creature, NPC) into the rig project: copy the files, import the skeletal mesh with its own
skeleton, import its clips onto that skeleton.

  rig_import_fbx_character.py --name SwampMonster --dest /Game/ZAS/Creatures/SwampMonster \\
      --mesh .../biped/Animation_Walking_withSkin.fbx --anim Walk=.../biped/Animation_Walking_withSkin.fbx \\
      --anim Run=.../biped/Animation_Running_withSkin.fbx [--scale 1.0] [--apply]

Creates <dest>/SK_<name> (+ its skeleton <dest>/SK_<name>_Skeleton and physics asset) and <dest>/A_<name>_<clip> per --anim.
Without --apply it prints the copy and the calls. The files go to <project>/Saved/Import/<name>/ with the `migrate`
maintenance account (key only); every .png next to an FBX is copied too, so materials find their textures.

Why (T-0023, 2026-11-19): the owner's creature models (Swamp_Monster, Snake_Robotic_Warrior, Abyssal_Leviathan_Pri) are FBX
exports whose biped clips (Animation_Walking_withSkin.fbx, ...) each carry the skinned mesh; importing one of them as the mesh
gives the skeleton the clips were made on. After this: ue_mesh_body.py for the body, then a combat spec with an anim_set and a
character (Wander.bEnabled for roaming).
Importer: always Interchange. The legacy FBX importer made these rigs' mesh node (Mesh0) the skeleton ROOT, and then every
clip failed ("Mesh contains Mesh0 bone as root but animation doesn't contain the root track"); Interchange gives the real root
(Hips) and the clips import with all 24 tracks (measured 2026-11-19). An existing mesh is kept (re-run safe).
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rig_copy_pack  # noqa: E402
import ue_route  # noqa: E402

PROJECT = "F:/Documents/Unreal Projects/WatooM_UEMCP_Test"


IMAGES = (".png", ".jpg", ".jpeg", ".tga")


def files_to_copy(mesh, anims, textures_from=None):
    """Every FBX plus the textures beside each (and every image under textures_from), without duplicates (order kept)."""
    out = []
    extra = sorted(os.path.join(r, n) for r, _, ns in os.walk(textures_from) for n in ns if n.lower().endswith(IMAGES)) if textures_from else []
    for g in extra:
        if g not in out:
            out.append(g)
    for f in [mesh] + [p for _, p in anims]:
        for g in [f] + sorted(os.path.join(os.path.dirname(f), n) for n in os.listdir(os.path.dirname(f) or ".") if n.lower().endswith(IMAGES)):
            if g not in out:
                out.append(g)
    return out


def rig_name(local_path, files):
    """Flatten to one folder on the rig; a clash of base names gets the parent folder as a prefix."""
    base = os.path.basename(local_path)
    if sum(1 for f in files if os.path.basename(f) == base) > 1:
        return "%s_%s" % (os.path.basename(os.path.dirname(local_path)), base)
    return base


def plan(name, dest, mesh, anims, scale=1.0, project=PROJECT, textures_from=None, static=False):
    if not name.replace("_", "").isalnum() or not dest.startswith("/Game/"):
        raise ValueError("name must be letters/digits/_ and dest a /Game/ path")
    for clip, _ in anims:
        if not clip.isalnum():
            raise ValueError("clip name %r must be letters/digits" % clip)
    files = files_to_copy(mesh, anims, textures_from)
    rdir = "%s/Saved/Import/%s" % (project, name)
    rp = {f: "%s/%s" % (rdir, rig_name(f, files)) for f in files}
    if static:
        if anims:
            raise ValueError("--static takes no --anim")
        # import_static_mesh has no save/replace flags: the explicit save below is what keeps it (T-0023: an unsaved statue
        # sat in a Save Content dialog that blocked the editor and was lost when the editor had to be ended)
        calls = [["asset.import_static_mesh", {"filePath": rp[mesh], "name": "SM_" + name, "packagePath": dest, "importMaterials": True,
                                               "importTextures": True, "combineMeshes": True, "importUniformScale": scale}]]
        calls.append(["asset.save", {"assetPaths": ["%s/SM_%s" % (dest, name)]}])
        return files, rdir, rp, {"phases": [{"name": "import " + name, "calls": calls}]}
    sk = "%s/SK_%s" % (dest, name)
    calls = [["asset.import_skeletal_mesh", {"filePath": rp[mesh], "name": "SK_" + name, "packagePath": dest, "importMaterials": True,
                                             "importTextures": True, "importUniformScale": scale, "createPhysicsAsset": True,
                                             "replaceExisting": False, "importer": "interchange", "save": True}]]
    for clip, f in anims:
        calls.append(["asset.import_animation", {"filePath": rp[f], "name": "A_%s_%s" % (name, clip), "packagePath": dest,
                                                 "skeletonPath": sk + "_Skeleton", "importSettings": {"bSnapToClosestFrameBoundary": True}}])
    # import_animation does NOT save (found 2026-11-19: six clips were still unsaved hours later and a plugin install's editor
    # stop opened a Save Content dialog that blocked everything); save the whole folder
    calls.append(["asset.save", {"assetPaths": ["%s/A_%s_%s" % (dest, name, clip) for clip, _ in anims]}])
    return files, rdir, rp, {"phases": [{"name": "import " + name, "calls": calls}]}


def imported_paths(reply):
    """Object paths an import reply names (importedAssets / animations[].path / assetPath), '' when it is not JSON."""
    try:
        d = json.loads(reply[reply.index("{"):])
    except ValueError:
        return []
    out = [p for p in d.get("importedAssets", []) if isinstance(p, str)]
    out += [x.get("path", "") for x in d.get("animations", []) if isinstance(x, dict)]
    out += [d[k] for k in ("assetPath", "skeleton") if isinstance(d.get(k), str)]
    return [p for p in out if p]


def in_folder(dirty_reply, folder):
    """Package names from an editor.list_dirty_packages reply that lie under folder (nothing else is ever saved here)."""
    try:
        d = json.loads(dirty_reply[dirty_reply.index("{"):])
    except ValueError:
        return []
    names = [x.get("package", x) if isinstance(x, dict) else x for x in d.get("content", []) + d.get("maps", [])]
    return [n for n in names if isinstance(n, str) and n.startswith(folder + "/")]


def main(argv=None, run=subprocess.run):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", required=True)
    ap.add_argument("--dest", required=True)
    ap.add_argument("--mesh", required=True, help="FBX holding the skinned mesh (a *_withSkin clip is fine)")
    ap.add_argument("--anim", action="append", default=[], help="Clip=path.fbx, repeatable")
    ap.add_argument("--static", action="store_true", help="a static mesh (statue, prop): SM_<name>, no skeleton or clips")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--textures-from", default=None, help="also copy every image under this folder (textures kept beside other FBXs)")
    ap.add_argument("--out", default=None, help="also write the calls file (for ue_run_phases.py)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--copy-only", action="store_true", help="with --apply: copy the files, do not import (the editor may be busy)")
    a = ap.parse_args(argv)
    anims = [tuple(x.split("=", 1)) for x in a.anim]
    files, rdir, rp, calls = plan(a.name, a.dest.rstrip("/"), a.mesh, anims, a.scale, textures_from=a.textures_from, static=a.static)
    if a.out:
        with open(a.out, "w") as f:
            json.dump(calls, f, indent=1)
    mk = ["ssh", "-i", rig_copy_pack.KEY, "-p", str(rig_copy_pack.PORT), "-o", "BatchMode=yes",
          "%s@%s" % (rig_copy_pack.USER, rig_copy_pack.HOST), 'mkdir "%s"' % rdir.replace("/", "\\")]
    cps = [["scp", "-q", "-i", rig_copy_pack.KEY, "-P", str(rig_copy_pack.PORT), "-o", "BatchMode=yes", f,
            "%s@%s:%s" % (rig_copy_pack.USER, rig_copy_pack.HOST, rp[f])] for f in files]
    if not a.apply:
        print("would copy %d files to %s and run:" % (len(files), rdir))
        print(json.dumps(calls, indent=1))
        return 0
    run(mk, capture_output=True)                       # may already exist
    for c in cps:
        if run(c).returncode:
            raise SystemExit("copy failed: " + c[-2])
    print("copied %d files to %s" % (len(files), rdir), flush=True)
    if a.copy_only:
        return 0
    t = ue_route.SshTransport(ue_route.ssh_command("10.99.1.44", 2224, "uemcp", ue_route.DEFAULT_KEY_DIR))
    bad, made = 0, []
    try:
        for m, args in calls["phases"][0]["calls"]:
            cat, meth = m.split(".", 1)
            if m == "asset.save":
                # also every asset an import reported, and every dirty package under the destination (materials, textures,
                # skeleton, physics asset: names the FBX decides; import_static_mesh's reply does not list its material)
                under = in_folder(t.call("editor", "list_dirty_packages", {}, 120), a.dest.rstrip("/"))
                args = {"assetPaths": sorted(set(args["assetPaths"]) | set(made) | set(under))}
            r = t.call(cat, meth, args, 900)
            if m.startswith("asset.import_"):
                made += [p.split(".")[0] for p in imported_paths(r) if p.startswith(a.dest.rstrip("/") + "/")]
            ok = not ue_route.reply_failed(r, getattr(t, "is_error", False)) or "Destination exists" in r   # re-run: keep it
            bad += not ok
            print("%s %s %s" % ("ok  " if ok else "FAIL", m, args.get("name", args.get("path")) if ok else r[:400]), flush=True)
    finally:
        t.close()
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
