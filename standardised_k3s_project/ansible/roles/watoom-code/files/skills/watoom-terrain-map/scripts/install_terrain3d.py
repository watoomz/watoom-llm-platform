#!/usr/bin/env python3
"""watoom-terrain-map: bake a heightmap into native Terrain3D regions (Godot 4.5+).

Installs the vendored Terrain3D GDExtension addon (../vendor/addons/terrain_3d,
see ../vendor/PROVENANCE.md) into a Godot project if not already present, then
headlessly imports a heightmap -- the EXR build_terrain.py already wrote, or
any other single-channel height image -- into Terrain3D's own region format.
No Godot editor GUI is needed for this step; it runs a plain SceneTree script
through `godot --headless --rendering-driver dummy --script ...`.

This is additive, not a replacement: build_terrain.py's existing terrain.gd/
heightmap.exr output is untouched by this script and keeps working on its own.
Use this when a project specifically wants Terrain3D's multi-layer texture
painting, foliage instancing and region streaming instead of (or alongside)
the simpler single-mesh terrain.gd approach.

Known limitation (confirmed by test, see ../vendor/PROVENANCE.md): a project
that has never been opened/imported needs one `--editor --quit` pass before a
plain `--script` run can see the new GDExtension class at all, but Terrain3D's
editor-plugin UI reliably segfaults under pure headless Linux with no
display attached -- always AFTER the import pass it exists for has already
finished and been written to `.godot/`, so the crash itself is harmless and
this script (`prime_import()`) deliberately ignores it, running it only once
per project. Every actual height bake after that goes through a plain
`--script` SceneTree run (never `--editor`), which is fully reliable. Texture
painting, foliage placement etc. still need the real editor with an actual
display/GPU -- the rig -- and were not re-tested this session.

Example:
  install_terrain3d.py --heightmap /data/ai/projects/games/<proj>/World/terrain/heightmap.exr \
      --min 36.78 --max 184.42 --project /data/ai/projects/games/<proj> \
      --out World/terrain/terrain3d_data

Requires a `godot`/`godot4` binary (4.5+) on PATH on whatever host runs this
(the homelab lab host has one; this does not need the rig).
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VENDOR_ADDON = os.path.join(HERE, "..", "vendor", "addons", "terrain_3d")


def find_godot():
    for name in ("godot", "godot4"):
        p = shutil.which(name)
        if p:
            return p
    sys.exit("[terrain3d] no 'godot' or 'godot4' binary on PATH -- install Godot 4.5+ first")


def install_addon(project_dir):
    dest = os.path.join(project_dir, "addons", "terrain_3d")
    if os.path.isdir(dest):
        print(f"[terrain3d] addon already present at {dest} -- leaving it as is "
              f"(delete it first to reinstall from vendor)")
        return dest
    if not os.path.isdir(VENDOR_ADDON):
        sys.exit(f"[terrain3d] vendored addon missing at {VENDOR_ADDON}")
    os.makedirs(os.path.join(project_dir, "addons"), exist_ok=True)
    shutil.copytree(VENDOR_ADDON, dest)
    print(f"[terrain3d] installed addon -> {dest}")
    return dest


def ensure_plugin_enabled(project_godot_path):
    """Add 'res://addons/terrain_3d/plugin.cfg' to [editor_plugins] enabled=, idempotently."""
    entry = "res://addons/terrain_3d/plugin.cfg"
    text = open(project_godot_path).read() if os.path.exists(project_godot_path) else (
        "config_version=5\n\n[application]\n\nconfig/name=\"untitled\"\n")
    if entry in text:
        print("[terrain3d] project.godot already enables the plugin")
        return
    m = re.search(r"\[editor_plugins\]\s*\n(.*?)(?=\n\[|\Z)", text, re.S)
    if m is None:
        text = text.rstrip("\n") + f'\n\n[editor_plugins]\n\nenabled=PackedStringArray("{entry}")\n'
        open(project_godot_path, "w").write(text)
        print("[terrain3d] added a new [editor_plugins] section")
        return
    section = m.group(1)
    em = re.search(r'enabled\s*=\s*PackedStringArray\((.*?)\)', section, re.S)
    if em is None:
        new_section = section.rstrip("\n") + f'\nenabled=PackedStringArray("{entry}")\n'
        text = text[:m.start(1)] + new_section + text[m.end(1):]
        open(project_godot_path, "w").write(text)
        print("[terrain3d] added enabled= to the existing [editor_plugins] section")
        return
    inner = em.group(1).strip()
    new_inner = f'{inner}, "{entry}"' if inner else f'"{entry}"'
    new_line = f'enabled=PackedStringArray({new_inner})'
    text = text[:m.start(1) + em.start()] + new_line + text[m.start(1) + em.end():]
    open(project_godot_path, "w").write(text)
    print("[terrain3d] appended the plugin to the existing enabled= list")


BAKE_SCRIPT = """extends SceneTree

var frame: int = 0
var terrain: Node = null

