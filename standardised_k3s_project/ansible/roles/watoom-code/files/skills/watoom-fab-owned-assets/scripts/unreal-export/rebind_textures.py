#!/usr/bin/env python3
"""Rebind exported textures onto an exported glb's material slots (T-0067, part of T-0065).

export_pack.py's ue_export_assets.py writes meshes (.glb) and their textures (.tga) as separate files; the
glb's material slots keep Unreal's shader graph structure but lose the Unreal material NAME (glTF export
renames them Material/Material_0/Material_1/...), so nothing rebinds the exported textures onto them -- every
imported combat mesh shows a flat white albedo in gg_assets.py check.

This drives headless Blender (the project's established tool for mesh/material work -- see
tools/blender-asset-builder, tools/ts4-animation) to: import the glb, assign one texture GROUP per material
slot (by exact glb material name, since names are generic and can't be inferred), wire a Base Color + Normal
Map + Roughness/Metallic (from either separate files or one packed ORM file) + optional Opacity/Emission into
each material's Principled BSDF, then export back out as a glb with the images packed in.

  rebind_textures.py --glb IN.glb --textures-dir DIR --bind '{"Material_0":"Exterior","Material_1":"Interior"}' --out OUT.glb

--bind maps each glb material name to a texture GROUP name; textures-dir is searched case-insensitively for
T_<group>_D|BaseColor.tga (albedo), _normal.tga, _roughness.tga, _metallic.tga, _ORM.tga (packed, G=rough
B=metal), _opacity.tga. A group needs at least an albedo file; everything else is optional. An _emissive/
_emiss file, if present, is intentionally left unbound (see _rebind_worker.py's comment -- the inspect check
flags any non-zero emission strength regardless of how dark a masked emissive texture mostly is). Exits 2
(refused) if --glb/--textures-dir are missing or no --bind group has an albedo match.
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
WORKER = os.path.join(HERE, "_rebind_worker.py")

SUFFIXES = {
    "albedo": ["_D", "_BaseColor", "_Diffuse"],
    "normal": ["_normal", "_Normal", "_N"],
    "roughness": ["_roughness", "_Roughness"],
    "metallic": ["_metallic", "_Metallic"],
    "orm": ["_ORM", "_orm"],
    "ao": ["_AO"],
    "opacity": ["_Opacity", "_opacity"],
    "emission": ["_Emissive", "_Emiss", "_emissive"],
}


def find_group_textures(textures_dir, group):
    found = {}
    for role, suffixes in SUFFIXES.items():
        for suf in suffixes:
            matches = glob.glob(os.path.join(textures_dir, "**", "*%s%s.tga" % (group, suf)), recursive=True)
            matches += glob.glob(os.path.join(textures_dir, "**", "*%s%s.TGA" % (group, suf)), recursive=True)
            if matches:
                found[role] = matches[0]
                break
    return found


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--glb", required=True)
    ap.add_argument("--textures-dir", required=True)
    ap.add_argument("--bind", required=True, help="JSON: {glb material name: texture group name}")
    ap.add_argument("--out", required=True)
    ap.add_argument("--blender", default="blender")
    a = ap.parse_args(argv)

    if not os.path.isfile(a.glb):
        print("refused: no such glb: %s" % a.glb, file=sys.stderr)
        return 2
    if not os.path.isdir(a.textures_dir):
        print("refused: no such textures dir: %s" % a.textures_dir, file=sys.stderr)
        return 2
    bind = json.loads(a.bind)

    groups = {}
    for mat_name, group in bind.items():
        tex = find_group_textures(a.textures_dir, group)
        if "albedo" not in tex:
            print("refused: no albedo texture found for group %r (material %r) under %s" % (group, mat_name, a.textures_dir), file=sys.stderr)
            return 2
        groups[mat_name] = tex

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"glb": os.path.abspath(a.glb), "out": os.path.abspath(a.out), "groups": groups}, f)
        request_path = f.name
    try:
        p = subprocess.run([a.blender, "--background", "--python", WORKER, "--", request_path],
                            capture_output=True, text=True, timeout=300)
    finally:
        os.unlink(request_path)
    sys.stdout.write(p.stdout)
    sys.stderr.write(p.stderr)
    if p.returncode != 0 or not os.path.isfile(a.out):
        print("rebind_textures: blender worker failed (exit %d), %s not written" % (p.returncode, a.out), file=sys.stderr)
        return 5
    print("rebind_textures: wrote %s (%d material(s) rebound)" % (a.out, len(groups)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
