extends SceneTree
func _initialize():
 call_deferred("_verify")
func _verify():
 var packed = load("res://scene.tscn")
 assert(packed is PackedScene, "Scene import failed")
 var instance = packed.instantiate()
 root.add_child(instance)
 await process_frame
 var meshes = instance.find_children("*", "MeshInstance3D", true, false)
 assert(meshes.size() > 0, "Missing imported mesh")
 var collisions = instance.find_children("*", "CollisionShape3D", true, false)
 if OS.get_environment("WATOOM_COLLISION") == "1":
  assert(collisions.size() > 0, "Collision did not import")
 var result = {"status":"PASS","meshes":meshes.size(),"collision_shapes":collisions.size()}
 if OS.get_environment("WATOOM_MATERIAL") == "1":
  var material = meshes[0].get_active_material(0)
  assert(material is BaseMaterial3D, "Missing imported PBR material")
  assert(material.albedo_texture != null, "Albedo texture did not import")
  assert(material.normal_enabled and material.normal_texture != null, "Normal map did not import")
  assert(material.roughness_texture != null and material.metallic_texture != null, "Packed PBR channels did not import")
  result["material_maps"] = "albedo, normal, roughness and metallic imported"
 if OS.get_environment("WATOOM_CHARACTER") == "1":
  var players = instance.find_children("*", "AnimationPlayer", true, false)
  var skeletons = instance.find_children("*", "Skeleton3D", true, false)
  assert(players.size() > 0 and skeletons.size() > 0, "Missing player or skeleton")
  var player = players[0]
  var skeleton = skeletons[0]
  var motion = {}
  for required in ["Idle", "Walk", "Run"]:
   var clip = ""
   for name in player.get_animation_list():
    if name == required or name.ends_with("/" + required):
     clip = name
   assert(clip != "", "Missing required clip: " + required)
   var length = player.get_animation(clip).length
   assert(length > 0, "Empty clip")
   player.play(clip)
   player.seek(length * 0.1, true)
   skeleton.force_update_all_bone_transforms()
   var first = []
   for bone in range(skeleton.get_bone_count()):
    first.append(skeleton.get_bone_pose(bone))
   player.seek(length * 0.37, true)
   skeleton.force_update_all_bone_transforms()
   var delta = 0.0
   for bone in range(skeleton.get_bone_count()):
    var pose = skeleton.get_bone_pose(bone)
    delta = max(delta, first[bone].origin.distance_to(pose.origin))
    delta = max(delta, first[bone].basis.get_rotation_quaternion().angle_to(pose.basis.get_rotation_quaternion()))
   assert(delta > 0.00001, "No actual skeleton motion: " + required)
   motion[required] = delta
  result["animation_motion"] = motion
  result["bones"] = skeleton.get_bone_count()
 var file = FileAccess.open("res://acceptance.json", FileAccess.WRITE)
 file.store_string(JSON.stringify(result))
 file.close()
 quit(0)
