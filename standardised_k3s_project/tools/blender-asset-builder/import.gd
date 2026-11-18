extends SceneTree
func _initialize():
	var scene = load("res://magpie.glb") as PackedScene
	if scene == null:
		quit(1)
		return
	var instance = scene.instantiate()
	root.add_child(instance)
	var todo = [instance]
	var meshes = 0
	var surfaces = 0
	var vertices = 0
	var invalid = 0
	while not todo.is_empty():
		var node = todo.pop_back()
		todo.append_array(node.get_children())
		if node is MeshInstance3D and node.mesh != null:
			meshes += 1
			for s in node.mesh.get_surface_count():
				surfaces += 1
				var arrays = node.mesh.surface_get_arrays(s)
				for v in arrays[Mesh.ARRAY_VERTEX]:
					vertices += 1
					if not v.is_finite(): invalid += 1
				if node.get_active_material(s) == null: invalid += 1
	var result = {"status":"PASS" if meshes > 0 and vertices > 0 and invalid == 0 else "FAIL", "meshes":meshes,"surfaces":surfaces,"vertices":vertices,"invalid":invalid,"godot":Engine.get_version_info().string,"rig":"NOT TESTED"}
	var f = FileAccess.open("res://result.json",FileAccess.WRITE)
	f.store_string(JSON.stringify(result,"  "))
	f.close()
	print(JSON.stringify(result))
	quit(0 if result.status == "PASS" else 1)
