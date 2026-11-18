#!/usr/bin/env python3
"""watoom-texture-layering: write the ue-mcp calls that build a layered Unreal landscape material (host-side; stdlib only).

Reads layer_masks.py's layer_report.json and the Unreal texture asset path of each layer, and writes material_calls.json:
the exact arguments for material.create, material.build_graph (TextureSample x layer, LandscapeLayerSample named after the
layer, Multiply, Add chain -> BaseColor, constant Roughness), landscape.set_material, plus the verification steps.

  unreal_landscape_material.py --layers terrain/layers --textures grass=/Game/ZAS/Textures/T_grass_D dirt=/Game/ZAS/Textures/T_dirt_D \
      --material /Game/ZAS/M_Terrain --landscape MyLandscape --tiling 2.5 --out ue/material_calls.json

Two engine facts this encodes (found the hard way): the layer name goes in "properties": {"ParameterName": ...} (a plain
parameterName field is ignored and every sample reads 'None'); and a landscape keeps drawing its default grey material until
the level is saved and reloaded after the material is assigned (reopening the same level does NOT reload it: open another level and
then this one). A landscape material has a 16-sampler budget shared with the landscape's own weightmaps and heightmap, so keep the
referenced textures to about 8-10 (material.get_shader_stats referencedTextureCount): 7 layers + detail + macro (15) rendered grey.
"""
import argparse
import json
import os
import sys


