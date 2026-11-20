extends RefCounted
## T-0066: a first-person shooter slice driven through REAL input (Input.action_press / parse_input_event):
## player_3d.gd + camera_rig.gd (first_person) + game/fps_weapon.gd under the camera; a destructible wall 6 m ahead
## (args.wall, game/destructible.gd) and a dummy fighter 6 m to the right. Simulated time (physics frames).
## args: {wall: "res://...glb", gun: "res://...glb" (optional), magazine: 6, fire_rate: 8, damage: 25, wall_health: 100}
## data: {checks: [{name, ok, detail}]}
const Player := preload("res://addons/gg/game/player_3d.gd")
const Rig := preload("res://addons/gg/game/camera_rig.gd")
const FpsWeapon := preload("res://addons/gg/game/fps_weapon.gd")
const Destructible := preload("res://addons/gg/game/destructible.gd")
const CombatComponent := preload("res://addons/gg/game/combat_component.gd")


func _frames(tree: SceneTree, n: int) -> void:
	for i in n:
		await tree.physics_frame


func _capsule(body: CharacterBody3D) -> void:
	var s := CollisionShape3D.new()
	s.shape = CapsuleShape3D.new()
	s.shape.radius = 0.35
	s.shape.height = 1.8
	s.position.y = 0.9
	body.add_child(s)


func _combat(team: int, hp: float) -> Node:
	var c := CombatComponent.new()
	c.name = "Combat"
	c.attrs.team = team
	c.attrs.max_health = hp
	c.attrs.health = hp
	return c


func _mouse(dx: float, dy: float) -> void:
	var e := InputEventMouseMotion.new()
	e.relative = Vector2(dx, dy)
	e.screen_relative = Vector2(dx, dy)   # what player_3d / camera_rig read: not scaled by the viewport stretch
	Input.parse_input_event(e)
	# deliver it NOW: injected input is otherwise dispatched on the next PROCESS frame, and with a heavy scene several
	# physics frames run per process frame (with the 123 MB AK-47 model, two physics frames later nothing had arrived)
	Input.flush_buffered_events()


