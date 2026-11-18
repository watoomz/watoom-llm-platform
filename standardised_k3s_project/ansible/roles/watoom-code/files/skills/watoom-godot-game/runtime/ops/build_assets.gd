extends RefCounted
## Builds simple stylised plant, rock and tree scenes from primitives, in the project's style (flat, toon, pbr or unshaded material).
## args: {style, out_dir:"res://assets/gg", assets:[{name, kind, height, radius, colors:{trunk:[r,g,b], leaf:[r,g,b]}}]}
## kinds: conifer, broadleaf, palm, shrub, grass, flower, reed, rock. Each scene is a Node3D whose children are MeshInstance3D parts,
## origin at the base (y = 0 is the ground), metres, +Y up. Result data: assets [{name, scene, height_m, width_m, parts}].
const Save := preload("res://addons/gg/lib/save.gd")
const Style := preload("res://addons/gg/lib/style.gd")

var style: Dictionary

func _mat(c: Array) -> Material:
	var m: Material = Style.material(style, Color(c[0], c[1], c[2]), "solid")
	if m is StandardMaterial3D:
		(m as StandardMaterial3D).cull_mode = BaseMaterial3D.CULL_DISABLED
	return m

func _part(root: Node3D, nm: String, mesh: Mesh, mat: Material, pos: Vector3, rot_deg := Vector3.ZERO, scl := Vector3.ONE) -> void:
	var mi := MeshInstance3D.new()
	mi.name = nm
	mi.mesh = mesh
	mi.material_override = mat
	mi.position = pos
	mi.rotation_degrees = rot_deg
	mi.scale = scl
	root.add_child(mi)

func _cyl(top: float, bottom: float, h: float, seg := 6) -> CylinderMesh:
	var c := CylinderMesh.new()
	c.top_radius = top
	c.bottom_radius = bottom
	c.height = h
	c.radial_segments = seg
	c.rings = 1
	return c

func _sph(r: float, seg := 7, rings := 4) -> SphereMesh:
	var s := SphereMesh.new()
	s.radius = r
	s.height = r * 2.0
	s.radial_segments = seg
	s.rings = rings
	return s

func _make(a: Dictionary) -> Node3D:
	var h := float(a["height"])
	var r := float(a["radius"])
	var trunk := _mat(a["colors"]["trunk"]) if a["colors"].has("trunk") else null
	var leaf := _mat(a["colors"]["leaf"])
	var root := Node3D.new()
	root.name = str(a["name"])
	match str(a["kind"]):
		"conifer":
			_part(root, "Trunk", _cyl(r * 0.12, r * 0.16, h * 0.3), trunk, Vector3(0, h * 0.15, 0))
			for i in range(3):
				var t := float(i) / 3.0
				_part(root, "Cone%d" % i, _cyl(0.0, r * (1.0 - t * 0.45), h * 0.42), leaf, Vector3(0, h * (0.28 + t * 0.3) + h * 0.21, 0))
		"broadleaf":
			_part(root, "Trunk", _cyl(r * 0.1, r * 0.15, h * 0.5), trunk, Vector3(0, h * 0.25, 0))
			_part(root, "Crown", _sph(r), leaf, Vector3(0, h * 0.68, 0), Vector3.ZERO, Vector3(1.0, (h * 0.5) / (r * 2.0) * 1.0, 1.0))
		"palm":
			_part(root, "Trunk", _cyl(r * 0.07, r * 0.1, h * 0.85), trunk, Vector3(0.12 * h * 0.1, h * 0.42, 0), Vector3(0, 0, -4))
			for i in range(6):
				var box := BoxMesh.new()
				box.size = Vector3(r * 1.9, 0.02, r * 0.35)
				var ang := float(i) * 60.0
				var p := Vector3(0.3, h * 0.88, 0).rotated(Vector3.UP, deg_to_rad(ang))
				_part(root, "Frond%d" % i, box, leaf, p + Vector3(0, 0, 0) + Vector3(cos(deg_to_rad(ang)), 0, -sin(deg_to_rad(ang))) * r * 0.9, Vector3(0, ang, -18))
		"shrub":
			for i in range(3):
				var o := Vector3(cos(i * 2.1) * r * 0.45, h * 0.35, sin(i * 2.1) * r * 0.45)
				_part(root, "Blob%d" % i, _sph(r * (0.55 + 0.1 * i)), leaf, o, Vector3.ZERO, Vector3(1, h / (r * 1.6), 1))
		"grass":
			for i in range(7):
				var a_ := float(i) * 51.4
				var lean := 10.0 + float(i % 3) * 8.0
				var o := Vector3(cos(deg_to_rad(a_)) * r * 0.5, h * 0.5, sin(deg_to_rad(a_)) * r * 0.5)
				_part(root, "Blade%d" % i, _cyl(0.0, r * 0.12, h, 4), leaf, o, Vector3(lean * sin(deg_to_rad(a_)), 0, -lean * cos(deg_to_rad(a_))))
		"flower":
			_part(root, "Stem", _cyl(0.01, 0.015, h * 0.8, 4), trunk, Vector3(0, h * 0.4, 0))
			_part(root, "Head", _sph(r, 6, 3), leaf, Vector3(0, h * 0.85, 0))
		"reed":
			for i in range(6):
				var a_ := float(i) * 60.0
				var o := Vector3(cos(deg_to_rad(a_)) * r * 0.4, h * 0.5, sin(deg_to_rad(a_)) * r * 0.4)
				_part(root, "Reed%d" % i, _cyl(0.0, r * 0.1, h * (0.8 + 0.07 * (i % 3)), 4), leaf, o, Vector3(5.0 * sin(deg_to_rad(a_)), 0, -5.0 * cos(deg_to_rad(a_))))
		"rock":
			_part(root, "Rock", _sph(r, 6, 3), leaf, Vector3(0, h * 0.4, 0), Vector3(0, 20, 0), Vector3(1.0, h / (r * 2.0) * 0.8, 0.85))
		_:
			return null
	return root

func _bounds(n: Node, xf: Transform3D, acc: Array) -> void:
	var t := xf
	if n is Node3D:
		t = xf * (n as Node3D).transform
	if n is MeshInstance3D and (n as MeshInstance3D).mesh != null:
		var bb: AABB = t * (n as MeshInstance3D).mesh.get_aabb()
		acc[0] = bb if acc[0] == null else (acc[0] as AABB).merge(bb)
	for k in n.get_children():
		_bounds(k, t, acc)

func run(tree: SceneTree, args: Dictionary) -> Dictionary:
	style = args["style"]
	var out_dir := str(args["out_dir"])
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(out_dir))
	var done: Array = []
	for a in args["assets"]:
		var root := _make(a)
		if root == null:
			return {"ok": false, "error": "unknown asset kind '%s' for %s (have conifer, broadleaf, palm, shrub, grass, flower, reed, rock)" % [a["kind"], a["name"]]}
		root.set_meta("gg_family", str(a["name"]))
		var acc: Array = [null]
		_bounds(root, Transform3D.IDENTITY, acc)
		var bb: AABB = acc[0]
		var path := "%s/%s.tscn" % [out_dir, a["name"]]
		var saved := Save.save_scene(root, path)
		if not saved["ok"]:
			return saved
		done.append({"name": a["name"], "scene": path, "height_m": bb.size.y, "width_m": maxf(bb.size.x, bb.size.z), "base_y": bb.position.y, "parts": root.get_child_count()})
		root.free()
	return {"ok": true, "data": {"assets": done}}