func _process(_delta: float) -> bool:
    frame += 1
    if frame == 1:
        terrain = ClassDB.instantiate("Terrain3D")
        terrain.data_directory = {data_dir}
        root.add_child(terrain)
    elif frame == 5:
        var img: Image = Image.new()
        var err: int = img.load({heightmap})
        if err != OK:
            print("@@BAKE_FAIL@@ could not load heightmap, Image error ", err)
            quit(1)
            return false
        terrain.data.import_images([img, null, null], Vector3.ZERO, {offset}, {scale})
        var n: int = terrain.data.get_region_count()
        if n == 0:
            print("@@BAKE_FAIL@@ import produced zero regions")
            quit(1)
            return false
        terrain.data.save_directory({data_dir})
        print("@@BAKE_OK@@ regions=", n)
    elif frame == 8:
        quit()
    return false
"""


def prime_import(godot_bin, project_dir):
    """First-ever load of a project needs Godot to scan/import it once before a plain
    --script run can see newly added GDExtension classes (confirmed by test: a bare
    --script run on a never-opened project reports Terrain3D as unregistered). The
    only way to trigger that scan from the CLI goes through editor startup
    (--editor/--import), and Terrain3D's editor-plugin UI reliably segfaults with no
    display attached (confirmed by test, see ../vendor/PROVENANCE.md) -- but only
    AFTER the import/extension-discovery step it exists for has already finished and
    been written to .godot/. So: run it, and deliberately ignore its exit code/crash;
    bake()'s own explicit class-registration check right after is the real signal."""
    subprocess.run([godot_bin, "--headless", "--rendering-driver", "dummy", "--editor", "--quit"],
                    cwd=project_dir, capture_output=True, text=True, timeout=120)


def bake(godot_bin, project_dir, heightmap_path, offset, scale, data_dir_res):
    script_path = os.path.join(project_dir, ".terrain3d_bake_tmp.gd")
    open(script_path, "w").write(BAKE_SCRIPT.format(
        data_dir=json.dumps(data_dir_res), heightmap=json.dumps(heightmap_path),
        offset=float(offset), scale=float(scale)))
    try:
        proc = subprocess.run(
            [godot_bin, "--headless", "--rendering-driver", "dummy", "--script",
             os.path.basename(script_path), project_dir],
            cwd=project_dir, capture_output=True, text=True, timeout=120)
    finally:
        os.remove(script_path)
    out = proc.stdout + proc.stderr
    if "@@BAKE_OK@@" not in out:
        print(out, file=sys.stderr)
        if "Cannot get class 'Terrain3D'" in out:
            sys.exit("[terrain3d] the addon's GDExtension never registered. This project has "
                      "probably never been opened/imported before -- prime_import() should have "
                      "handled that; if it still fails, open the project once in the real editor "
                      "(the rig) and retry.")
        sys.exit(f"[terrain3d] bake failed (exit {proc.returncode}); see Godot output above")
    line = next(ln for ln in out.splitlines() if "@@BAKE_OK@@" in ln)
    print(f"[terrain3d] {line.replace('@@BAKE_OK@@', '').strip()}")


def write_scene(project_dir, scene_path, data_dir_res):
    abs_path = os.path.join(project_dir, scene_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    open(abs_path, "w").write(
        '[gd_scene load_steps=1 format=3]\n\n'
        '[node name="Terrain3D" type="Terrain3D"]\n'
        f'data_directory = "{data_dir_res}"\n'
    )
    print(f"[terrain3d] wrote {abs_path}")


def res_rel(project_dir, path):
    return "res://" + os.path.relpath(path, project_dir).replace(os.sep, "/")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--heightmap", required=True, help="path to a single-channel height image (EXR/PNG)")
    ap.add_argument("--min", type=float, required=True, help="world height (m) that pixel value 0.0 maps to")
    ap.add_argument("--max", type=float, required=True, help="world height (m) that pixel value 1.0 maps to")
    ap.add_argument("--project", required=True, help="Godot project root (has project.godot)")
    ap.add_argument("--out", default="World/terrain/terrain3d_data",
                     help="region data dir, relative to --project (default World/terrain/terrain3d_data)")
    ap.add_argument("--scene", default="World/terrain/terrain3d.tscn",
                     help="scene file to write, relative to --project")
    args = ap.parse_args()

    project_dir = os.path.abspath(args.project)
    pg = os.path.join(project_dir, "project.godot")
    if not os.path.exists(pg):
        sys.exit(f"[terrain3d] {project_dir} has no project.godot")

    install_addon(project_dir)
    ensure_plugin_enabled(pg)

    data_dir_abs = os.path.join(project_dir, args.out)
    os.makedirs(data_dir_abs, exist_ok=True)
    data_dir_res = res_rel(project_dir, data_dir_abs)

    godot_bin = find_godot()
    if not os.path.isdir(os.path.join(project_dir, ".godot", "imported")):
        print("[terrain3d] no existing .godot import cache -- priming the project once "
              "(a benign crash here is expected, see prime_import's docstring)")
        prime_import(godot_bin, project_dir)
    bake(godot_bin, project_dir, os.path.abspath(args.heightmap), args.min, args.max - args.min, data_dir_res)
    write_scene(project_dir, args.scene, data_dir_res)
    print(f"[terrain3d] done. Instance {res_rel(project_dir, os.path.join(project_dir, args.scene))} "
          f"in a scene. Texture painting / foliage still need the real editor on the rig; "
          f"collision_mode defaults to Dynamic/Game, which is fine for a shipped build.")


if __name__ == "__main__":
    main()
