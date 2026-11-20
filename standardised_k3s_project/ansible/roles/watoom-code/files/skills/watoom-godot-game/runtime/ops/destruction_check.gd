extends RefCounted
## T-0066: prove a pre-fractured prop (game/destructible.gd) breaks under the existing gun path and behaves.
## A floor, a wall from args.model (Intact + Piece_* from fracture.py) standing on it, a shooter 4 m in front.
## Every shot is the gg_combat gun: a REAL PhysicsServer raycast -> collider.get_node("Combat") -> try_ability.
## Time is simulated: each physics frame is 1/physics_ticks_per_second s, so N frames = N/60 s whatever the host speed.
## args: {model: "res://...glb", max_health: 100, damage: 40}. data: {checks: [{name, ok, detail}], pieces: N}.
const Destructible := preload("res://addons/gg/game/destructible.gd")
const CombatComponent := preload("res://addons/gg/game/combat_component.gd")


func _frames(tree: SceneTree, n: int) -> void:
	for i in n:
		await tree.physics_frame


func _shoot(tree: SceneTree, shooter: Node, from: Vector3, to: Vector3, amount: float, now: float) -> Dictionary:
	var q := PhysicsRayQueryParameters3D.create(from, to)
	var hit := tree.root.get_world_3d().direct_space_state.intersect_ray(q)
	var col: Node = hit.get("collider")
	var target: Node = col.get_node_or_null("Combat") if col != null else null
	var r := {}
	if target != null:
		if col.has_method("hit_at"):
			col.hit_at(hit["position"], (to - from).normalized())
		r = shooter.get_node("Combat").try_ability("gun", {"kind": "damage", "amount": amount}, target, 0.0, now)
	return {"collider": col, "position": hit.get("position"), "result": r}


func run(tree: SceneTree, args: Dictionary) -> Dictionary:
	var path: String = args.get("model", "")
	if path == "" or not ResourceLoader.exists(path):
		return {"ok": false, "error": "args.model %s is not a resource in this project (gg_destruction.py init copies the test wall)" % path, "data": {}}
	var max_health: float = float(args.get("max_health", 100.0))
	var damage: float = float(args.get("damage", 40.0))
	var holder := Node3D.new()
	tree.root.add_child(holder)

	var floor := StaticBody3D.new()
	var fs := CollisionShape3D.new()
	fs.shape = BoxShape3D.new()
	fs.shape.size = Vector3(40, 1, 40)
	floor.add_child(fs)
	holder.add_child(floor)
	floor.global_position = Vector3(0, -0.5, 0)

	var shooter := Node3D.new()
	var sc := CombatComponent.new()
	sc.name = "Combat"
	shooter.add_child(sc)
	holder.add_child(shooter)

	var wall := Destructible.new()
	wall.name = "Wall"
	wall.model = load(path)
	wall.max_health = max_health
	holder.add_child(wall)
	await _frames(tree, 2)

	var rows: Array = []
	var n := wall.pieces_src.size()
	rows.append(["model has an Intact mesh and pieces", wall.intact != null and n >= 2, "pieces=%d" % n])
	if wall.intact == null or n < 2:
		holder.queue_free()
		return _verdict(rows, n)
	var box: AABB = wall.intact.global_transform * wall.intact.get_aabb()
	var inside := 0
	for p in wall.pieces_src:
		if box.grow(0.01).has_point(p.global_position):
			inside += 1
	rows.append(["every piece sits inside the intact mesh", inside == n, "%d of %d piece centres inside %s" % [inside, n, box]])

	# shoot at mid-height of the wall's face from 4 m in front (+Z side)
	var aim := box.get_center()
	var from := Vector3(aim.x, aim.y, box.end.z + 4.0)
	var to := Vector3(aim.x, aim.y, box.position.z - 4.0)
	var shots := int(ceil(max_health / damage))
	var s1 := _shoot(tree, shooter, from, to, damage, 0.0)
	rows.append(["the gun ray hits the intact wall's collider", s1["collider"] == wall, "collider=%s at %s" % [s1["collider"], s1["position"]]])
	await _frames(tree, 2)
	rows.append(["below the threshold it stays whole", not wall.is_broken and wall.intact.visible and wall.combat.attrs.health == max_health - damage,
		"health=%s broken=%s" % [wall.combat.attrs.health, wall.is_broken]])

	var before := {}
	for p in wall.pieces_src:
		before[String(p.name).trim_prefix("Piece_")] = p.global_position
	for i in range(1, shots):
		_shoot(tree, shooter, from, to, damage, float(i))
	await _frames(tree, 1)   # _physics_process sees dead and shatters (the push is applied, positions not yet integrated)
	var bodies: Array = wall.pieces
	# a piece may already have moved one frame at its own break velocity: the jump is what is left after that
	var dt := 1.0 / float(Engine.physics_ticks_per_second)
	var jump := 0.0
	var worst := ""
	for b in bodies:
		var k := String(b.name).trim_prefix("Debris_")
		var excess: float = b.global_position.distance_to(before.get(k, b.global_position)) - b.linear_velocity.length() * dt
		if excess > jump:
			jump = excess
			worst = "%s %s -> %s v=%s mass=%.1f scale=%s" % [k, before[k], b.global_position, b.linear_velocity, b.mass, b.global_transform.basis.get_scale()]
	rows.append(["lethal damage breaks it into rigid pieces", wall.is_broken and bodies.size() == n and bodies.all(func(b): return b is RigidBody3D),
		"shots=%d health=%s broken=%s bodies=%d" % [shots, wall.combat.attrs.health, wall.is_broken, bodies.size()]])
	rows.append(["the swap shows no jump (piece at its intact position)", jump < 0.05, "largest move beyond one frame of its own velocity %.3f m (%s)" % [jump, worst]])
	rows.append(["the intact mesh is hidden and its collider off", not wall.intact.visible, "intact visible=%s" % wall.intact.visible])

	var y0 := 0.0
	var z0 := 0.0
	for b in bodies:
		y0 += b.global_position.y
		z0 += b.global_position.z
	await _frames(tree, 240)   # 4 simulated seconds
	var y1 := 0.0
	var z1 := 0.0
	var lowest := INF
	var resting := 0
	for b in bodies:
		y1 += b.global_position.y
		z1 += b.global_position.z
		lowest = min(lowest, b.global_position.y)
		if b.sleeping or b.linear_velocity.length() < 0.2:
			resting += 1
	var m := float(bodies.size())
	rows.append(["the pieces fall", y1 / m < y0 / m - 0.2, "mean height %.2f -> %.2f m" % [y0 / m, y1 / m]])
	rows.append(["the shot pushes them away from the shooter", z1 / m < z0 / m, "mean z %.2f -> %.2f (shot travels -z)" % [z0 / m, z1 / m]])
	rows.append(["no piece falls through the floor", lowest > -0.3, "lowest piece centre %.2f m" % lowest])
	rows.append(["they settle", resting >= int(m * 0.8), "%d of %d at rest after 4 s" % [resting, int(m)]])
	var s2 := _shoot(tree, shooter, from, to, damage, 99.0)
	rows.append(["the same shot now passes where the wall stood", s2["collider"] != wall, "collider now %s" % [s2["collider"]]])

	holder.queue_free()
	return _verdict(rows, n)


func _verdict(rows: Array, n: int) -> Dictionary:
	var checks: Array = []
	var ok := true
	for row in rows:
		checks.append({"name": row[0], "ok": row[1], "detail": row[2]})
		ok = ok and row[1]
	return {"ok": ok, "error": null if ok else "one or more destruction checks failed", "data": {"checks": checks, "pieces": n}}
