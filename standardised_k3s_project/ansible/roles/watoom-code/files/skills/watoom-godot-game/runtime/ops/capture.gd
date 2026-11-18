extends RefCounted
## Render a scene (or a builder script) from named views and save PNGs.
## args: {scene|builder: "res://...", views: [{name, kind(3d|2d), position, look_at, fov, ortho_size, center, zoom}],
##        frames: int, size: [w,h], out_dir: "/abs"}
func run(tree: SceneTree, args: Dictionary) -> Dictionary:
	var warnings: Array = []
	var root: Window = tree.root
	var want := Vector2i(int(args.get("size", [1280, 720])[0]), int(args.get("size", [1280, 720])[1]))
	if args.has("internal"):
		# same as the project's stretch settings: render at the internal size, scale up by an integer with nearest filtering
		root.content_scale_size = Vector2i(int(args["internal"][0]), int(args["internal"][1]))
		root.content_scale_mode = Window.CONTENT_SCALE_MODE_VIEWPORT
		root.content_scale_aspect = Window.CONTENT_SCALE_ASPECT_KEEP
		root.content_scale_stretch = Window.CONTENT_SCALE_STRETCH_INTEGER
	var holder := Node.new()
	holder.name = "GGScene"
	root.add_child(holder)
	if args.has("scene"):
		var packed = load(str(args["scene"]))
		if packed == null:
			return {"ok": false, "error": "cannot load scene %s" % args["scene"]}
		holder.add_child(packed.instantiate())
	elif args.has("builder"):
		var bs = load(str(args["builder"]))
		if bs == null:
			return {"ok": false, "error": "cannot load builder %s" % args["builder"]}
		bs.new().build(holder, args.get("ctx", {}))
	else:
		return {"ok": false, "error": "capture needs scene or builder"}
	var frames := int(args.get("frames", 8))
	var views: Array = args.get("views", [])
	if views.is_empty():
		warnings.append("no views given: used the scene's own current camera")
		views = [{"name": "default", "kind": "scene"}]
	var files: Array = []
	var actual := Vector2i.ZERO
	for v in views:
		var cam: Node = null
		if v.get("kind", "3d") == "3d":
			var c := Camera3D.new()
			c.fov = float(v.get("fov", 60.0))
			if v.has("ortho_size"):
				c.projection = Camera3D.PROJECTION_ORTHOGONAL
				c.size = float(v["ortho_size"])
			holder.add_child(c)
			var p: Array = v.get("position", [0, 2, 5])
			var l: Array = v.get("look_at", [0, 0, 0])
			var up := Vector3.UP
			if v.has("ortho_size") and absf(float(p[0]) - float(l[0])) < 0.001 and absf(float(p[2]) - float(l[2])) < 0.001:
				up = Vector3.FORWARD  # looking straight down: pick a non-parallel up
			c.look_at_from_position(Vector3(p[0], p[1], p[2]), Vector3(l[0], l[1], l[2]), up)
			c.make_current()
			cam = c
		elif v.get("kind", "3d") == "2d":
			var c2 := Camera2D.new()
			holder.add_child(c2)
			var ctr: Array = v.get("center", [0, 0])
			c2.position = Vector2(ctr[0], ctr[1])
			var z := float(v.get("zoom", 1.0))
			c2.zoom = Vector2(z, z)
			c2.make_current()
			cam = c2
		for i in range(maxi(frames, 1)):
			await tree.process_frame
		var img: Image = root.get_texture().get_image()
		if img == null:
			return {"ok": false, "error": "viewport returned no image (is this run headless? use xvfb)"}
		img.convert(Image.FORMAT_RGB8)
		if args.has("internal") and img.get_size() != want:
			img.resize(want.x, want.y, Image.INTERPOLATE_NEAREST)
		actual = img.get_size()
		var path := "%s/%s.png" % [str(args["out_dir"]), str(v.get("name", "view"))]
		var err := img.save_png(path)
		if err != OK:
			return {"ok": false, "error": "save_png failed (%d): %s" % [err, path]}
		files.append({"name": str(v.get("name", "view")), "path": path})
		if cam != null:
			cam.queue_free()
			await tree.process_frame
	if actual != want:
		warnings.append("captured size %s != requested %s" % [actual, want])
	return {"ok": true, "data": {"files": files, "size": [actual.x, actual.y]}, "warnings": warnings}
