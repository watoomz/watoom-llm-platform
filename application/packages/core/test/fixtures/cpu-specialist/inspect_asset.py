"""Minimal Blender geometry inspection fixture for the CPU specialist test.

Run inside Blender: blender --background --python inspect_asset.py -- inspect <asset>
  --input-root DIR --output-root DIR --output NAME
Writes <output-root>/<NAME>/manifest.json. Never modifies the input.
"""
import argparse, glob, hashlib, json, os, sys

import bpy

def digest(path):
    with open(path, "rb") as stream:
        return hashlib.sha256(stream.read()).hexdigest()

def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["inspect"])
    parser.add_argument("asset")
    parser.add_argument("--input-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if os.sep in args.asset or args.asset.startswith(".") or os.sep in args.output or args.output.startswith("."):
        raise SystemExit("asset and output must be plain names")
    source = os.path.join(args.input_root, args.asset)
    before_hash = digest(source)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.wm.obj_import(filepath=source)
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    before = [{"name": o.name, "vertices": len(o.data.vertices), "faces": len(o.data.polygons)} for o in meshes]
    target = os.path.join(args.output_root, args.output)
    os.makedirs(target)
    manifest = {
        "blender": bpy.app.version_string,
        "asset": args.asset,
        "asset_sha256": before_hash,
        "gpu_device_nodes_present": bool(glob.glob("/dev/nvidia*") or glob.glob("/dev/dri/*")),
        "original_unchanged": digest(source) == before_hash,
        "before": before,
    }
    with open(os.path.join(target, "manifest.json"), "w") as stream:
        json.dump(manifest, stream, indent=2, sort_keys=True)

main()