def build(layers, textures, material, tiling, roughness, normals=None, detail=None, macro=None, macro_texture=None, macro_gain=1.8, landscape="<landscape label>"):
    """normals: optional {layer: /Game/normal_map}; detail: optional factor (e.g. 0.11) for a second, larger-scale pass.

    With `detail`, every layer's colour is texture(uv*tiling) * texture(uv*tiling*detail) * 2, which hides the repeat and
    adds large-scale variation (a single flat-tiled texture reads as flat colour from a distance). With `normals`, the
    weighted sum of the layers' normal maps drives Normal, so the ground has relief under the sun.
    With `macro` (e.g. 0.006; landscape UVs are one unit per quad, so repeats across the map = macro * tiling * (vertices - 1)), the finished colour is multiplied by `macro_texture`
    (default: the last layer's texture) sampled at that very large scale times `macro_gain`, so the ground gets light and dark
    patches across hundreds of metres instead of reading as one flat colour. The macro texture is DESATURATED first: multiplying a
    green grass colour by a brown soil colour turns the whole ground grey-brown, so it may only change brightness."""
    normals = normals or {}
    names = [n for n in layers]
    missing = [n for n in names if n not in textures]
    if missing:
        raise SystemExit("no texture asset given for layer(s): %s" % ", ".join(missing))
    nodes = [{"name": "uv", "class": "MaterialExpressionTextureCoordinate", "posX": -1700, "posY": 0,
              "properties": {"UTiling": float(tiling), "VTiling": float(tiling)}}]
    conn = []
    if detail:
        nodes += [{"name": "uv2", "class": "MaterialExpressionTextureCoordinate", "posX": -1700, "posY": 200,
                   "properties": {"UTiling": float(tiling) * float(detail), "VTiling": float(tiling) * float(detail)}},
                  {"name": "two", "class": "MaterialExpressionConstant", "posX": -1300, "posY": -200, "value": 2.0}]
    for i, n in enumerate(names):
        y = i * 300
        nodes += [{"name": "tex_" + n, "class": "MaterialExpressionTextureSample", "posX": -1400, "posY": y, "texturePath": textures[n]},
                  {"name": "w_" + n, "class": "MaterialExpressionLandscapeLayerSample", "posX": -1100, "posY": y + 150, "properties": {"ParameterName": n}},
                  {"name": "m_" + n, "class": "MaterialExpressionMultiply", "posX": -800, "posY": y}]
        conn += [{"from": "uv", "to": "tex_" + n, "toInput": "Coordinates"}, {"from": "w_" + n, "to": "m_" + n, "toInput": "B"}]
        if detail:
            nodes += [{"name": "tex2_" + n, "class": "MaterialExpressionTextureSample", "posX": -1400, "posY": y + 100, "texturePath": textures[n]},
                      {"name": "mix_" + n, "class": "MaterialExpressionMultiply", "posX": -1100, "posY": y},
                      {"name": "mix2_" + n, "class": "MaterialExpressionMultiply", "posX": -950, "posY": y}]
            conn += [{"from": "uv2", "to": "tex2_" + n, "toInput": "Coordinates"},
                     {"from": "tex_" + n, "fromOutput": "RGB", "to": "mix_" + n, "toInput": "A"},
                     {"from": "tex2_" + n, "fromOutput": "RGB", "to": "mix_" + n, "toInput": "B"},
                     {"from": "mix_" + n, "to": "mix2_" + n, "toInput": "A"}, {"from": "two", "to": "mix2_" + n, "toInput": "B"},
                     {"from": "mix2_" + n, "to": "m_" + n, "toInput": "A"}]
        else:
            conn.append({"from": "tex_" + n, "fromOutput": "RGB", "to": "m_" + n, "toInput": "A"})
    prev = "m_" + names[0]
    for i, n in enumerate(names[1:]):
        a = "add_%d" % i
        nodes.append({"name": a, "class": "MaterialExpressionAdd", "posX": -500 + i * 120, "posY": i * 200})
        conn += [{"from": prev, "to": a, "toInput": "A"}, {"from": "m_" + n, "to": a, "toInput": "B"}]
        prev = a
    if macro:
        mt = macro_texture or textures[names[-1]]
        nodes += [{"name": "uvm", "class": "MaterialExpressionTextureCoordinate", "posX": -1700, "posY": 400,
                   "properties": {"UTiling": float(tiling) * float(macro), "VTiling": float(tiling) * float(macro)}},
                  {"name": "tex_macro", "class": "MaterialExpressionTextureSample", "posX": -1400, "posY": 1400, "texturePath": mt},
                  {"name": "desat", "class": "MaterialExpressionDesaturation", "posX": -1200, "posY": 1400},
                  {"name": "one", "class": "MaterialExpressionConstant", "posX": -1300, "posY": 1500, "value": 1.0},
                  {"name": "gain", "class": "MaterialExpressionConstant", "posX": -1300, "posY": 1300, "value": float(macro_gain)},
                  {"name": "macro_k", "class": "MaterialExpressionMultiply", "posX": -1000, "posY": 1400},
                  {"name": "macro_out", "class": "MaterialExpressionMultiply", "posX": -300, "posY": 1300}]
        conn += [{"from": "uvm", "to": "tex_macro", "toInput": "Coordinates"},
                 {"from": "tex_macro", "fromOutput": "RGB", "to": "desat", "toInput": "Input"}, {"from": "one", "to": "desat", "toInput": "Fraction"},
                 {"from": "desat", "to": "macro_k", "toInput": "A"}, {"from": "gain", "to": "macro_k", "toInput": "B"},
                 {"from": prev, "to": "macro_out", "toInput": "A"}, {"from": "macro_k", "to": "macro_out", "toInput": "B"}]
        prev = "macro_out"
    props = [{"property": "BaseColor", "from": prev}, {"property": "Roughness", "from": "rough"}]
    nodes.append({"name": "rough", "class": "MaterialExpressionConstant", "posX": -300, "posY": 1500, "value": float(roughness)})
    if normals:
        nprev = None
        for i, n in enumerate(names):
            if n not in normals:
                continue
            nodes += [{"name": "ntex_" + n, "class": "MaterialExpressionTextureSample", "posX": -1400, "posY": 1700 + i * 200, "texturePath": normals[n]},
                      {"name": "nm_" + n, "class": "MaterialExpressionMultiply", "posX": -800, "posY": 1700 + i * 200}]
            conn += [{"from": "uv", "to": "ntex_" + n, "toInput": "Coordinates"},
                     {"from": "ntex_" + n, "fromOutput": "RGB", "to": "nm_" + n, "toInput": "A"}, {"from": "w_" + n, "to": "nm_" + n, "toInput": "B"}]
            if nprev is None:
                nprev = "nm_" + n
            else:
                add = "nadd_" + n
                nodes.append({"name": add, "class": "MaterialExpressionAdd", "posX": -500, "posY": 1700 + i * 200})
                conn += [{"from": nprev, "to": add, "toInput": "A"}, {"from": "nm_" + n, "to": add, "toInput": "B"}]
                nprev = add
        if nprev:
            props.append({"property": "Normal", "from": nprev})
    folder, _, name = material.rpartition("/")
    return {
        "layers": names,
        "calls": [
            ["material.create", {"name": name, "packagePath": folder}],
            ["material.build_graph", {"assetPath": material, "nodes": nodes, "connections": conn, "propertyConnections": props}],
            ["landscape.set_material", {"materialPath": material, "landscapeName": landscape}],
            ["level.save", {}],
            ["asset.save_all_dirty", {"saveMapPackages": True, "saveContentPackages": True}],
            ["level.load", {"levelPath": "<another map>", "saveFirst": False, "discardUnsaved": False}],
            ["level.load", {"levelPath": "<the level with the landscape>", "saveFirst": False, "discardUnsaved": False}],
        ],
        "verify": ["material.read_graph must list Landscape Layer Sample '<layer>' for every layer (never 'None')",
                   "after the save + reload, wait for editor.get_shader_compile_status {waitUntilIdle: true}, then tools/rig-ue-mcp/ue_viewport_shot.py OUT.png must show the layers, not uniform grey (editor.capture_scene_png only for geometry and placement)",
                   "editor.get_log filtered on 'Failed to compile' must be empty: a failed compile keeps the last good shader and hides every later edit",
                   "normal-map TextureSample nodes need a Normal sampler type: check material.read_graph and the capture for relief"],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--layers", required=True, help="layer_masks.py output directory (reads layer_report.json)")
    ap.add_argument("--textures", nargs="+", required=True, metavar="LAYER=/Game/path", help="one Unreal texture asset path per layer")
    ap.add_argument("--material", required=True, help="new material asset path, e.g. /Game/ZAS/M_Terrain")
    ap.add_argument("--tiling", type=float, default=2.5, help="UV repeats per landscape quad (one UV unit per quad: tile_m = quad_m / tiling; 2.5 on a 7.94 m quad gives ~3 m tiles)")
    ap.add_argument("--landscape", required=True, help="landscape actor label for landscape.set_material")
    ap.add_argument("--roughness", type=float, default=0.9)
    ap.add_argument("--normals", nargs="*", default=[], metavar="LAYER=/Game/normal", help="optional normal map per layer")
    ap.add_argument("--detail", type=float, default=0.0, help="second-pass tiling factor, e.g. 0.11 (0 = off)")
    ap.add_argument("--macro", type=float, default=0.0, help="very-large-scale colour variation factor, e.g. 0.006 (0 = off)")
    ap.add_argument("--macro-texture", default=None, help="texture for the macro pass (default: the last layer's texture)")
    ap.add_argument("--macro-gain", type=float, default=1.8)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    report = json.load(open(os.path.join(a.layers, "layer_report.json")))
    layers = [l["name"] for l in report["layers"]]
    textures = dict(t.split("=", 1) for t in a.textures)
    out = build(layers, textures, a.material, a.tiling, a.roughness, dict(t.split("=", 1) for t in a.normals), a.detail or None,
                a.macro or None, a.macro_texture, a.macro_gain, landscape=a.landscape)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(out, open(a.out, "w"), indent=2)
    print("wrote", a.out, "for layers:", ", ".join(layers))
    return 0


if __name__ == "__main__":
    sys.exit(main())
