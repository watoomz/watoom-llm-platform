extends RefCounted
## Reports what is inside a scene so a model can classify an unknown asset without opening an editor.
## args: {scene}. Result data: aabb {pos, size}, meshes, surfaces, triangles, materials [{node, surface, kind, albedo, albedo_texture, emission,
## transparent, cull, unshaded, shader}], lights, skeletons, animation_players, has_collision.
func _walk(n: Node, xf: Transform3D, out: Dictionary) -> void:
	var t := xf
	if n is Node3D:
		t = xf * (n as Node3D).transform
	if n is Light3D:
		out["lights"] += 1
	if n is Skeleton3D:
		out["skeletons"] += 1
	if n is AnimationPlayer:
		out["animation_players"] += 1
	if n is CollisionShape3D:
		out["has_collision"] = true
	if n is MeshInstance3D and (n as MeshInstance3D).mesh != null:
		var mi := n as MeshInstance3D
		out["meshes"] += 1
		var bb: AABB = t * mi.mesh.get_aabb()
		out["bb"] = bb if out["bb"] == null else (out["bb"] as AABB).merge(bb)
		for s in range(mi.mesh.get_surface_count()):
			out["surfaces"] += 1
			var arr := mi.mesh.surface_get_arrays(s)
			if arr.size() > Mesh.ARRAY_INDEX and arr[Mesh.ARRAY_INDEX] != null and (arr[Mesh.ARRAY_INDEX] as PackedInt32Array).size() > 0:
				out["triangles"] += (arr[Mesh.ARRAY_INDEX] as PackedInt32Array).size() / 3
			elif arr[Mesh.ARRAY_VERTEX] != null:
				out["triangles"] += (arr[Mesh.ARRAY_VERTEX] as PackedVector3Array).size() / 3
			var m: Material = mi.material_override  # Godot: material_override beats a surface override beats the mesh material
			if m == null:
				m = mi.get_surface_override_material(s)
			if m == null:
				m = mi.mesh.surface_get_material(s)
			out["materials"].append(_describe(str(mi.name), s, m))
	for k in n.get_children():
		_walk(k, t, out)

func _describe(node: String, surface: int, m: Material) -> Dictionary:
	var d := {"node": node, "surface": surface, "kind": "none", "albedo": null, "albedo_texture": false, "emission": 0.0, "transparent": false,
		"cull": "back", "unshaded": false, "shader": ""}
	if m == null:
		return d
	d["kind"] = m.get_class()
	if m is BaseMaterial3D:
		var b := m as BaseMaterial3D
		d["albedo"] = [b.albedo_color.r, b.albedo_color.g, b.albedo_color.b, b.albedo_color.a]
		d["albedo_texture"] = b.albedo_texture != null
		d["emission"] = b.emission_energy_multiplier if b.emission_enabled else 0.0
		d["transparent"] = b.transparency != BaseMaterial3D.TRANSPARENCY_DISABLED
		d["cull"] = ["back", "front", "disabled"][b.cull_mode]
		d["unshaded"] = b.shading_mode == BaseMaterial3D.SHADING_MODE_UNSHADED
	elif m is ShaderMaterial:
		var sm := m as ShaderMaterial
		d["shader"] = sm.shader.resource_path if sm.shader != null else ""
		var a = sm.get_shader_parameter("albedo")
		if a is Color:
			d["albedo"] = [a.r, a.g, a.b, a.a]
	return d

func run(tree: SceneTree, args: Dictionary) -> Dictionary:
	var packed = load(str(args["scene"]))
	if packed == null or not (packed is PackedScene):
		return {"ok": false, "error": "cannot load %s as a scene (is it imported? run gg_project.py doctor)" % args["scene"]}
	var inst: Node = (packed as PackedScene).instantiate()
	var out := {"bb": null, "meshes": 0, "surfaces": 0, "triangles": 0, "materials": [], "lights": 0, "skeletons": 0, "animation_players": 0, "has_collision": false}
	_walk(inst, Transform3D.IDENTITY, out)
	var bb = out["bb"]
	inst.free()
	if bb == null:
		return {"ok": true, "data": {"scene": args["scene"], "meshes": 0, "aabb": null}}
	var b: AABB = bb
	var deps := []
	for d in ResourceLoader.get_dependencies(str(args["scene"])):
		var parts := str(d).split("::")
		deps.append(parts[parts.size() - 1])
	return {"ok": true, "data": {"scene": args["scene"], "dependencies": deps, "aabb": {"pos": [b.position.x, b.position.y, b.position.z], "size": [b.size.x, b.size.y, b.size.z]},
		"meshes": out["meshes"], "surfaces": out["surfaces"], "triangles": out["triangles"], "materials": out["materials"], "lights": out["lights"],
		"skeletons": out["skeletons"], "animation_players": out["animation_players"], "has_collision": out["has_collision"]}}
