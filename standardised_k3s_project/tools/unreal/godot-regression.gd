extends SceneTree
func _init():
    var packed = load("res://recovery-room.glb") as PackedScene
    if packed == null:
        push_error("GLB did not import as PackedScene")
        quit(2)
        return
    var scene = packed.instantiate()
    root.add_child(scene)
    var pending: Array[Node] = [scene]
    var meshes = 0
    var vertices = 0
    while not pending.is_empty():
        var node = pending.pop_back()
        pending.append_array(node.get_children())
        if node is Node3D and not node.transform.is_finite():
            push_error("Nonfinite transform")
            quit(3)
            return
        if node is MeshInstance3D and node.mesh != null:
            meshes += 1
            for surface in range(node.mesh.get_surface_count()):
                var arrays = node.mesh.surface_get_arrays(surface)
                vertices += arrays[Mesh.ARRAY_VERTEX].size()
    if meshes < 5 or vertices < 40:
        push_error("Missing room geometry: %s meshes %s vertices" % [meshes, vertices])
        quit(4)
        return
    var result = {"status":"PASS","meshes":meshes,"vertices":vertices,"engine":Engine.get_version_info().string}
    var out = FileAccess.open("res://godot-regression.json", FileAccess.WRITE)
    out.store_string(JSON.stringify(result))
    out.close()
    print("WATOOM_UNREAL_GODOT_REGRESSION_PASS ", JSON.stringify(result))
    quit(0)
