extends RefCounted
## T-0075: proves ONE declarative weapon/spell spec entry (see templates/combat_spec.example.json, loaded and
## validated by gg_combat.py's spec_errors/load_spec/resolve_ability) actually fires against the real engine,
## the same way combat_slice.gd proves the T-0070 hardcoded sword/gun/spell did, but data-driven: the ability's
## own delivery ("melee"|"raycast"|"instant"), range_m, cooldown_s, effect (kind/amount/damage_type) and
## optional cost (resource/amount) all come from the spec, not from this script. vfx recipes named in the
## spec's "vfx" field are built (not rendered -- gg_vfx.py check already proves a recipe draws non-flat pixels;
## this only proves VFX.build() accepts the spec's own recipe dict without error). "animation" is recorded as
## declared data only: the owned packs this spec format targets (e.g. low-poly-weapons-set, StaticMesh-only
## weapon props) have no skeleton/AnimationPlayer wired up yet, so no live animation playback is claimed here.
## args: {category: "weapons"|"spells", name: String, ability: Dictionary}. data: {checks: [{name, ok, detail}]}.
const CombatComponent := preload("res://addons/gg/game/combat_component.gd")
const Combat := preload("res://addons/gg/game/combat.gd")
const VFX := preload("res://addons/gg/game/vfx.gd")


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
	# headroom for whichever resource a spec's "cost" names, regardless of CombatAttributes' own per-resource defaults
	combat.attrs.max_mana = 100.0
	combat.attrs.mana = 100.0
	combat.attrs.max_stamina = 100.0
	combat.attrs.stamina = 100.0
	combat.attrs.max_ammo = 100
	combat.attrs.ammo = 100
	body.add_child(combat)
	return body


func _expected_delta(effect: Dictionary) -> float:
	var kind: String = effect.get("kind", "")
	if kind == "damage":
		return -float(effect.get("amount", 0.0))
	if kind == "heal":
		return float(effect.get("amount", 0.0))
	return 0.0


