extends RefCounted
## T-0070 vertical slice: a REAL running scene (CharacterBody3D + CollisionShape3D + CombatComponent as an
## actual scene-tree child, ticked through physics_frame), not the synthetic combat_check.gd scenario of bare
## RefCounted objects. One attacker, one dummy target, three abilities: sword (melee range check), gun (a real
## PhysicsServer raycast against the dummy's real collider), spell (instant effect at range). No animation,
## VFX or input binding yet (T-0068/T-0069) -- this proves the combat core actually works wired into physics.
## args: {} (none yet). data: {checks: [{name, ok, detail}]}.
const CombatComponent := preload("res://addons/gg/game/combat_component.gd")


func _body(name: String, team: int, max_health: float) -> CharacterBody3D:
	var body := CharacterBody3D.new()
	body.name = name
	var shape := CollisionShape3D.new()
	shape.shape = CapsuleShape3D.new()
	shape.shape.radius = 0.35
	shape.shape.height = 1.8
	body.add_child(shape)
	var combat := CombatComponent.new()
	combat.name = "Combat"
	combat.attrs.team = team
	combat.attrs.max_health = max_health
	combat.attrs.health = max_health
	body.add_child(combat)
	return body


func run(tree: SceneTree, args: Dictionary) -> Dictionary:
	var holder := Node3D.new()
	tree.root.add_child(holder)
	var player := _body("Player", 0, 100.0)
	var dummy := _body("Dummy", 1, 150.0)
	holder.add_child(player)
	holder.add_child(dummy)
	player.global_position = Vector3.ZERO
	dummy.global_position = Vector3(0, 0, -2.5)   # 2.5 m ahead: inside melee range, well inside gun range
	await tree.physics_frame
	await tree.physics_frame

	var player_combat: Node = player.get_node("Combat")
	var dummy_combat: Node = dummy.get_node("Combat")
	var rows: Array = []

	# sword: melee range check against the real transform distance, then try_ability
	var dist: float = player.global_position.distance_to(dummy.global_position)
	var in_melee_range := dist <= 3.0
	var r1: Dictionary = {}
	if in_melee_range:
		r1 = player_combat.try_ability("sword", {"kind": "damage", "amount": 30.0}, dummy_combat, 1.0, 0.0)
	rows.append(["sword hits in range", in_melee_range and r1.get("ok", true) != false and dummy_combat.attrs.health == 120.0, "dist=%.1f health=%s result=%s" % [dist, dummy_combat.attrs.health, r1]])

	var r2: Dictionary = player_combat.try_ability("sword", {"kind": "damage", "amount": 30.0}, dummy_combat, 1.0, 0.2)
	rows.append(["sword cooldown blocks an immediate repeat", r2.get("ok", true) == false and dummy_combat.attrs.health == 120.0, "result=%s" % [r2]])

	# gun: a REAL PhysicsServer raycast from the player, forward (-Z), against the dummy's REAL collider
	var space := tree.root.get_world_3d().direct_space_state
	var from: Vector3 = player.global_position + Vector3(0, 0.5, 0)   # mid-torso height: the capsule's hemispherical cap starts near its top, a ray grazing the cap pole can miss
	var to: Vector3 = from + player.global_transform.basis.z * -10.0
	var query := PhysicsRayQueryParameters3D.create(from, to)
	query.exclude = [player.get_rid()]
	var hit := space.intersect_ray(query)
	var hit_combat: Node = (hit.get("collider") as Node).get_node_or_null("Combat") if hit.get("collider") != null else null
	var r3: Dictionary = {}
	if hit_combat != null:
		r3 = player_combat.try_ability("gun", {"kind": "damage", "amount": 25.0}, hit_combat, 0.1, 1.0)
	rows.append(["gun raycast hits the dummy's real collider", hit.get("collider") == dummy, "raycast collider=%s" % [hit.get("collider")]])
	rows.append(["gun shot through the raycast deals damage", r3.get("ok", true) != false and dummy_combat.attrs.health == 95.0, "health=%s result=%s" % [dummy_combat.attrs.health, r3]])

	# spell: instant effect at range, no collider/raycast needed
	var r4: Dictionary = player_combat.try_ability("spell", {"kind": "damage", "amount": 40.0}, dummy_combat, 2.0, 2.0)
	rows.append(["spell lands at range", r4.get("ok", true) != false and dummy_combat.attrs.health == 55.0, "health=%s result=%s" % [dummy_combat.attrs.health, r4]])

	# finish it off with another sword swing once its cooldown has elapsed
	var r5: Dictionary = player_combat.try_ability("sword", {"kind": "damage", "amount": 60.0}, dummy_combat, 1.0, 3.0)
	rows.append(["the dummy dies once health reaches 0", dummy_combat.attrs.dead == true and dummy_combat.attrs.health == 0.0, "health=%s dead=%s result=%s" % [dummy_combat.attrs.health, dummy_combat.attrs.dead, r5]])

	holder.queue_free()
	var checks: Array = []
	var ok := true
	for row in rows:
		checks.append({"name": row[0], "ok": row[1], "detail": row[2]})
		ok = ok and row[1]
	return {"ok": ok, "error": null if ok else "one or more vertical-slice checks failed", "data": {"checks": checks}}
