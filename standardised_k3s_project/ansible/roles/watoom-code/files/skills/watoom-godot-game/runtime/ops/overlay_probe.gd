extends RefCounted
## Run the project's main scene for a few frames and read the overlay window state back from the engine.
## args: {scene: "" (default: the project's main scene), frames: 20}
## data: requested flags and geometry as the ENGINE reports them. It does not prove a desktop compositor shows them: see gg-ui.md.
func run(tree: SceneTree, args: Dictionary) -> Dictionary:
	var scene_path := str(args.get("scene", ""))
	if scene_path == "":
		scene_path = str(ProjectSettings.get_setting("application/run/main_scene", ""))
	if scene_path == "":
		return {"ok": false, "error": "the project has no application/run/main_scene and no scene was given"}
	var packed = load(scene_path)
	if packed == null:
		return {"ok": false, "error": "cannot load scene %s" % scene_path}
	var inst: Node = packed.instantiate()
	tree.root.add_child(inst)
	for i in int(args.get("frames", 20)):
		await tree.process_frame
	var w: Window = tree.root
	var screen := DisplayServer.window_get_current_screen()
	var usable := DisplayServer.screen_get_usable_rect(screen)
	return {"ok": true, "data": {"scene": scene_path,
		"flags": {"borderless": DisplayServer.window_get_flag(DisplayServer.WINDOW_FLAG_BORDERLESS), "always_on_top": DisplayServer.window_get_flag(DisplayServer.WINDOW_FLAG_ALWAYS_ON_TOP),
			"transparent": DisplayServer.window_get_flag(DisplayServer.WINDOW_FLAG_TRANSPARENT), "mouse_passthrough": DisplayServer.window_get_flag(DisplayServer.WINDOW_FLAG_MOUSE_PASSTHROUGH)},
		"window": {"position": [w.position.x, w.position.y], "size": [w.size.x, w.size.y]},
		"screen": {"size": [DisplayServer.screen_get_size(screen).x, DisplayServer.screen_get_size(screen).y], "usable": [usable.position.x, usable.position.y, usable.size.x, usable.size.y]},
		"passthrough_points": w.mouse_passthrough_polygon.size(),
		"viewport_transparent_bg": w.transparent_bg,
		"project": {"per_pixel_transparency": bool(ProjectSettings.get_setting("display/window/per_pixel_transparency/allowed", false)),
			"size_transparent": bool(ProjectSettings.get_setting("display/window/size/transparent", false)),
			"borderless": bool(ProjectSettings.get_setting("display/window/size/borderless", false)),
			"always_on_top": bool(ProjectSettings.get_setting("display/window/size/always_on_top", false)),
			"transparent_background": bool(ProjectSettings.get_setting("rendering/viewport/transparent_background", false))}}}
