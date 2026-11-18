extends SceneTree
func _init():
    var scene = load("res://geometry.glb") as PackedScene
    if scene == null:
        quit(2)
        return
    var node = scene.instantiate()
    root.add_child(node)
    var pending: Array[Node] = [node]
    var meshes = 0
    var vertices = 0
    var collisions = 0
    while not pending.is_empty():
        var item = pending.pop_back()
        pending.append_array(item.get_children())
        if item is Node3D and not item.transform.is_finite():
            quit(3)
            return
        if item is MeshInstance3D and item.mesh != null:
            meshes += 1
            for surface in range(item.mesh.get_surface_count()):
                vertices += item.mesh.surface_get_arrays(surface)[Mesh.ARRAY_VERTEX].size()
            if item.mesh.create_trimesh_shape() != null:
                collisions += 1
    if meshes < 1 or vertices < 3 or collisions < 1:
        quit(4)
        return
    var result = {"status":"PASS","meshes":meshes,"vertices":vertices,"collision_shapes_constructed":collisions,"engine":Engine.get_version_info().string,"scope":"Sample geometry compatibility; shader fidelity not certified"}
    var file = FileAccess.open("res://godot-geometry.json",FileAccess.WRITE)
    file.store_string(JSON.stringify(result))
    quit(0)
