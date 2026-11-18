#!/usr/bin/env python3
"""watoom-texture-layering: build a layered PBR material in Blender from a JSON spec.

Stacks layers bottom-to-top on one Principled BSDF the way a production material is authored: a base layer covers
everything, each later layer is mixed in by a mask (slope, height, noise, vertex colour, ambient occlusion, edges or
uniform), colour/roughness/metallic mix per layer, normals are blended (not averaged-then-lost), and optional global
macro variation (large-scale tint + roughness breakup) and detail normal (small-scale tiling) sit on top.

Usage (inside Blender; the pinned worker normally runs this, see SKILL.md):
  blender -b scene.blend -P blender_layered_material.py -- --spec layers_material.json [--objects A B] [--save out.blend]
  MCP:    import blender_layered_material as b; print(b.build(spec, objects=["Rock"]))

Spec (JSON):
  {"name": "M_Cliff", "tiling": 4,
   "macro":  {"scale_m": 12, "tint": [0.9, 0.9, 0.85], "tint_amount": 0.25, "roughness_amount": 0.2},   # optional
   "detail": {"normal": "tex/detail_n.png", "tiling": 24, "strength": 0.3},                           # optional
   "layers": [
     {"name": "base", "color": [0.4, 0.36, 0.3], "roughness": 0.9},                                      # first = base, no mask
     {"name": "rock", "textures": "tex/rock", "mask": {"type": "slope", "from_deg": 30, "to_deg": 50},   # textures = a folder
      "roughness": 0.8},
     {"name": "snow", "color": [0.9, 0.92, 0.95], "roughness": 0.55, "mask": {"type": "height", "from_m": 40, "to_m": 55,
      "noise": {"scale_m": 3, "amount": 0.3}}},
     {"name": "wear", "color": [0.55, 0.5, 0.45], "mask": {"type": "edges", "radius": 0.02, "invert": false}}]}
  Layer fields: color [r,g,b] sRGB 0-1 | textures (folder with basecolor/normal/roughness/ao maps named by suffix) |
  roughness | metallic | normal_strength | tiling (UV repeats) | projection ("uv" default, or "box" for UV-less meshes: colour/roughness only) | mask. Mask types: uniform, slope, height, noise, vertex_color
  (attribute name), ao (Cycles/EEVEE ambient occlusion node), edges (Bevel node; use for edge wear). "invert" flips a
  mask; "contrast" (default 1) sharpens it; "noise": {scale_m, amount} breaks up any mask boundary.

The result is procedural: it renders in Blender and bakes with blender-texture-baking, but it does not export to
glTF/FBX as-is -- bake albedo/ORM/normal for engines (SKILL.md, "Shipping to an engine").
"""
import json
import math
import os
import re
import sys

import bpy

MAPS = {
    "basecolor": ("basecolor", "albedo", "diffuse", "diff", "col", "color", "bc", "d"),
    "normal": ("normal", "normalgl", "nor", "nrm", "n"),
    "roughness": ("roughness", "rough", "rgh", "r"),
    "ao": ("ao", "occlusion", "ambientocclusion"),
}