func run(tree: SceneTree, args: Dictionary) -> Dictionary:
	var ability: Dictionary = args.get("ability", {})
	var ability_name: String = str(args.get("name", "?"))
	var delivery: String = str(ability.get("delivery", ""))
	var range_m: float = float(ability.get("range_m", 5.0))
	var cooldown_s: float = float(ability.get("cooldown_s", 1.0))
	var effect: Dictionary = ability.get("effect", {})
	var cost: Dictionary = ability.get("cost", {})
	var ability_id := "spec_" + ability_name

	var holder := Node3D.new()
	tree.root.add_child(holder)
	var player := _body("Player", 0, 100.0)
	var dummy := _body("Dummy", 1, 1000.0)   # high health: several specs/resist combos must not kill it mid-check
	holder.add_child(player)
	holder.add_child(dummy)
	player.global_position = Vector3.ZERO

	var rows: Array = []
	var player_combat: Node = player.get_node("Combat")
	var dummy_combat: Node = dummy.get_node("Combat")

	# 1) resource cost, if the spec has one -- paid once, up front, independent of the ability's own cooldown
	if not cost.is_empty():
		var resource: String = str(cost.get("resource", "stamina"))
		var amount: float = float(cost.get("amount", 0.0))
		var before: float = player_combat.attrs.get(resource)
		var cost_result: Dictionary = Combat.apply_effect(player_combat.attrs, {"kind": "cost", "resource": resource, "amount": amount})
		var after: float = player_combat.attrs.get(resource)
		rows.append(["cost paid (%s -%s)" % [resource, amount], cost_result.get("ok", false) == true and absf(after - (before - amount)) < 0.01, "before=%s after=%s result=%s" % [before, after, cost_result]])

	var health_before: float = dummy_combat.attrs.health
	var r1: Dictionary = {}
	var delivered := false
	if delivery == "melee":
		dummy.global_position = Vector3(0, 0, -maxf(range_m - 0.5, 0.1))
		await tree.physics_frame
		await tree.physics_frame
		var dist: float = player.global_position.distance_to(dummy.global_position)
		delivered = dist <= range_m
		if delivered:
			r1 = player_combat.try_ability(ability_id, effect, dummy_combat, cooldown_s, 0.0)
	elif delivery == "raycast":
		dummy.global_position = Vector3(0, 0, -maxf(range_m * 0.5, 0.5))
		await tree.physics_frame
		await tree.physics_frame
		var space := tree.root.get_world_3d().direct_space_state
		var from: Vector3 = player.global_position + Vector3(0, 0.5, 0)   # mid-torso: avoids the capsule's own polar cap, see gg-combat.md
		var to: Vector3 = from + player.global_transform.basis.z * -range_m
		var query := PhysicsRayQueryParameters3D.create(from, to)
		query.exclude = [player.get_rid()]
		var hit := space.intersect_ray(query)
		delivered = hit.get("collider") == dummy
		if delivered:
			r1 = player_combat.try_ability(ability_id, effect, dummy_combat, cooldown_s, 0.0)
	elif delivery == "instant":
		dummy.global_position = Vector3(0, 0, -maxf(range_m * 0.9, 1.0))
		await tree.physics_frame
		await tree.physics_frame
		delivered = true
		r1 = player_combat.try_ability(ability_id, effect, dummy_combat, cooldown_s, 0.0)

	var expect_delta: float = _expected_delta(effect)
	var landed: bool = delivered and r1.get("ok", true) != false and is_equal_approx(dummy_combat.attrs.health, health_before + expect_delta)
	rows.append(["%s delivery lands (%s)" % [delivery, ability_name], landed, "delivered=%s before=%s after=%s result=%s" % [delivered, health_before, dummy_combat.attrs.health, r1]])

	# 2) cooldown: an immediate repeat at the same clock time must be refused, health must not move again
	var health_after_first: float = dummy_combat.attrs.health
	var r2: Dictionary = player_combat.try_ability(ability_id, effect, dummy_combat, cooldown_s, 0.01)
	rows.append(["cooldown blocks an immediate repeat", r2.get("ok", true) == false and dummy_combat.attrs.health == health_after_first, "result=%s" % [r2]])

	# 3) vfx hookup: each named recipe in the spec must build without error (not rendered here -- gg_vfx.py check proves that live)
	var vfx: Dictionary = ability.get("vfx", {})
	for vfx_name in vfx:
		var particles: GPUParticles3D = VFX.build(vfx[vfx_name])
		rows.append(["vfx '%s' builds" % [vfx_name], particles != null, "recipe=%s" % [vfx[vfx_name]]])
		if particles != null:
			particles.queue_free()

	# 4) animation hookup: data only -- no skeleton/AnimationPlayer in this spec's target packs to bind it to live
	var anim: Dictionary = ability.get("animation", {})
	rows.append(["animation hookup declared", not anim.is_empty(), "animation=%s (data only: no skeleton in this pack to bind to)" % [anim]])

	# 5) the weapon model: "mesh" (res:// glb) loads, is a plausible hand-held size, and every "parts" glb (magazine,
	# trigger: the unreal-export bridge writes each StaticMesh separately, all on the body's pivot) sits on the body
	var mesh_path: String = str(ability.get("mesh", ""))
	if mesh_path.begins_with("res://"):
		var body_box = _model_box(mesh_path)
		var size: float = body_box.get_longest_axis_size() if body_box != null else 0.0
		rows.append(["weapon model loads at a hand-held size", body_box != null and size > 0.1 and size < 3.0,
			"%s longest side %.2f m" % [mesh_path, size]])
		for part in ability.get("parts", []):
			var pb = _model_box(str(part))
			rows.append(["part %s sits on the body" % str(part).get_file(), pb != null and body_box != null and body_box.grow(0.02).intersects(pb),
				"part box %s, body box %s" % [pb, body_box]])

	holder.queue_free()
	var checks: Array = []
	var ok := true
	for row in rows:
		checks.append({"name": row[0], "ok": row[1], "detail": row[2]})
		ok = ok and row[1]
	return {"ok": ok, "error": null if ok else "one or more spec checks failed", "data": {"checks": checks}}


## Combined AABB (in the model's own space) of every MeshInstance3D in a glb, or null when it does not load / has no mesh.
func _model_box(path: String):
	if not ResourceLoader.exists(path):
		return null
	var root := (load(path) as PackedScene).instantiate() as Node3D
	var box = null
	for m in root.find_children("*", "MeshInstance3D", true, false):
		var xf := Transform3D()
		var n: Node = m
		while n != root and n != null:
			xf = (n as Node3D).transform * xf
			n = n.get_parent()
		var b: AABB = xf * (m as MeshInstance3D).get_aabb()
		box = b if box == null else box.merge(b)
	root.free()
	return box
