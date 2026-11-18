extends RefCounted
## T-0071: proves game/pickup.gd works live in a real SceneTree -- a real CharacterBody3D player overlapping
## a real Area3D pickup, Area3D's own physics-driven body_entered signal (not a scripted call), changing the
## player's CombatComponent attrs and then despawning (one-shot) or respawning (timed) for real.
## args: {}. data: {checks: [{name, ok, detail}]}.
const CombatComponent := preload("res://addons/gg/game/combat_component.gd")
const Pickup := preload("res://addons/gg/game/pickup.gd")


func _player(max_ammo: int, ammo: int, max_mana: float, mana: float) -> CharacterBody3D:
	var body := CharacterBody3D.new()
	body.name = "Player"
	var shape := CollisionShape3D.new()
	shape.shape = CapsuleShape3D.new()
	shape.shape.radius = 0.35
	shape.shape.height = 1.8
	body.add_child(shape)
	var combat := CombatComponent.new()
	combat.name = "Combat"
	combat.attrs.team = 0
	combat.attrs.max_ammo = max_ammo
	combat.attrs.ammo = ammo
	combat.attrs.max_mana = max_mana
	combat.attrs.mana = mana
	body.add_child(combat)
	return body


func _pickup(effect: Dictionary, respawn_s: float) -> Area3D:
	var area := Pickup.new()
	area.name = "Pickup"
	area.effect = effect
	area.respawn_s = respawn_s
	var shape := CollisionShape3D.new()
	shape.shape = SphereShape3D.new()
	shape.shape.radius = 0.5
	area.add_child(shape)
	return area


func run(tree: SceneTree, args: Dictionary) -> Dictionary:
	var holder := Node3D.new()
	tree.root.add_child(holder)

	var ammo_player := _player(60, 10, 100.0, 100.0)
	var ammo_pickup := _pickup({"kind": "grant", "resource": "ammo", "amount": 100}, 0.0)
	holder.add_child(ammo_player)
	holder.add_child(ammo_pickup)
	ammo_player.global_position = Vector3.ZERO
	ammo_pickup.global_position = Vector3.ZERO  # fully overlapping: this checks the signal fires, not positioning

	var respawn_player := _player(0, 0, 100.0, 10.0)
	var respawn_pickup := _pickup({"kind": "grant", "resource": "mana", "amount": 50}, 2.0)
	holder.add_child(respawn_player)
	holder.add_child(respawn_pickup)
	respawn_player.global_position = Vector3(10, 0, 0)
	respawn_pickup.global_position = Vector3(10, 0, 0)

	await tree.physics_frame
	await tree.physics_frame
	await tree.physics_frame
	await tree.process_frame   # set_deferred("monitoring", ...) applies at the next idle frame, not the next physics tick
	await tree.process_frame

	var rows: Array = []
	var ammo_combat: Node = ammo_player.get_node("Combat")
	rows.append(["walking into an ammo pickup grants ammo, clamped at max", ammo_combat.attrs.ammo == 60, "ammo=%s" % ammo_combat.attrs.ammo])
	rows.append(["a one-shot pickup frees itself after being collected", not is_instance_valid(ammo_pickup) or ammo_pickup.get_parent() == null, "valid=%s in_tree=%s" % [is_instance_valid(ammo_pickup), is_instance_valid(ammo_pickup) and ammo_pickup.is_inside_tree()]])

	var respawn_combat: Node = respawn_player.get_node("Combat")
	rows.append(["the first mana pickup grants mana", respawn_combat.attrs.mana == 60.0, "mana=%s" % respawn_combat.attrs.mana])
	rows.append(["a respawning pickup disables monitoring right after collection", respawn_pickup.monitoring == false, "monitoring=%s" % respawn_pickup.monitoring])

	# drain it back down so a second grant is visible, then wait (real wall time, not a frame count -- a
	# physics/process frame's wall-clock cost varies with engine overhead) for the real respawn timer to fire
	respawn_combat.attrs.mana = 10.0
	var respawned := false
	var start_ms := Time.get_ticks_msec()
	while Time.get_ticks_msec() - start_ms < 8000:
		await tree.process_frame
		if respawn_pickup.monitoring:
			respawned = true
			break
	rows.append(["the pickup's monitoring re-enables after its respawn timer", respawned, "waited %d ms" % (Time.get_ticks_msec() - start_ms)])

	await tree.physics_frame
	await tree.physics_frame
	rows.append(["the respawned pickup grants mana again", respawn_combat.attrs.mana == 60.0, "mana=%s" % respawn_combat.attrs.mana])

	holder.queue_free()
	var checks: Array = []
	var ok := true
	for row in rows:
		checks.append({"name": row[0], "ok": row[1], "detail": row[2]})
		ok = ok and row[1]
	return {"ok": ok, "error": null if ok else "one or more pickup checks failed", "data": {"checks": checks}}
