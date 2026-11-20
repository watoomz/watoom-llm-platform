"""Derive bounded PBR maps from an indexed existing image; no learned or baked claim."""

import bpy, math
import numpy as np


def prepare(request, work):
    params = request.get("parameters", {})
    resolution = params.get("texture_resolution", 128)
    source = bpy.data.images.load(request["sources"][0]["path"], check_existing=False)
    if not len(source.pixels):
        raise ValueError("Source texture could not be decoded")
    original = list(source.size)
    source.scale(resolution, resolution)
    pixels = np.empty(resolution * resolution * 4, dtype=np.float32)
    source.pixels.foreach_get(pixels)
    rgba = pixels.reshape((resolution, resolution, 4))
    rgb = rgba[:, :, :3]
    if not np.isfinite(rgba).all():
        raise ValueError("Nonfinite source texture")
    luminance = np.mean(rgb, axis=2)
    dy, dx = np.gradient(luminance)
    normal = np.dstack((-dx * 2, -dy * 2, np.ones_like(dx)))
    normal /= np.linalg.norm(normal, axis=2, keepdims=True)
    normal = normal * 0.5 + 0.5
    roughness = np.clip(params.get("roughness", 0.65) + (luminance - 0.5) * 0.15, 0, 1)
    metallic = np.full_like(luminance, params.get("metallic", 0))
    values = {
        "albedo": rgb,
        "normal": normal,
        "roughness": np.repeat(roughness[:, :, None], 3, axis=2),
        "metallic": np.repeat(metallic[:, :, None], 3, axis=2),
        "orm": np.dstack((np.ones_like(luminance), roughness, metallic)),
    }
    images = {}
    for name, data in values.items():
        image = bpy.data.images.new("LibraryDerived-" + name, width=resolution, height=resolution, alpha=True)
        if name != "albedo":
            image.colorspace_settings.name = "Non-Color"
        array = np.dstack((data, np.ones_like(luminance))).astype(np.float32)
        image.pixels.foreach_set(array.ravel())
        image.update()
        image.filepath_raw = str(work / (name + ".png"))
        image.file_format = "PNG"
        image.save()
        image.pack()
        images[name] = image
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=1)
    obj = bpy.context.object
    obj.name = "LibraryMaterialPreview"
    for poly in obj.data.polygons:
        poly.use_smooth = True
    mat = bpy.data.materials.new("LibraryDerivedPBR")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    shader = nodes.get("Principled BSDF")
    for name, socket in [("albedo", "Base Color"), ("roughness", "Roughness"), ("metallic", "Metallic")]:
        node = nodes.new("ShaderNodeTexImage")
        node.image = images[name]
        if name == "albedo":
            albedo_node = node
        links.new(node.outputs["Color"], shader.inputs[socket])
    texture = nodes.new("ShaderNodeTexImage")
    texture.image = images["normal"]
    normal_node = nodes.new("ShaderNodeNormalMap")
    links.new(texture.outputs["Color"], normal_node.inputs["Color"])
    links.new(normal_node.outputs["Normal"], shader.inputs["Normal"])
    obj.data.materials.append(mat)
    # A real bounded UV bake of the reused albedo, with lighting excluded.
    # Other maps remain explicitly labelled procedural/configured, not geometry bakes.
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 1
    target = bpy.data.images.new("LibraryUVBakedAlbedo", width=resolution, height=resolution, alpha=True)
    target_node = nodes.new("ShaderNodeTexImage")
    target_node.image = target
    nodes.active = target_node
    emission = nodes.new("ShaderNodeEmission")
    links.new(albedo_node.outputs["Color"], emission.inputs["Color"])
    output = next(node for node in nodes if node.type == "OUTPUT_MATERIAL")
    links.new(emission.outputs[0], output.inputs["Surface"])
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.bake(type="EMIT", use_clear=True, margin=2)
    baked = np.empty(resolution * resolution * 4, dtype=np.float32)
    target.pixels.foreach_get(baked)
    if not np.isfinite(baked).all():
        raise ValueError("Nonfinite UV-baked albedo")
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    nodes.remove(emission)
    nodes.remove(target_node)
    albedo_node.image = target
    target.filepath_raw = str(work / "albedo.png")
    target.file_format = "PNG"
    target.save()
    target.pack()
    return {
        "material": {
            "source_dimensions": original,
            "resolution": resolution,
            "method": "UV-space emission bake of existing image albedo; luminance-derived procedural normal/roughness; configured metallic; no high/low geometry normal bake or learned generation",
            "baking": {"type": "EMIT", "device": "CPU", "resolution": resolution, "finite": True},
            "normal_convention": "OpenGL +Y",
            "orm_channels": {"R": "occlusion constant 1 (not baked)", "G": "roughness", "B": "metallic"},
            "roughness_base": params.get("roughness", 0.65),
            "metallic": params.get("metallic", 0),
            "finite_maps": True,
        },
        "_files": [name + ".png" for name in values],
    }
