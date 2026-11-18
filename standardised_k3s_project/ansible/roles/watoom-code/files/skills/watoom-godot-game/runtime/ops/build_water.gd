extends RefCounted
## Builds res://levels/<level>/water.tscn: a sea plane at sea_level_m over the whole world and a ribbon mesh per creek.
## args: {level, style, world:{size_m:[x,z], cell_m, size_px}, sea_level_m, color:[r,g,b], creeks:[{points:[[x,y,z]...], width_m}]}
## Result data: scene, sea_y (the saved plane's world y), creek_vertices, nodes.
const Save := preload("res://addons/gg/lib/save.gd")
const Style := preload("res://addons/gg/lib/style.gd")

func _material(style: Dictionary, color: Color) -> Material:
	var m: Material = Style.material(style, color, "water")
	if m is StandardMaterial3D:
		var sm := m as StandardMaterial3D
		sm.cull_mode = BaseMaterial3D.CULL_DISABLED
		if style["material"]["shading"] == "pbr":
			sm.roughness = 0.08
			sm.metallic_specular = 0.9
			sm.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
			sm.albedo_color = Color(color.r, color.g, color.b, 0.82)
	return m

func _ribbon(points: Array, width: float) -> ArrayMesh:
	var verts := PackedVector3Array()
	var norms := PackedVector3Array()
	var n := points.size()
	for i in range(n):
		var p := Vector3(points[i][0], points[i][1], points[i][2])
		var a: Vector3 = Vector3(points[maxi(i - 1, 0)][0], 0, points[maxi(i - 1, 0)][2])
		var b: Vector3 = Vector3(points[mini(i + 1, n - 1)][0], 0, points[mini(i + 1, n - 1)][2])
		var t := (b - a).normalized()
		var side := Vector3(-t.z, 0, t.x) * (width * 0.5)
		verts.append(p + side)
		verts.append(p - side)
		norms.append(Vector3.UP)
		norms.append(Vector3.UP)
	var idx := PackedInt32Array()
	for i in range(n - 1):
		var q := [i * 2, i * 2 + 1, (i + 1) * 2, (i + 1) * 2 + 1]
		for tri in [[q[0], q[1], q[2]], [q[1], q[3], q[2]]]:
			var e1: Vector3 = verts[tri[1]] - verts[tri[0]]
			var e2: Vector3 = verts[tri[2]] - verts[tri[0]]
			if e1.cross(e2).y > 0.0:  # Godot front faces are clockwise seen from the front: we want up, so cross(e1, e2).y must be negative
				idx.append_array([tri[0], tri[2], tri[1]])
			else:
				idx.append_array(tri)
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = verts
	arrays[Mesh.ARRAY_NORMAL] = norms
	arrays[Mesh.ARRAY_INDEX] = idx
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	return mesh

func run(tree: SceneTree, args: Dictionary) -> Dictionary:
	var style: Dictionary = args["style"]
	var W: Dictionary = args["world"]
	var sx := float(W["size_m"][0])
	var sz := float(W["size_m"][1])
	var c: Array = args["color"]
	var color := Color(c[0], c[1], c[2])
	var mat := _material(style, color)
	var root := Node3D.new()
	root.name = "Water"
	var sea := MeshInstance3D.new()
	sea.name = "Sea"
	var plane := PlaneMesh.new()
	plane.size = Vector2(sx, sz)
	plane.material = mat
	sea.mesh = plane
	sea.position = Vector3(sx * 0.5, float(args["sea_level_m"]), sz * 0.5)
	root.add_child(sea)
	var cverts := 0
	var k := 0
	for cr in args.get("creeks", []):
		var mi := MeshInstance3D.new()
		mi.name = "Creek_%d" % k
		var mesh := _ribbon(cr["points"], float(cr["width_m"]))
		mesh.surface_set_material(0, mat)
		mi.mesh = mesh
		cverts += mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX].size()
		root.add_child(mi)
		k += 1
	var out := "res://levels/%s/water.tscn" % args["level"]
	var saved := Save.save_scene(root, out)
	if not saved["ok"]:
		return saved
	var back: Node = (ResourceLoader.load(out, "PackedScene", ResourceLoader.CACHE_MODE_IGNORE) as PackedScene).instantiate()
	var sea_y: float = back.get_node("Sea").position.y
	back.free()
	return {"ok": true, "data": {"scene": out, "sea_y": sea_y, "creek_vertices": cverts, "nodes": saved["nodes"]}}
