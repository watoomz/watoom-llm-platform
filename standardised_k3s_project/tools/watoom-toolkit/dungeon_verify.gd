extends SceneTree
func _initialize():
 call_deferred("_verify")
func fail(message):
 push_error(message)
 quit(1)
func _verify():
 var packed = load("res://scene.tscn")
 if not packed is PackedScene:
  fail("Scene import failed")
  return
 var instance = packed.instantiate()
 root.add_child(instance)
 await process_frame
 var meshes = instance.find_children("*", "MeshInstance3D", true, false)
 var collisions = instance.find_children("*", "CollisionShape3D", true, false)
 if meshes.is_empty() or collisions.is_empty():
  fail("Geometry or generated static collision missing")
  return
 var surfaces = 0
 var textured = 0
 for mesh in meshes:
  if mesh.mesh == null:
   fail("Missing mesh resource")
   return
  for index in range(mesh.mesh.get_surface_count()):
   surfaces += 1
   var material = mesh.get_active_material(index)
   if material is BaseMaterial3D and material.albedo_texture != null:
    textured += 1
 if surfaces == 0 or textured != surfaces:
  fail("Material texture lost during engine import")
  return
 var result = {"status":"PASS","meshes":meshes.size(),"collision_shapes":collisions.size(),"surfaces":surfaces,"textured_surfaces":textured}
 var file = FileAccess.open("res://acceptance.json",FileAccess.WRITE)
 file.store_string(JSON.stringify(result))
 file.close()
 quit(0)
