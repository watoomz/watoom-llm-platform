extends RefCounted
## Assemble authored highest-detail components; keep node transforms and materials.
static func load_mesh(path: String) -> ArrayMesh:
 var scene := load(path) as PackedScene
 if scene == null:
  push_error("Asset is not a PackedScene: " + path)
  return null
 var root := scene.instantiate()
 var rows: Array = []
 _collect(root, Transform3D.IDENTITY, -1, rows)
 var best := 2147483647
 for row in rows:
  if row.lod >= 0:
   best = mini(best, row.lod)
 var merged := ArrayMesh.new()
 for row in rows:
  if row.lod >= 0 and row.lod != best:
   continue
  var node: MeshInstance3D = row.node
  for surface in node.mesh.get_surface_count():
   var tool := SurfaceTool.new()
   tool.append_from(node.mesh, surface, row.transform)
   tool.set_material(_material(node.get_active_material(surface)))
   tool.commit(merged)
 root.free()
 if merged.get_surface_count() == 0:
  push_error("No usable mesh surfaces: " + path)
  return null
 return merged

static func _collect(node: Node, parent_transform: Transform3D, inherited_lod: int, rows: Array) -> void:
 var transform := parent_transform
 if node is Node3D:
  transform = parent_transform * node.transform
 var lod := inherited_lod
 var regex := RegEx.new()
 regex.compile("(?i)_lod([0-9]+)(?:$|_)")
 var match_result := regex.search(str(node.name))
 if match_result != null:
  lod = int(match_result.get_string(1))
 if node is MeshInstance3D and node.mesh != null:
  rows.append({"node": node, "transform": transform, "lod": lod})
 for child in node.get_children():
  _collect(child, transform, lod, rows)

static func _material(original: Material) -> Material:
 if not original is StandardMaterial3D:
  return original
 var material := original as StandardMaterial3D
 # Some exported foliage declares OPAQUE despite a cutout alpha texture.
 if material.transparency == BaseMaterial3D.TRANSPARENCY_DISABLED and material.albedo_texture != null:
  var image := material.albedo_texture.get_image()
  if image != null:
   if image.is_compressed():
    image.decompress()
   if image.detect_alpha() != Image.ALPHA_NONE:
    material = material.duplicate() as StandardMaterial3D
    material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
    material.alpha_scissor_threshold = 0.5
    material.cull_mode = BaseMaterial3D.CULL_DISABLED
 return material
