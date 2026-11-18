"""Blender-side half of rebind_textures.py: runs under `blender --background --python _rebind_worker.py --
<request.json>`. Not a standalone CLI -- imports bpy, so it only runs inside Blender.

request.json: {"glb": path, "out": path, "groups": {material_name: {albedo, normal?, roughness?, metallic?,
orm?, ao?, opacity?, emission?: path}}}. For each named material already present after import, builds a
Principled BSDF texture graph from whichever roles were found and exports the whole scene back out as one glb
with the images packed in (export_image_format=AUTO re-encodes any source format, TGA included, to PNG/JPEG;
Blender reads TGA natively so no pre-conversion is needed).
"""
import json
import sys

import bpy

request_path = sys.argv[sys.argv.index("--") + 1]
req = json.loads(open(request_path).read())

# --background still loads the factory startup scene (its own default Cube/Camera/Light); clear it first so
# the exported glb holds only what the source file actually had, not an inflated bounding box from a stray
# 2m default cube.
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

bpy.ops.import_scene.gltf(filepath=req["glb"])

materials = {m.name: m for m in bpy.data.materials}
bound = 0
for mat_name, tex in req["groups"].items():
    mat = materials.get(mat_name)
    if mat is None or not mat.use_nodes:
        print("rebind: skipping %r, not found in %s" % (mat_name, list(materials)))
        continue
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        print("rebind: skipping %r, no Principled BSDF node" % mat_name)
        continue

    def img_node(path, non_color):
        image = bpy.data.images.load(path, check_existing=True)
        if non_color:
            image.colorspace_settings.name = "Non-Color"
        node = nodes.new("ShaderNodeTexImage")
        node.image = image
        return node

    albedo = img_node(tex["albedo"], non_color=False)
    links.new(albedo.outputs["Color"], bsdf.inputs["Base Color"])

    if "opacity" in tex:
        opacity = img_node(tex["opacity"], non_color=True)
        links.new(opacity.outputs["Color"], bsdf.inputs["Alpha"])
        mat.blend_method = "CLIP"

    if "normal" in tex:
        normal_tex = img_node(tex["normal"], non_color=True)
        normal_map = nodes.new("ShaderNodeNormalMap")
        links.new(normal_tex.outputs["Color"], normal_map.inputs["Color"])
        links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])

    if "orm" in tex:
        orm = img_node(tex["orm"], non_color=True)
        sep = nodes.new("ShaderNodeSeparateColor")
        links.new(orm.outputs["Color"], sep.inputs["Color"])
        links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
        links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
    else:
        if "roughness" in tex:
            rough = img_node(tex["roughness"], non_color=True)
            links.new(rough.outputs["Color"], bsdf.inputs["Roughness"])
        if "metallic" in tex:
            metal = img_node(tex["metallic"], non_color=True)
            links.new(metal.outputs["Color"], bsdf.inputs["Metallic"])

    # emission is deliberately not wired: gg_assets.py check (gg_catalog.py's `glows` rule) reads the
    # material's uniform emission_energy_multiplier, not the texture's content, so a masked emissive (e.g.
    # glowing eyes on an otherwise-black mask) trips it as a false "glows" error the same as a fully-lit one.
    # Rebinding albedo/normal/roughness/metallic is this worker's job (T-0067); masked emission needs the
    # checker taught to sample the texture, not a strength constant, so it's left unbound for now.

    bound += 1

for image in bpy.data.images:
    image.pack()

bpy.ops.export_scene.gltf(filepath=req["out"], export_format="GLB", export_image_format="AUTO", export_materials="EXPORT")
print("rebind: bound %d/%d material(s), wrote %s" % (bound, len(req["groups"]), req["out"]))