func run(tree: SceneTree, args: Dictionary) -> Dictionary:
	var wall_path: String = args.get("wall", "")
	if wall_path == "" or not ResourceLoader.exists(wall_path):
		return {"ok": false, "error": "args.wall %s is not a resource (gg_destruction.py init copies the test wall)" % wall_path, "data": {}}
	var magazine: int = int(args.get("magazine", 6))
	var fire_rate: float = float(args.get("fire_rate", 8.0))
	var damage: float = float(args.get("damage", 25.0))
	var wall_health: float = float(args.get("wall_health", 100.0))
	var dt := 1.0 / float(Engine.physics_ticks_per_second)
	var rows: Array = []
	# a project made by gg_project.py init has these (gg_style ACTIONS); a UI-init scratch project does not
	for a in ["move_forward", "move_back", "move_left", "move_right", "jump"]:
		if not InputMap.has_action(a):
			InputMap.add_action(a)

	var holder := Node3D.new()
	tree.root.add_child(holder)
	var floor := StaticBody3D.new()
	var fs := CollisionShape3D.new()
	fs.shape = BoxShape3D.new()
	fs.shape.size = Vector3(60, 1, 60)
	floor.add_child(fs)
	holder.add_child(floor)
	floor.position = Vector3(0, -0.5, 0)

	var player := Player.new()
	player.name = "Player"
	player.speed = 0.0                      # stand still: this slice is about shooting
	_capsule(player)
	player.add_child(_combat(0, 100.0))
	var rig := Rig.new()
	rig.name = "CameraRig"
	rig.mode = "first_person"
	player.add_child(rig)
	holder.add_child(player)

	var wall := Destructible.new()
	wall.name = "Wall"
	wall.model = load(wall_path)
	wall.max_health = wall_health
	wall.position = Vector3(0, 0, -6)          # 6 m ahead (-Z), standing on the floor
	holder.add_child(wall)

	var dummy := CharacterBody3D.new()
	dummy.name = "Dummy"
	_capsule(dummy)
	dummy.add_child(_combat(1, 100.0))
	# local position BEFORE add_child: added at the origin first, the dummy sat inside the player for a frame and the
	# player depenetrated up onto it (camera found at (6, 3.4, 0))
	dummy.position = Vector3(6, 0, 0)          # 6 m to the right (+X)
	holder.add_child(dummy)
	await _frames(tree, 2)

	var gun := FpsWeapon.new()
	gun.name = "Rifle"
	gun.magazine = magazine
	gun.start_reserve = magazine * 2
	gun.fire_rate = fire_rate
	gun.damage = damage
	gun.reload_s = 1.0
	var gun_path: String = args.get("gun", "")
	if gun_path != "" and ResourceLoader.exists(gun_path):
		gun.model = load(gun_path)
	rig.camera.add_child(gun)
	await _frames(tree, 2)
	var cam: Camera3D = rig.camera
	rows.append(["fire and reload actions exist", InputMap.has_action("fire") and InputMap.has_action("reload"), "fire=%s reload=%s" % [InputMap.has_action("fire"), InputMap.has_action("reload")]])
	rows.append(["the gun uses the player's Combat (reserve = its ammo)", gun.combat == player.get_node("Combat") and gun.reserve() == magazine * 2,
		"combat=%s reserve=%d" % [gun.combat.get_path(), gun.reserve()]])
	if gun.model != null:
		var mp: Vector3 = gun._model_node.global_position
		rows.append(["the gun model is in view in front of the eye", cam.is_position_in_frustum(mp) and (cam.global_transform.affine_inverse() * mp).z < 0.0,
			"model at %s (camera space %s)" % [mp, cam.global_transform.affine_inverse() * mp]])

	# 1. aim with the mouse: look up 10 degrees, then back down (camera pitch, clamped)
	_mouse(0, -10.0 / rig.mouse_sens)
	await _frames(tree, 2)
	var up := rig.look_pitch
	_mouse(0, 10.0 / rig.mouse_sens)
	_mouse(0, 1000.0 / rig.mouse_sens)
	await _frames(tree, 2)
	var clamped := rig.look_pitch
	_mouse(0, clamped / rig.mouse_sens)   # mouse up (negative dy) raises the pitch: back to level
	await _frames(tree, 2)
	rows.append(["mouse up/down pitches the camera and clamps", abs(up - 10.0) < 0.5 and abs(clamped + rig.max_look_deg) < 0.01 and abs(rig.look_pitch) < 0.5,
		"up %.1f, clamped %.1f, back %.1f deg" % [up, clamped, rig.look_pitch]])

	# 2. hold fire for 0.5 s at the wall: shots at fire_rate, magazine drains, the wall takes the damage and breaks
	var hits: Array = []   # an Array: a GDScript lambda captures a local int BY VALUE, so a counter there stays 0
	gun.fired.connect(func(h): hits.append(h))
	var pitch0 := rig.look_pitch
	Input.action_press("fire")
	var peak := pitch0   # highest pitch DURING the burst: each 0.8 deg kick is recovered in ~0.07 s, before the next shot
	for i in int(0.5 / dt):
		await tree.physics_frame
		peak = max(peak, rig.look_pitch)
	Input.action_release("fire")
	var expect := int(ceil(0.5 * fire_rate))
	rows.append(["holding fire shoots at the fire rate", abs(gun.shots - expect) <= 1, "%d shots in 0.5 s (fire_rate %.0f)" % [gun.shots, fire_rate]])
	rows.append(["each shot takes one round", gun.in_mag == magazine - gun.shots, "in_mag %d after %d shots (magazine %d)" % [gun.in_mag, gun.shots, magazine]])
	var need := int(ceil(wall_health / damage))
	var hits_wall := hits.filter(func(h): return h.get("collider") == wall).size()
	var first: Dictionary = hits[0] if hits.size() > 0 else {}
	rows.append(["the shots hit the wall and break it", hits_wall >= need and wall.is_broken,
		"%d wall hits, %d needed, broken=%s, health %s; first shot from %s dir %s hit %s" % [hits_wall, need, wall.is_broken,
		wall.combat.attrs.health, cam.global_position, -cam.global_transform.basis.z, first]])
	rows.append(["recoil kicks the view up while firing", peak > pitch0 + 0.5, "pitch %.2f -> %.2f deg" % [pitch0, peak]])
	await _frames(tree, int(1.0 / dt))
	rows.append(["the view comes back down after firing", abs(rig.look_pitch - pitch0) < 0.3, "pitch %.2f deg 1 s after release" % rig.look_pitch])

	# 3. empty magazine reloads from the reserve by itself: fire until empty, release, wait the reload time
	var reserve0 := gun.reserve()
	Input.action_press("fire")
	for i in int(2.0 / dt):
		if gun.in_mag == 0:
			break
		await tree.physics_frame
	Input.action_release("fire")
	var emptied := gun.in_mag == 0
	await _frames(tree, int((gun.reload_s + 0.3) / dt))
	rows.append(["an empty magazine reloads from the reserve", emptied and gun.in_mag == magazine and gun.reserve() == reserve0 - magazine,
		"emptied=%s, after the reload in_mag %d reserve %d (was %d)" % [emptied, gun.in_mag, gun.reserve(), reserve0]])

	# 4. turn right 90 degrees with the mouse and tap fire: the dummy takes one shot
	_mouse(90.0 / player.mouse_sens, 0)
	await _frames(tree, 3)
	var yaw := rad_to_deg(player.rotation.y)
	var d0: float = dummy.get_node("Combat").attrs.health
	var before := gun.shots
	Input.action_press("fire")
	await _frames(tree, 1)
	Input.action_release("fire")
	await _frames(tree, 2)
	var d1: float = dummy.get_node("Combat").attrs.health
	rows.append(["turning with the mouse aims the gun", abs(yaw + 90.0) < 1.0, "yaw %.1f deg" % yaw])
	rows.append(["a tap fires once and hurts what is aimed at", gun.shots == before + 1 and d1 == d0 - damage, "shots +%d, dummy %s -> %s" % [gun.shots - before, d0, d1]])

	holder.queue_free()
	var checks: Array = []
	var ok := true
	for row in rows:
		checks.append({"name": row[0], "ok": row[1], "detail": row[2]})
		ok = ok and row[1]
	return {"ok": ok, "error": null if ok else "one or more FPS checks failed", "data": {"checks": checks}}
