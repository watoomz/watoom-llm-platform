extends RefCounted
## The one save protocol for every builder: set owner on every descendant, pack, save <name>.new.tscn, reload with
## CACHE_MODE_IGNORE, compare node counts, rename over the final name. On any failure the .new file is removed and the
## final scene is untouched. Returns {ok, error, nodes}.
static func count(n: Node) -> int:
	var c := 1
	for k in n.get_children():
		c += count(k)
	return c

static func set_owner_rec(n: Node, owner_node: Node, keep_instances: bool = false) -> void:
	for k in n.get_children():
		k.owner = owner_node
		if keep_instances and str(k.scene_file_path) != "":
			continue  # an instanced scene is saved as a reference: its own children keep their own owner
		set_owner_rec(k, owner_node, keep_instances)

## keep_instances = true: child nodes that were instanced from a scene file are saved as references to that file, not flattened into this scene.
static func save_scene(root: Node, out: String, keep_instances: bool = false) -> Dictionary:
	var tmp := out.replace(".tscn", ".new.tscn")
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(out.get_base_dir()))
	set_owner_rec(root, root, keep_instances)
	var want := count(root)
	var packed := PackedScene.new()
	var err := packed.pack(root)
	if err != OK:
		return {"ok": false, "error": "pack failed (%d)" % err}
	err = ResourceSaver.save(packed, tmp)
	if err != OK:
		return {"ok": false, "error": "save failed (%d): %s" % [err, tmp]}
	var back = ResourceLoader.load(tmp, "PackedScene", ResourceLoader.CACHE_MODE_IGNORE)
	if back == null:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(tmp))
		return {"ok": false, "error": "reload of %s failed" % tmp}
	var inst: Node = back.instantiate()
	var got := count(inst)
	var bad := _empty_meshes(inst)
	inst.free()
	if bad != "":
		DirAccess.remove_absolute(ProjectSettings.globalize_path(tmp))
		return {"ok": false, "error": "reloaded scene has a MeshInstance3D without a mesh or material: " + bad}
	if got != want:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(tmp))
		return {"ok": false, "error": "reload mismatch: built %d nodes, reloaded %d (nodes without owner are dropped on save)" % [want, got]}
	var rn := DirAccess.rename_absolute(ProjectSettings.globalize_path(tmp), ProjectSettings.globalize_path(out))
	if rn != OK:
		return {"ok": false, "error": "rename of %s over %s failed (%d)" % [tmp, out, rn]}
	return {"ok": true, "nodes": got}

static func _empty_meshes(n: Node) -> String:
	if n is MeshInstance3D:
		var mi := n as MeshInstance3D
		if mi.mesh == null:
			return str(mi.name) + " (no mesh)"
		for i in range(mi.mesh.get_surface_count()):
			if mi.mesh.surface_get_material(i) == null and mi.get_surface_override_material(i) == null and mi.material_override == null:
				return str(mi.name) + " (surface %d has no material)" % i
	for k in n.get_children():
		var r := _empty_meshes(k)
		if r != "":
			return r
	return ""
