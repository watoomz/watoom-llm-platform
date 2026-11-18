extends RefCounted
## Builds res://levels/<level>/terrain.tscn: chunked ArrayMesh + HeightMapShape3D + a layered splat material chosen by the style.
## args: {level, style, world:{size_m:[x,z], cell_m, size_px:[nx,nz]}, heights_f32:"/abs", splats:["/abs/splat_0.png", ...],
##        colors:[[r,g,b],...], chunk:int}
## Result data: collider_max_err (64 raycasts at vertices vs the height data), mesh_y/data_y ranges, chunks, nodes.
const Save := preload("res://addons/gg/lib/save.gd")
const Style := preload("res://addons/gg/lib/style.gd")

func _shader_for(style: Dictionary) -> String:
	match style["material"]["shading"]:
		"flat": return "terrain_flat"
		"toon": return "terrain_toon"
		"unshaded": return "terrain_unshaded"
	return "terrain_pbr"

func run(tree: SceneTree, args: Dictionary) -> Dictionary:
	var style: Dictionary = args["style"]
	var W: Dictionary = args["world"]
	var nx := int(W["size_px"][0])
	var nz := int(W["size_px"][1])
	var cell := float(W["cell_m"])
	var level := str(args["level"])
	var gen := "res://gg/generated/%s" % level
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(gen))
	var f := FileAccess.open(str(args["heights_f32"]), FileAccess.READ)
	if f == null:
		return {"ok": false, "error": "cannot open heights %s" % args["heights_f32"]}
	var h: PackedFloat32Array = f.get_buffer(nx * nz * 4).to_float32_array()
	f.close()
	if h.size() != nx * nz:
		return {"ok": false, "error": "heights file has %d values, world.json says %dx%d=%d" % [h.size(), nx, nz, nx * nz]}
	var hmin := 1e30
	var hmax := -1e30
	for v in h:
		hmin = minf(hmin, v)
		hmax = maxf(hmax, v)
	# material
	var mat := ShaderMaterial.new()
	mat.shader = load("res://addons/gg/shaders/%s.gdshader" % _shader_for(style))
	var splat_res: Array = []
	for i in range(args["splats"].size()):
		var img := Image.load_from_file(str(args["splats"][i]))
		if img == null:
			return {"ok": false, "error": "cannot load splat %s" % args["splats"][i]}
		if img.get_width() != nx or img.get_height() != nz:
			return {"ok": false, "error": "splat %s is %dx%d but terrain is %dx%d" % [args["splats"][i], img.get_width(), img.get_height(), nx, nz]}
		var tex := ImageTexture.create_from_image(img)
		var se := ResourceSaver.save(tex, "%s/splat_%d.res" % [gen, i])
		if se != OK:
			return {"ok": false, "error": "cannot save splat texture (%d)" % se}
		tex.take_over_path("%s/splat_%d.res" % [gen, i])
		mat.set_shader_parameter("splat_%d" % i, tex)
		splat_res.append(tex)
	if args["splats"].size() < 2:
		var blank := Image.create(nx, nz, false, Image.FORMAT_RGBA8)
		blank.fill(Color(0, 0, 0, 0))
		mat.set_shader_parameter("splat_1", ImageTexture.create_from_image(blank))
	var ncol: int = args["colors"].size()
	for i in range(ncol):
		var c: Array = args["colors"][i]
		mat.set_shader_parameter("layer_color_%d" % i, Color(c[0], c[1], c[2]))
	mat.set_shader_parameter("layer_count", ncol)
	mat.set_shader_parameter("terrain_size", Vector2(float(W["size_m"][0]), float(W["size_m"][1])))
	mat.set_shader_parameter("terrain_origin", Vector2.ZERO)
	if style["material"]["shading"] == "pbr":
		mat.set_shader_parameter("roughness_value", float(style["material"]["roughness"]))
	if style["material"]["shading"] == "toon":
		mat.set_shader_parameter("softness", float(style["material"].get("toon_softness", 0.15)))
	var me := ResourceSaver.save(mat, "%s/terrain_material.res" % gen)
	if me != OK:
		return {"ok": false, "error": "cannot save terrain material (%d)" % me}
	mat.take_over_path("%s/terrain_material.res" % gen)
	# chunks
	var root := Node3D.new()
	root.name = "Terrain"
	var chunk := int(args.get("chunk", 64))
	var count := 0
	var mesh_min := 1e30
	var mesh_max := -1e30
	var j0 := 0
	while j0 < nz - 1:
		var j1 := mini(j0 + chunk, nz - 1)
		var i0 := 0
		while i0 < nx - 1:
			var i1 := mini(i0 + chunk, nx - 1)
			var verts := PackedVector3Array()
			var norms := PackedVector3Array()
			var idx := PackedInt32Array()
			var cw := i1 - i0 + 1
			for j in range(j0, j1 + 1):
				for i in range(i0, i1 + 1):
					var y: float = h[j * nx + i]
					verts.append(Vector3(i * cell, y, j * cell))
					var hl: float = h[j * nx + maxi(i - 1, 0)]
					var hr: float = h[j * nx + mini(i + 1, nx - 1)]
					var hu: float = h[maxi(j - 1, 0) * nx + i]
					var hd: float = h[mini(j + 1, nz - 1) * nx + i]
					norms.append(Vector3(hl - hr, 2.0 * cell, hu - hd).normalized())
			for j in range(j1 - j0):
				for i in range(i1 - i0):
					var a := j * cw + i
					var b := a + 1
					var c := a + cw
					var d := c + 1
					idx.append_array([a, b, c, b, d, c])  # clockwise seen from above = front face in Godot
			var arrays := []
			arrays.resize(Mesh.ARRAY_MAX)
			arrays[Mesh.ARRAY_VERTEX] = verts
			arrays[Mesh.ARRAY_NORMAL] = norms
			arrays[Mesh.ARRAY_INDEX] = idx
			var mesh := ArrayMesh.new()
			mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
			mesh.surface_set_material(0, mat)
			var path := "%s/terrain_%d_%d.res" % [gen, i0, j0]
			var ce := ResourceSaver.save(mesh, path)
			if ce != OK:
				return {"ok": false, "error": "cannot save chunk mesh %s (%d)" % [path, ce]}
			mesh.take_over_path(path)
			var mi := MeshInstance3D.new()
			mi.name = "Chunk_%d_%d" % [i0, j0]
			mi.mesh = mesh
			root.add_child(mi)
			var bb := mesh.get_aabb()
			mesh_min = minf(mesh_min, bb.position.y)
			mesh_max = maxf(mesh_max, bb.position.y + bb.size.y)
			count += 1
			i0 = i1
		j0 = j1
	# collider: HeightMapShape3D is centred on its origin with 1-unit spacing, so scale x/z by cell and move to the middle
	var body := StaticBody3D.new()
	body.name = "Collider"
	var cs := CollisionShape3D.new()
	cs.name = "Shape"
	var hs := HeightMapShape3D.new()
	hs.map_width = nx
	hs.map_depth = nz
	hs.map_data = h
	cs.shape = hs
	body.add_child(cs)
	body.position = Vector3((nx - 1) * cell * 0.5, 0.0, (nz - 1) * cell * 0.5)
	body.scale = Vector3(cell, 1.0, cell)
	root.add_child(body)
	var saved := Save.save_scene(root, "res://levels/%s/terrain.tscn" % level)
	if not saved["ok"]:
		return saved
	# verify the collider against the data with real physics
	tree.root.add_child(root)
	await tree.physics_frame
	await tree.physics_frame
	var space := root.get_world_3d().direct_space_state
	var rng := RandomNumberGenerator.new()
	rng.seed = 11
	var max_err := 0.0
	var misses := 0
	for k in range(64):
		var i := rng.randi_range(1, nx - 2)
		var j := rng.randi_range(1, nz - 2)
		var q := PhysicsRayQueryParameters3D.create(Vector3(i * cell, hmax + 100.0, j * cell), Vector3(i * cell, hmin - 100.0, j * cell))
		var hit := space.intersect_ray(q)
		if hit.is_empty():
			misses += 1
		else:
			max_err = maxf(max_err, absf(hit["position"].y - float(h[j * nx + i])))
	root.queue_free()
	await tree.process_frame
	return {"ok": true, "data": {"scene": "res://levels/%s/terrain.tscn" % level, "chunks": count, "nodes": saved["nodes"],
		"collider_max_err": max_err, "raycast_misses": misses, "mesh_y": [mesh_min, mesh_max], "data_y": [hmin, hmax]}}
