extends RefCounted
## Drops the REAL player capsule onto the REAL terrain collider at each point and reports where it comes to rest. Measures the collider against the data.
## args: {scenes:[res://...terrain.tscn, colliders...], player_scene, points:[[x,z,y_start],...], ticks:120}
## Data: points [{x, z, rest_y, on_floor, ticks}], physics_engine.
func run(tree: SceneTree, args: Dictionary) -> Dictionary:
	var holder := Node3D.new()
	tree.root.add_child(holder)
	for s in args["scenes"]:
		var packed = load(str(s))
		if packed == null:
			return {"ok": false, "error": "cannot load %s" % s}
		holder.add_child((packed as PackedScene).instantiate())
	var pp = load(str(args["player_scene"]))
	if pp == null:
		return {"ok": false, "error": "cannot load %s" % args["player_scene"]}
	var player: CharacterBody3D = (pp as PackedScene).instantiate()
	holder.add_child(player)
	await tree.physics_frame
	var out: Array = []
	for pt in args["points"]:
		player.velocity = Vector3.ZERO
		player.global_position = Vector3(pt[0], pt[2], pt[1])
		var still := 0
		var last_y := 1e9
		var n := 0
		while n < int(args.get("ticks", 120)):
			await tree.physics_frame
			n += 1
			if player.is_on_floor() and absf(player.global_position.y - last_y) < 0.0005:
				still += 1
				if still >= 5:
					break
			else:
				still = 0
			last_y = player.global_position.y
		out.append({"x": pt[0], "z": pt[1], "rest_y": player.global_position.y, "on_floor": player.is_on_floor(), "ticks": n})
	holder.queue_free()
	return {"ok": true, "data": {"points": out, "physics_engine": str(ProjectSettings.get_setting("physics/3d/physics_engine", "DEFAULT"))}}
