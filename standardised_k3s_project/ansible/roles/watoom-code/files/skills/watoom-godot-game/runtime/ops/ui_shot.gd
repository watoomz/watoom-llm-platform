extends RefCounted
## Render one UI scene into a TRANSPARENT SubViewport and save the PNG (alpha kept: what the screen would show through).
## args: {scene: "res://...", size: [w, h], frames: 12, out: "/abs/name.png", fit: "full"|"none"}
## data: {size, png, census: {...}}; the census reads the controls back so layout faults are numbers, not guesses.
func _walk(n: Node, out: Array) -> void:
	out.append(n)
	for c in n.get_children():
		_walk(c, out)

func run(tree: SceneTree, args: Dictionary) -> Dictionary:
	var sz: Array = args.get("size", [1280, 240])
	var size := Vector2i(int(sz[0]), int(sz[1]))
	var packed = load(str(args.get("scene", "")))
	if packed == null:
		return {"ok": false, "error": "cannot load scene %s" % args.get("scene", "")}
	var vp := SubViewport.new()
	vp.size = size
	vp.transparent_bg = true
	vp.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	tree.root.add_child(vp)
	var inst: Node = packed.instantiate()
	vp.add_child(inst)
	if inst is Control and str(args.get("fit", "full")) == "full":
		(inst as Control).set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for i in int(args.get("frames", 12)):
		await tree.process_frame
	await RenderingServer.frame_post_draw
	var img: Image = vp.get_texture().get_image()
	var err := img.save_png(str(args["out"]))
	if err != OK:
		return {"ok": false, "error": "cannot save %s (error %d)" % [args["out"], err]}
	var nodes: Array = []
	_walk(inst, nodes)
	var labels: Array = []
	var buttons: Array = []
	var bars := 0
	var rects := 0
	var viewports: Array = []
	var clipped: Array = []
	var small: Array = []
	var empty_labels := 0
	var vrect := Rect2(Vector2.ZERO, Vector2(size))
	for n in nodes:
		if not (n is Control):
			continue
		var c: Control = n
		if not c.is_visible_in_tree():
			continue
		var r: Rect2 = c.get_global_rect()
		var row := {"name": str(c.name), "rect": [r.position.x, r.position.y, r.size.x, r.size.y]}
		if r.size.x > 0 and r.size.y > 0 and not vrect.grow(1.0).encloses(r):
			clipped.append(row)
		if c is Label:
			var l: Label = c
			if l.text.strip_edges() == "":
				empty_labels += 1
			else:
				row["text"] = l.text.substr(0, 40)
				row["font_size"] = l.get_theme_font_size("font_size")
				labels.append(row)
		elif c is BaseButton:
			row["text"] = (c as Button).text.substr(0, 40) if c is Button else ""
			buttons.append(row)
			if minf(r.size.x, r.size.y) < 24.0:
				small.append(row)
		elif c is ProgressBar:
			bars += 1
		elif c is TextureRect:
			rects += 1
		elif c is SubViewportContainer:
			viewports.append(row)
	return {"ok": true, "data": {"size": [size.x, size.y], "png": str(args["out"]),
		"census": {"controls": nodes.size(), "labels": labels.slice(0, 60), "buttons": buttons.slice(0, 60), "progress_bars": bars, "texture_rects": rects,
			"model_views": viewports.slice(0, 20), "clipped": clipped.slice(0, 20), "small_buttons": small.slice(0, 20), "empty_labels": empty_labels}}}
