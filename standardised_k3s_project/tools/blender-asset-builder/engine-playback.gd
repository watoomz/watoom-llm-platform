extends SceneTree
var meshes := 0
var invalid := 0
var players: Array[AnimationPlayer] = []
var skeletons: Array[Skeleton3D] = []
func visit(n: Node):
 if n is MeshInstance3D:
  meshes += 1
  if not n.mesh: invalid += 1
  else:
   for s in range(n.mesh.get_surface_count()):
    var a = n.mesh.surface_get_arrays(s)
    for v in a[Mesh.ARRAY_VERTEX]:
     if not v.is_finite(): invalid += 1
 if n is AnimationPlayer: players.append(n)
 if n is Skeleton3D: skeletons.append(n)
 for child in n.get_children(): visit(child)
func pose() -> String:
 var values: Array = []
 for s in skeletons:
  for b in range(s.get_bone_count()): values.append(str(s.get_bone_pose(b)))
 return JSON.stringify(values)
func _initialize():
 call_deferred("check")
func check():
 var packed = load("res://asset.glb")
 if not packed:
  quit(1)
  return
 var scene = packed.instantiate()
 root.add_child(scene)
 await process_frame
 visit(scene)
 var motions := {}
 for p in players:
  for name in p.get_animation_list():
   if name == "RESET": continue
   p.play(name)
   p.seek(0.0, true)
   var a = pose()
   p.seek(0.25, true)
   var b = pose()
   motions[name] = {"changed": a != b, "duration": p.get_animation(name).length}
 var animated = FileAccess.file_exists("res://animated.required")
 var ok = meshes > 0 and invalid == 0
 if animated:
  ok = ok and skeletons.size() > 0 and motions.size() >= 3
  for name in motions: ok = ok and motions[name].changed
 var result = {"status": "PASS" if ok else "FAIL", "meshes": meshes, "invalid": invalid, "skeletons": skeletons.size(), "motions": motions}
 var f = FileAccess.open("res://result.json", FileAccess.WRITE)
 f.store_string(JSON.stringify(result, "  "))
 print(JSON.stringify(result))
 quit(0 if ok else 1)
