extends RefCounted
## The style probe scene: the SAME geometry for every preset, so only the style differs.
## build(parent, ctx): ctx.style = resolved style dict; ctx.dimension = "3d" | "2d".
const Style := preload("res://addons/gg/lib/style.gd")

func build(parent: Node, ctx: Dictionary = {}) -> void:
	var style: Dictionary = ctx["style"]
	if str(ctx.get("dimension", "3d")) == "2d":
		_build_2d(parent, style)
	else:
		_build_3d(parent, style)
	var post := Style.palette_layer(style)
	if post != null:
		parent.add_child(post)

func _mesh(parent: Node, mesh: Mesh, color: Color, pos: Vector3, style: Dictionary, nm: String) -> MeshInstance3D:
	var m := MeshInstance3D.new()
	m.name = nm
	m.mesh = mesh
	m.material_override = Style.material(style, color)
	m.position = pos
	parent.add_child(m)
	return m

func _build_3d(parent: Node, style: Dictionary) -> void:
	var seg: int = int(style["geometry"]["mesh_segments"])
	var we := WorldEnvironment.new()
	we.name = "WorldEnvironment"
	we.environment = Style.environment(style)
	parent.add_child(we)
	parent.add_child(Style.sun(style))
	# ground: three layers (grass base, dirt, sand), 40 m patch
	var g := PlaneMesh.new(); g.size = Vector2(40, 40)
	_mesh(parent, g, Color(0.30, 0.55, 0.25), Vector3(0, 0, 0), style, "Grass")
	var dirt := CylinderMesh.new(); dirt.top_radius = 6.0; dirt.bottom_radius = 6.0; dirt.height = 0.02; dirt.radial_segments = maxi(seg, 8)
	_mesh(parent, dirt, Color(0.45, 0.32, 0.20), Vector3(-6, 0.01, -4), style, "Dirt")
	var sand := CylinderMesh.new(); sand.top_radius = 5.0; sand.bottom_radius = 5.0; sand.height = 0.02; sand.radial_segments = maxi(seg, 8)
	_mesh(parent, sand, Color(0.85, 0.78, 0.52), Vector3(8, 0.02, -2), style, "Sand")
	# reference cards (18 percent grey, white, black) standing up facing the camera
	var card := BoxMesh.new(); card.size = Vector3(1.4, 1.4, 0.06)
	_mesh(parent, card, Color(0.46, 0.46, 0.46), Vector3(-2.2, 0.7, 2.0), style, "GreyCard")
	_mesh(parent, card, Color(0.95, 0.95, 0.95), Vector3(-0.7, 0.7, 2.0), style, "WhiteCard")
	_mesh(parent, card, Color(0.04, 0.04, 0.04), Vector3(0.8, 0.7, 2.0), style, "BlackCard")
	# six colour chips
	var chips := [Color(0.9, 0.1, 0.1), Color(0.1, 0.8, 0.2), Color(0.1, 0.2, 0.9), Color(0.1, 0.8, 0.9), Color(0.9, 0.1, 0.8), Color(0.95, 0.85, 0.1)]
	var chip := BoxMesh.new(); chip.size = Vector3(0.6, 0.6, 0.06)
	for i in range(6):
		_mesh(parent, chip, chips[i], Vector3(-2.0 + i * 0.7, 0.3, 3.2), style, "Chip%d" % i)
	# sphere, faceted rock, tree
	var sp := SphereMesh.new(); sp.radius = 0.8; sp.height = 1.6; sp.radial_segments = seg; sp.rings = maxi(seg / 2, 3)
	_mesh(parent, sp, Color(0.75, 0.75, 0.78), Vector3(2.6, 0.8, 1.0), style, "Sphere")
	var rock := SphereMesh.new(); rock.radius = 0.9; rock.height = 1.4; rock.radial_segments = 6; rock.rings = 3
	_mesh(parent, rock, Color(0.45, 0.43, 0.42), Vector3(4.4, 0.6, 0.0), style, "Rock")
	var trunk := CylinderMesh.new(); trunk.top_radius = 0.18; trunk.bottom_radius = 0.24; trunk.height = 2.0; trunk.radial_segments = maxi(seg / 2, 5)
	_mesh(parent, trunk, Color(0.40, 0.26, 0.15), Vector3(-5.0, 1.0, -2.0), style, "Trunk")
	var crown := CylinderMesh.new(); crown.top_radius = 0.0; crown.bottom_radius = 1.4; crown.height = 3.2; crown.radial_segments = maxi(seg / 2, 6)
	_mesh(parent, crown, Color(0.15, 0.45, 0.18), Vector3(-5.0, 3.4, -2.0), style, "Crown")
	# water
	var wq := PlaneMesh.new(); wq.size = Vector2(10, 6)
	var wm := _mesh(parent, wq, Style.water_color(style), Vector3(2.0, 0.04, -7.0), style, "Water")
	wm.material_override = Style.material(style, Style.water_color(style))

func _tile_image(w: int, h: int, cols: Array, rng: RandomNumberGenerator) -> Image:
	var img := Image.create(w, h, false, Image.FORMAT_RGB8)
	for y in range(h):
		for x in range(w):
			var base: Color = cols[0]
			if y > h * 0.62:
				base = cols[1]          # dirt field
			if x > w * 0.6 and y < h * 0.45:
				base = cols[2]          # pond
			if x > w * 0.55 and x < w * 0.62 and y < h * 0.45:
				base = cols[3]          # sand edge
			if rng.randf() < 0.06:
				base = base.darkened(0.15)
			img.set_pixel(x, y, base)
	return img

func _build_2d(parent: Node, style: Dictionary) -> void:
	var pal: Array = style["material"].get("palette") if style["material"].get("palette") != null else []
	var cols: Array = []
	for i in [6, 1, 9, 4]:
		cols.append(Style.hexcol(pal[i]) if pal.size() > i else [Color(0.3, 0.6, 0.3), Color(0.5, 0.3, 0.2), Color(0.2, 0.4, 0.8), Color(0.9, 0.8, 0.5)][cols.size()])
	var rng := RandomNumberGenerator.new()
	rng.seed = 7
	var sp := Sprite2D.new()
	sp.name = "TileField"
	sp.centered = false
	sp.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	sp.texture = ImageTexture.create_from_image(_tile_image(320, 180, cols, rng))
	parent.add_child(sp)
	var tree := Image.create(16, 24, false, Image.FORMAT_RGBA8)
	tree.fill(Color(0, 0, 0, 0))
	for y in range(24):
		for x in range(16):
			if y < 14 and absi(x - 8) <= 1 + y / 2:
				tree.set_pixel(x, y, Style.hexcol(pal[7]) if pal.size() > 7 else Color.DARK_GREEN)
			elif y >= 14 and absi(x - 8) < 2:
				tree.set_pixel(x, y, Style.hexcol(pal[2]) if pal.size() > 2 else Color.SADDLE_BROWN)
	var tt := ImageTexture.create_from_image(tree)
	for p in [Vector2(40, 50), Vector2(90, 30), Vector2(60, 100)]:
		var t := Sprite2D.new()
		t.texture = tt
		t.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		t.position = p
		parent.add_child(t)
	var cam := ColorRect.new()  # clear colour reference swatch
	cam.name = "Swatch"
	cam.color = Style.hexcol(pal[13]) if pal.size() > 13 else Color.GRAY
	cam.position = Vector2(8, 150)
	cam.size = Vector2(24, 20)
	parent.add_child(cam)