class Builder:
    def __init__(self, mat):
        self.mat = mat
        self.nt = mat.node_tree
        self.nodes, self.links = self.nt.nodes, self.nt.links
        self._x = -1400

    def node(self, kind, label=None, **props):
        n = self.nodes.new(kind)
        if label:
            n.label = label
        for k, v in props.items():
            setattr(n, k, v)
        n.location = (self._x, 0)
        self._x += 40
        return n

    def link(self, out, inp):
        self.links.new(out, inp)

    def const(self, value):
        n = self.node("ShaderNodeValue")
        n.outputs[0].default_value = float(value)
        return n.outputs[0]

    def math(self, op, a=None, b=None, clamp=False):
        n = self.node("ShaderNodeMath", operation=op)
        n.use_clamp = clamp
        for i, v in enumerate((a, b)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                n.inputs[i].default_value = float(v)
            else:
                self.link(v, n.inputs[i])
        return n.outputs[0]

    def mix_color(self, fac, a, b, blend="MIX"):
        n = self.node("ShaderNodeMix", data_type="RGBA", blend_type=blend)
        self.link(fac, n.inputs["Factor"])
        for sock, v in ((n.inputs["A"], a), (n.inputs["B"], b)):
            if isinstance(v, (list, tuple)):
                sock.default_value = (*v, 1.0)
            else:
                self.link(v, sock)
        return n.outputs["Result"]

    def mix_float(self, fac, a, b):
        n = self.node("ShaderNodeMix", data_type="FLOAT")
        self.link(fac, n.inputs["Factor"])
        for sock, v in ((n.inputs["A"], a), (n.inputs["B"], b)):
            if isinstance(v, (int, float)):
                sock.default_value = float(v)
            else:
                self.link(v, sock)
        return n.outputs["Result"]

    def mix_vector(self, fac, a, b):
        n = self.node("ShaderNodeMix", data_type="VECTOR")
        self.link(fac, n.inputs["Factor"])
        self.link(a, n.inputs["A"])
        self.link(b, n.inputs["B"])
        return n.outputs["Result"]

    # ---- masks -------------------------------------------------------------------------------------------------
    def ramp(self, value, lo, hi):
        """0 below lo, 1 above hi, smooth in between (map range with smoothstep)."""
        n = self.node("ShaderNodeMapRange", data_type="FLOAT", interpolation_type="SMOOTHSTEP", clamp=True)
        self.link(value, n.inputs["Value"])
        n.inputs["From Min"].default_value, n.inputs["From Max"].default_value = float(lo), float(hi)
        return n.outputs["Result"]

    def noise(self, scale_m, seed_offset=0.0):
        n = self.node("ShaderNodeTexNoise", noise_dimensions="3D")
        n.inputs["Scale"].default_value = 1.0 / max(float(scale_m), 1e-4)
        coord = self.node("ShaderNodeTexCoord")
        shift = self.node("ShaderNodeVectorMath", operation="ADD")  # a different offset per use gives each mask its own pattern
        shift.inputs[1].default_value = (float(seed_offset) * 17.3, float(seed_offset) * 9.1, float(seed_offset) * 5.7)
        self.link(coord.outputs["Object"], shift.inputs[0])
        self.link(shift.outputs["Vector"], n.inputs["Vector"])
        return n.outputs["Fac"]

    def mask(self, m):
        t = m.get("type", "uniform")
        if t == "uniform":
            v = self.node("ShaderNodeValue")
            v.outputs[0].default_value = float(m.get("value", 1.0))
            out = v.outputs[0]
        elif t == "slope":
            # 0 on flat ground, 1 on vertical faces: angle from world up of the (object-space) geometry normal
            geo = self.node("ShaderNodeNewGeometry")
            tr = self.node("ShaderNodeVectorTransform", vector_type="NORMAL", convert_from="OBJECT", convert_to="WORLD")
            self.link(geo.outputs["Normal"], tr.inputs["Vector"])
            sep = self.node("ShaderNodeSeparateXYZ")
            self.link(tr.outputs["Vector"], sep.inputs["Vector"])
            angle = self.math("ARCCOSINE", self.math("MAXIMUM", self.math("MINIMUM", sep.outputs["Z"], 1.0), -1.0))
            out = self.ramp(self.math("DEGREES", angle), m.get("from_deg", 30.0), m.get("to_deg", 50.0))
        elif t == "height":
            pos = self.node("ShaderNodeNewGeometry")
            tr = self.node("ShaderNodeVectorTransform", vector_type="POINT", convert_from="OBJECT", convert_to="WORLD")
            self.link(pos.outputs["Position"], tr.inputs["Vector"])
            sep = self.node("ShaderNodeSeparateXYZ")
            self.link(tr.outputs["Vector"], sep.inputs["Vector"])
            z = sep.outputs["Z"]
            if "noise" in m:  # wobble the elevation so the snow line is not a flat plane
                z = self.math("ADD", z, self.math("MULTIPLY", self.math("SUBTRACT", self.noise(m["noise"].get("scale_m", 3.0)), 0.5), 2.0 * float(m["noise"].get("amount", 0.3)) * max(1e-6, float(m.get("to_m", 1)) - float(m.get("from_m", 0)))))
            out = self.ramp(z, m.get("from_m", 0.0), m.get("to_m", 1.0))
        elif t == "noise":
            out = self.ramp(self.noise(m.get("scale_m", 2.0)), m.get("from", 0.4), m.get("to", 0.6))
        elif t == "vertex_color":
            a = self.node("ShaderNodeAttribute", attribute_name=m["attribute"], attribute_type="GEOMETRY")
            sep = self.node("ShaderNodeSeparateColor")
            self.link(a.outputs["Color"], sep.inputs["Color"])
            out = sep.outputs[{"r": "Red", "g": "Green", "b": "Blue"}[m.get("channel", "r")]]
        elif t == "ao":
            n = self.node("ShaderNodeAmbientOcclusion", inside=bool(m.get("inside", False)), only_local=True)
            n.inputs["Distance"].default_value = float(m.get("distance", 0.5))
            out = self.math("SUBTRACT", 1.0, n.outputs["AO"])  # cavities -> 1
        elif t == "edges":
            # Bevel changes the normal only on convex edges: how far it differs from the geometry normal is the edge amount
            bevel = self.node("ShaderNodeBevel", samples=8)
            bevel.inputs["Radius"].default_value = float(m.get("radius", 0.02))
            geo = self.node("ShaderNodeNewGeometry")
            dot = self.node("ShaderNodeVectorMath", operation="DOT_PRODUCT")
            self.link(bevel.outputs["Normal"], dot.inputs[0])
            self.link(geo.outputs["Normal"], dot.inputs[1])
            out = self.ramp(self.math("SUBTRACT", 1.0, dot.outputs["Value"]), 0.0, float(m.get("sensitivity", 0.05)))
        else:
            raise ValueError("unknown mask type: " + t)
        if t != "height" and "noise" in m:
            out = self.math("MULTIPLY", out, self.math("ADD", 0.5, self.math("MULTIPLY", self.noise(m["noise"].get("scale_m", 2.0), 7.0), float(m["noise"].get("amount", 0.3)) * 2.0)), clamp=True)
        if float(m.get("contrast", 1.0)) != 1.0:
            out = self.math("MULTIPLY", self.math("SUBTRACT", out, 0.5), float(m["contrast"]))
            out = self.math("ADD", out, 0.5, clamp=True)
        if m.get("invert"):
            out = self.math("SUBTRACT", 1.0, out)
        return out


def find_maps(folder):
    found = {}
    for f in sorted(os.listdir(folder)):
        stem, ext = os.path.splitext(f)
        if ext.lower() not in (".png", ".jpg", ".jpeg", ".exr", ".tif", ".tiff", ".webp"):
            continue
        token = re.split(r"[_\-. ]", stem.lower())[-1]
        for kind, names in MAPS.items():
            if token in names and kind not in found:
                found[kind] = os.path.join(folder, f)
    return found


def image_node(b, path, colorspace, tiling, projection="uv"):
    """Image texture with its own mapping. UV by default (tangent-space normal maps need UVs); "box" projects from the
    object coordinates for UV-less meshes (colour and roughness only)."""
    img = bpy.data.images.load(os.path.abspath(path), check_existing=True)
    img.colorspace_settings.name = colorspace
    n = b.node("ShaderNodeTexImage", image=img)
    mp = b.node("ShaderNodeMapping")
    coord = b.node("ShaderNodeTexCoord")
    b.link(coord.outputs["UV" if projection == "uv" else "Object"], mp.inputs["Vector"])
    mp.inputs["Scale"].default_value = (tiling, tiling, tiling)
    if projection == "box":
        n.projection = "BOX"
        n.projection_blend = 0.25
    b.link(mp.outputs["Vector"], n.inputs["Vector"])
    return n


def layer_surface(b, layer, spec_tiling, warnings):
    """-> (color socket|rgb, roughness socket|float, metallic float, normal vector socket|None)"""
    tiling = float(layer.get("tiling", spec_tiling))
    projection = layer.get("projection", "uv")
    color, rough, normal = layer.get("color", [0.5, 0.5, 0.5]), float(layer.get("roughness", 0.8)), None
    if "textures" in layer:
        maps = find_maps(layer["textures"])
        if "basecolor" not in maps:
            raise ValueError("layer %s: no basecolor map found in %s" % (layer["name"], layer["textures"]))
        color = image_node(b, maps["basecolor"], "sRGB", tiling, projection).outputs["Color"]
        if "ao" in maps:
            ao = image_node(b, maps["ao"], "Non-Color", tiling, projection).outputs["Color"]
            color = b.mix_color(ao_fac(b, ao), color, [0.0, 0.0, 0.0])  # AO only deepens crevices (see references)
        if "roughness" in maps:
            sep = b.node("ShaderNodeSeparateColor")
            b.link(image_node(b, maps["roughness"], "Non-Color", tiling, projection).outputs["Color"], sep.inputs["Color"])
            rough = sep.outputs["Red"]
        if "normal" in maps:
            if projection == "box":
                warnings.append("layer %s: tangent-space normal map skipped under box projection (use UVs or a height/bump map)" % layer["name"])
            else:
                nm = b.node("ShaderNodeNormalMap", space="TANGENT")
                nm.inputs["Strength"].default_value = float(layer.get("normal_strength", 1.0))
                b.link(image_node(b, maps["normal"], "Non-Color", tiling).outputs["Color"], nm.inputs["Color"])
                normal = nm.outputs["Normal"]
    return color, rough, float(layer.get("metallic", 0.0)), normal


def ao_fac(b, ao_color):
    """A small darkening factor from an AO map (0..~0.35): AO is not a colour; it only deepens crevices."""
    sep = b.node("ShaderNodeSeparateColor")
    b.link(ao_color, sep.inputs["Color"])
    return b.math("MULTIPLY", b.math("SUBTRACT", 1.0, sep.outputs["Red"]), 0.35, clamp=True)


def build(spec, objects=()):
    name = spec.get("name", "M_Layered")
    layers = spec["layers"]
    if not layers:
        raise ValueError("at least one layer")
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    if hasattr(mat, "use_nodes"):
        mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    b = Builder(mat)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    default_tile = float(spec.get("tiling", 4.0))
    warnings = []
    color, rough, metal, normal = layer_surface(b, layers[0], default_tile, warnings)
    for layer in layers[1:]:
        fac = b.mask(layer.get("mask", {"type": "uniform"}))
        c, r, m, n = layer_surface(b, layer, default_tile, warnings)
        color = b.mix_color(fac, color, c)
        rough = b.mix_float(fac, rough, r)
        metal = b.mix_float(fac, metal, m)
        if n is not None:
            base_n = normal if normal is not None else None
            if base_n is None:
                flat = b.node("ShaderNodeNormalMap")  # flat tangent-space normal as the "below" value
                flat.inputs["Color"].default_value = (0.5, 0.5, 1.0, 1.0)
                base_n = flat.outputs["Normal"]
            normal = b.mix_vector(fac, base_n, n)
    macro = spec.get("macro")
    if macro:
        field = b.noise(macro.get("scale_m", 12.0), 3.0)
        tint = macro.get("tint", [1.0, 1.0, 1.0])
        tinted = b.mix_color(b.const(1.0), color, [*tint], "MULTIPLY")
        color = b.mix_color(b.math("MULTIPLY", field, float(macro.get("tint_amount", 0.25))), color, tinted)
        rough = b.math("ADD", rough, b.math("MULTIPLY", b.math("SUBTRACT", field, 0.5), float(macro.get("roughness_amount", 0.2))), clamp=True)
    detail = spec.get("detail")
    if detail and detail.get("normal"):
        d = b.node("ShaderNodeNormalMap", space="TANGENT")
        d.inputs["Strength"].default_value = float(detail.get("strength", 0.3))
        b.link(image_node(b, detail["normal"], "Non-Color", float(detail.get("tiling", 24.0))).outputs["Color"], d.inputs["Color"])
        normal = d.outputs["Normal"] if normal is None else b.mix_vector(b.const(0.5), normal, d.outputs["Normal"])
    for sock, v in ((bsdf.inputs["Base Color"], color), (bsdf.inputs["Roughness"], rough), (bsdf.inputs["Metallic"], metal)):
        if isinstance(v, (list, tuple)):
            sock.default_value = (*v, 1.0) if sock.name == "Base Color" else v
        elif isinstance(v, (int, float)):
            sock.default_value = float(v)
        else:
            b.link(v, sock)
    if normal is not None:
        b.link(normal, bsdf.inputs["Normal"])
    b.link(bsdf.outputs["BSDF"], out.inputs["Surface"])
    assigned = []
    for ob_name in objects:
        ob = bpy.data.objects[ob_name]
        if ob.type != "MESH":
            raise ValueError("%s is not a mesh" % ob_name)
        ob.data.materials.clear()
        ob.data.materials.append(mat)
        assigned.append(ob_name)
    return {"ok": True, "material": mat.name, "nodes": len(nt.nodes), "layers": [l.get("name", "?") for l in layers], "assigned": assigned, "warnings": warnings}


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--objects", nargs="*", default=[])
    ap.add_argument("--save")
    a = ap.parse_args(argv)
    result = build(json.load(open(a.spec)), a.objects)
    if a.save:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(a.save))
        result["saved"] = os.path.abspath(a.save)
    print("@@JSON@@" + json.dumps(result))


if __name__ == "__main__":
    main()
