extends RefCounted
## RUNS a level with scripted input and records a per-physics-tick trace. Verdicts are computed in Python from the trace (never here).
## args: {scene, script:[{ticks, press:[actions], mouse_dx}], shots:{start:"/abs/a.png", end:"/abs/b.png"}, trace:"/abs/trace.json", settle_ticks}
## Each trace row: [tick, x, y_feet, z, yaw_deg, on_floor, vy, cam_x, cam_y, cam_z]. Data: physics_ticks, process_frames, physics_engine, camera_current, action_seen,
## mouse_events, scripted_ticks.
func _shot(tree: SceneTree, path: String) -> bool:
	var img := tree.root.get_viewport().get_texture().get_image()
	return img != null and img.save_png(path) == OK

func run(tree: SceneTree, args: Dictionary) -> Dictionary:
	var packed = load(str(args["scene"]))
	if packed == null:
		return {"ok": false, "error": "cannot load %s" % args["scene"]}
	var holder := Node3D.new()
	holder.name = "GGSmoke"
	tree.root.add_child(holder)
	var level: Node = (packed as PackedScene).instantiate()
	holder.add_child(level)
	var player := level.get_node_or_null("Player") as CharacterBody3D
	if player == null:
		return {"ok": false, "error": "the level has no node named Player"}
	var missing: Array = []
	for a in ["move_forward", "move_back", "move_left", "move_right", "jump"]:
		if not InputMap.has_action(a):
			missing.append(a)
	if not missing.is_empty():
		return {"ok": false, "error": "InputMap is missing actions %s (run gg_style.py apply)" % str(missing)}
	var rows: Array = []
	var p0 := Engine.get_physics_frames()
	var f0 := Engine.get_process_frames()
	var tick := 0
	var shot_start_done := false
	var total := 0
	for step in args["script"]:
		total += int(step["ticks"])
	var settle := int(args.get("settle_ticks", 60))
	for step in args["script"]:
		var press: Array = step.get("press", [])
		var dx := float(step.get("mouse_dx", 0.0))
		for a in press:
			Input.action_press(a)
		if dx != 0.0:
			var ev := InputEventMouseMotion.new()
			ev.relative = Vector2(dx, 0.0)
			ev.position = Vector2(100, 100)
			Input.parse_input_event(ev)
		for i in range(int(step["ticks"])):
			await tree.physics_frame
			tick += 1
			var cam := tree.root.get_viewport().get_camera_3d()
			var cp := cam.global_position if cam != null else Vector3(NAN, NAN, NAN)
			rows.append([tick, player.global_position.x, player.global_position.y, player.global_position.z, rad_to_deg(player.global_rotation.y), player.is_on_floor(), player.velocity.y, cp.x, cp.y, cp.z])
			if not shot_start_done and tick >= settle:
				shot_start_done = true
				await RenderingServer.frame_post_draw
				if not _shot(tree, str(args["shots"]["start"])):
					return {"ok": false, "error": "could not save the start screenshot"}
		for a in press:
			Input.action_release(a)
	await RenderingServer.frame_post_draw
	if not _shot(tree, str(args["shots"]["end"])):
		return {"ok": false, "error": "could not save the end screenshot"}
	var f := FileAccess.open(str(args["trace"]), FileAccess.WRITE)
	if f == null:
		return {"ok": false, "error": "cannot write %s" % args["trace"]}
	f.store_string(JSON.stringify(rows))
	f.close()
	var cam2 := tree.root.get_viewport().get_camera_3d()
	var data := {"physics_ticks": Engine.get_physics_frames() - p0, "process_frames": Engine.get_process_frames() - f0, "scripted_ticks": total,
		"physics_engine": str(ProjectSettings.get_setting("physics/3d/physics_engine", "DEFAULT")), "camera_current": cam2 != null and cam2.current,
		"action_seen": player.get("action_seen"), "mouse_events": player.get("mouse_events")}
	holder.queue_free()
	return {"ok": true, "data": data}
