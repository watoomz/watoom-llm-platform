extends RefCounted
## Builds res://levels/<level>/scatter.tscn: one MultiMeshInstance3D per family, from a placement list.
## args: {level, families:{name:{scene, instances:[[x,y,z,yaw_rad,scale],...]}}}
## Each family's scene parts are merged into ONE mesh (every part keeps its material). Result data: families {name: count}, nodes.
const Save := preload("res://addons/gg/lib/save.gd")

func _collect(n: Node, xf: Transform3D, out: Array) -> void:
	var t := xf
	if n is Node3D:
		t = xf * (n as Node3D).transform
	if n is MeshInstance3D and (n as MeshInstance3D).mesh != null:
		out.append([n, t])
	for k in n.get_children():
		_collect(k, t, out)

func _merge(scene_path: String) -> ArrayMesh:
	var packed = load(scene_path)
	if packed == null or not (packed is PackedScene):
		return null
	var inst: Node = (packed as PackedScene).instantiate()
	var parts: Array = []
	_collect(inst, Transform3D.IDENTITY, parts)
	var mesh := ArrayMesh.new()
	for p in parts:
		var mi: MeshInstance3D = p[0]
		var t: Transform3D = p[1]
		for s in range(mi.mesh.get_surface_count()):
			if mi.mesh is ArrayMesh and (mi.mesh as ArrayMesh).surface_get_primitive_type(s) != Mesh.PRIMITIVE_TRIANGLES:  # primitive meshes are always triangles
				inst.free()
				return null  # lines/points/strips would be rewritten as triangles
			var arr := mi.mesh.surface_get_arrays(s)
			var v: PackedVector3Array = arr[Mesh.ARRAY_VERTEX]
			var nv := PackedVector3Array()
			nv.resize(v.size())
			for i in range(v.size()):
				nv[i] = t * v[i]
			arr[Mesh.ARRAY_VERTEX] = nv
			if arr[Mesh.ARRAY_NORMAL] != null:
				var nn: PackedVector3Array = arr[Mesh.ARRAY_NORMAL]
				var rn := PackedVector3Array()
				rn.resize(nn.size())
				for i in range(nn.size()):
					rn[i] = (t.basis.inverse().transposed() * nn[i]).normalized()
				arr[Mesh.ARRAY_NORMAL] = rn
			if arr[Mesh.ARRAY_TANGENT] != null:
				var tg: PackedFloat32Array = arr[Mesh.ARRAY_TANGENT]
				for i in range(tg.size() / 4):
					var tv := (t.basis * Vector3(tg[i * 4], tg[i * 4 + 1], tg[i * 4 + 2])).normalized()
					tg[i * 4] = tv.x
					tg[i * 4 + 1] = tv.y
					tg[i * 4 + 2] = tv.z
				arr[Mesh.ARRAY_TANGENT] = tg
			mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
			var m: Material = mi.material_override  # Godot: material_override beats a surface override beats the mesh material
			if m == null:
				m = mi.get_surface_override_material(s)
			if m == null:
				m = mi.mesh.surface_get_material(s)
			mesh.surface_set_material(mesh.get_surface_count() - 1, m)
	inst.free()
	return mesh

func run(tree: SceneTree, args: Dictionary) -> Dictionary:
	var root := Node3D.new()
	root.name = "Scatter"
	var counts := {}
	for fam in args["families"].keys():
		var spec: Dictionary = args["families"][fam]
		var mesh := _merge(str(spec["scene"]))
		if mesh == null or mesh.get_surface_count() == 0:
			return {"ok": false, "error": "family %s: cannot build a mesh from %s" % [fam, spec["scene"]]}
		var inst: Array = spec["instances"]
		var mm := MultiMesh.new()
		mm.transform_format = MultiMesh.TRANSFORM_3D
		mm.mesh = mesh
		mm.instance_count = inst.size()
		for i in range(inst.size()):
			var d: Array = inst[i]
			var b := Basis(Vector3.UP, float(d[3])).scaled(Vector3.ONE * float(d[4]))
			mm.set_instance_transform(i, Transform3D(b, Vector3(d[0], d[1], d[2])))
		var node := MultiMeshInstance3D.new()
		node.name = str(fam)
		node.multimesh = mm
		node.set_meta("gg_family", str(fam))
		root.add_child(node)
		counts[fam] = inst.size()
	var out := "res://levels/%s/scatter.tscn" % args["level"]
	var saved := Save.save_scene(root, out)
	if not saved["ok"]:
		return saved
	var back: Node = (ResourceLoader.load(out, "PackedScene", ResourceLoader.CACHE_MODE_IGNORE) as PackedScene).instantiate()
	for fam in counts.keys():
		var n := back.get_node_or_null(str(fam))
		if n == null or (n as MultiMeshInstance3D).multimesh == null or (n as MultiMeshInstance3D).multimesh.instance_count != counts[fam]:
			back.free()
			return {"ok": false, "error": "reloaded scatter scene does not hold %d instances of %s" % [counts[fam], fam]}
		# positions must survive the save: compare the first, middle and last instance with what was asked for (a headless run keeps none of them)
		var want: Array = args["families"][fam]["instances"]
		for k in [0, want.size() / 2, want.size() - 1]:
			var got: Vector3 = (n as MultiMeshInstance3D).multimesh.get_instance_transform(k).origin
			if got.distance_to(Vector3(want[k][0], want[k][1], want[k][2])) > 0.01:
				back.free()
				return {"ok": false, "error": "family %s instance %d reloaded at %s but was placed at %s: transforms were not saved (is the op running under a real renderer?)" % [fam, k, got, Vector3(want[k][0], want[k][1], want[k][2])]}
	back.free()
	return {"ok": true, "data": {"scene": out, "families": counts, "nodes": saved["nodes"]}}
