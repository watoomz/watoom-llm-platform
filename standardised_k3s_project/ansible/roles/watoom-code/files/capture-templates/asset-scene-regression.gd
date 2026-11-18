extends SceneTree
## Run through an approved bounded worker, never a full game load in the app.
func _initialize() -> void:
 var helper = load("res://scripts/asset_scene_mesh.gd")
 var root := Node3D.new()
 var image := Image.create(2, 2, false, Image.FORMAT_RGBA8)
 image.fill(Color(0.2, 0.7, 0.1, 1))
 image.set_pixel(0, 0, Color(0, 0, 0, 0))
 var texture := ImageTexture.create_from_image(image)
 for row in [["Trunk_LOD0", Vector3(2, 0, 0)], ["Leaves_LOD0", Vector3(0, 3, 0)], ["Leaves_LOD1", Vector3(100, 100, 100)]]:
  var node := MeshInstance3D.new()
  node.name = row[0]
  node.position = row[1]
  var arrays: Array = []
  arrays.resize(Mesh.ARRAY_MAX)
  arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3.ZERO, Vector3.RIGHT, Vector3.UP])
  var mesh := ArrayMesh.new()
  mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
  node.mesh = mesh
  var material := StandardMaterial3D.new()
  material.albedo_texture = texture
  node.material_override = material
  root.add_child(node)
  node.owner = root
 var packed := PackedScene.new()
 assert(packed.pack(root) == OK)
 var path := "user://asset-scene-regression.tscn"
 assert(ResourceSaver.save(packed, path) == OK)
 var merged: ArrayMesh = helper.load_mesh(path)
 assert(merged.get_surface_count() == 2, "Exclude lower LOD while retaining trunk and leaves")
 assert(merged.get_aabb().end.x < 4 and merged.get_aabb().end.y >= 4, "Preserve child transforms")
 for i in 2:
  var material := merged.surface_get_material(i) as StandardMaterial3D
  assert(material.albedo_texture != null, "Preserve instance material override and texture")
  assert(material.transparency == BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR, "Respect texture alpha")
 assert((root.get_child(0).material_override as StandardMaterial3D).transparency == BaseMaterial3D.TRANSPARENCY_DISABLED, "Do not mutate authored resources")
 root.free()
 DirAccess.remove_absolute(ProjectSettings.globalize_path(path))
 var terrain = load("res://scripts/terrain.gd").new()
 terrain.build()
 var terrain_mesh: Mesh = terrain.build_terrain_mesh()
 var collision: CollisionShape3D = terrain.build_collision_node()
 var faces := terrain_mesh.get_faces()
 assert(faces == collision.shape.get_faces(), "Render and collision surfaces must match")
 assert(faces.size() == terrain.GRID_DIV * terrain.GRID_DIV * 6, "Triangle triplets required")
 for i in range(0, faces.size(), 3):
  var a := Vector2(faces[i].x, faces[i].z)
  var b := Vector2(faces[i+1].x, faces[i+1].z)
  var c := Vector2(faces[i+2].x, faces[i+2].z)
  assert(absf((b-a).cross(c-a)) > 0.01, "No collapsed ground triangles")
 for i in terrain.tree_count:
  assert(terrain.tree_transform(i).origin.is_equal_approx(terrain.tree_positions[i]), "Scaling must not move tree origins")
 var tree: Mesh = helper.load_mesh("res://assets/m7/env/Trees/SM_Small_Tree_04_LOD.gltf")
 assert(tree.get_surface_count() == 2, "Actual tree requires LOD0 trunk and leaves only")
 assert(tree.surface_get_material(1).albedo_texture != null, "Actual leaf texture preserved")
 assert(tree.surface_get_material(1).transparency == BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR, "Actual leaf cutout alpha enabled")
 collision.free()
 print("PASS: LOD, component transforms, material overrides, alpha, source immutability, terrain topology/collision and instance origins")
 quit()
