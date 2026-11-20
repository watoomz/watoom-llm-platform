extends Node3D
## First-person hitscan gun (T-0066). Make it a child of the first-person Camera3D (camera_rig.gd "Camera3D").
## Fires through the gg_combat path every weapon uses: a REAL raycast from the screen centre -> the hit collider's
## "Combat" child -> try_ability, and hit_at(point, dir) when the collider has it (game/destructible.gd), so walls
## break where they were shot. Magazine is local; the reserve is the owner's CombatAttributes.ammo, so gg_combat
## ammo pickups refill it. Registers its own input actions if the project has none: fire = left mouse, reload = R.
##
##   var gun := FpsWeapon.new(); gun.model = preload("res://assets/weapons/rifle.glb"); camera.add_child(gun)
## In a SAVED scene put it under the player's CameraRig (camera_rig.gd makes its Camera3D in _ready, which runs AFTER the
## children's _ready): it moves itself under rig.camera once that exists.
##
## signal fired(hit: Dictionary)   (hit = intersect_ray result, empty on a miss)
## signal reloaded(in_mag: int, reserve: int)
signal fired(hit: Dictionary)
signal reloaded(in_mag: int, reserve: int)

const CombatComponent := preload("res://addons/gg/game/combat_component.gd")

@export var model: PackedScene
@export var model_offset := Vector3(0.22, -0.2, -0.45)   ## where the gun sits in front of the eye (m, camera space)
@export var model_rotation_deg := Vector3.ZERO
@export var model_scale := 1.0
@export var damage := 25.0
@export var element := "physical"
@export var fire_rate := 8.0           ## shots per second while fire is held
@export var magazine := 30
@export var start_reserve := 90
@export var reload_s := 1.6
@export var range_m := 200.0
@export var spread_deg := 0.0          ## random cone half-angle per shot
@export var recoil_deg := 0.8          ## camera pitch kick per shot
@export var recoil_return_dps := 12.0  ## pitch recovered per second
@export var kick_m := 0.04             ## the model jumps back this much per shot

var in_mag := 0
var combat: Node                       ## the owner's CombatComponent (found up the tree) or our own
var shots := 0
var _cooldown := 0.0
var _reload_left := 0.0
var _recoil_owed := 0.0
var _model_node: Node3D
var _rng := RandomNumberGenerator.new()


func _ready() -> void:
	var p := get_parent()
	if not (p is Camera3D) and "camera" in p:
		_attach.call_deferred(p)
		return
	_setup()


func _attach(rig: Node) -> void:
	if rig.camera == null:
		push_error("FpsWeapon %s: %s has no camera" % [name, rig.name])
		return
	reparent(rig.camera, false)
	_setup()   # _ready runs once per node: re-entering the tree does not call it again


func _setup() -> void:
	_ensure_action("fire", _mouse(MOUSE_BUTTON_LEFT))
	_ensure_action("reload", _key(KEY_R))
	combat = _find_combat()
	if combat == null:
		combat = CombatComponent.new()
		combat.name = "Combat"
		add_child(combat)
	if combat.attrs.max_ammo < start_reserve:
		combat.attrs.max_ammo = start_reserve
	combat.attrs.ammo = start_reserve
	in_mag = magazine
	if model != null:
		_model_node = model.instantiate()
		add_child(_model_node)
		_model_node.position = model_offset
		_model_node.rotation_degrees = model_rotation_deg
		_model_node.scale = Vector3.ONE * model_scale


static func _mouse(b: int) -> InputEvent:
	var e := InputEventMouseButton.new()
	e.button_index = b
	return e


static func _key(k: int) -> InputEvent:
	var e := InputEventKey.new()
	e.physical_keycode = k
	return e


static func _ensure_action(action: String, ev: InputEvent) -> void:
	if not InputMap.has_action(action):
		InputMap.add_action(action)
		InputMap.action_add_event(action, ev)


func _find_combat() -> Node:
	var n := get_parent()
	while n != null:
		var c := n.get_node_or_null("Combat")
		if c != null and "attrs" in c:
			return c
		n = n.get_parent()
	return null


func _camera() -> Camera3D:
	var n := get_parent()
	while n != null and not (n is Camera3D):
		n = n.get_parent()
	return n as Camera3D


func reserve() -> int:
	return combat.attrs.ammo


func _physics_process(dt: float) -> void:
	_cooldown = max(0.0, _cooldown - dt)
	if _reload_left > 0.0:
		_reload_left -= dt
		if _reload_left <= 0.0:
			_finish_reload()
	elif Input.is_action_just_pressed("reload") or (in_mag == 0 and reserve() > 0):
		start_reload()
	if Input.is_action_pressed("fire"):
		fire()
	# recoil: the kick is applied at once, recovered at recoil_return_dps
	if _recoil_owed > 0.0:
		var back: float = min(_recoil_owed, recoil_return_dps * dt)
		_recoil_owed -= back
		_pitch(-back)
	if _model_node != null:
		_model_node.position = _model_node.position.lerp(model_offset, min(1.0, dt * 20.0))


func _pitch(deg: float) -> void:
	var rig := get_parent()
	while rig != null and not rig.has_method("add_pitch"):
		rig = rig.get_parent()
	if rig != null:
		rig.add_pitch(deg)


func start_reload() -> bool:
	if _reload_left > 0.0 or in_mag == magazine or reserve() <= 0:
		return false
	_reload_left = reload_s
	return true


func _finish_reload() -> void:
	var take: int = min(magazine - in_mag, reserve())
	combat.attrs.ammo = reserve() - take
	in_mag += take
	reloaded.emit(in_mag, reserve())


## One shot if the gun is ready (cooldown, ammo, not reloading). Returns the hit ({} on a miss or no shot).
func fire() -> Dictionary:
	if _cooldown > 0.0 or _reload_left > 0.0 or in_mag <= 0:
		return {}
	var cam := _camera()
	if cam == null:
		push_error("FpsWeapon %s: not under a Camera3D" % name)
		return {}
	_cooldown = 1.0 / fire_rate
	in_mag -= 1
	shots += 1
	var basis := cam.global_transform.basis
	var dir := -basis.z
	if spread_deg > 0.0:
		var a := deg_to_rad(_rng.randf_range(-spread_deg, spread_deg))
		var b := deg_to_rad(_rng.randf_range(-spread_deg, spread_deg))
		dir = (dir + basis.x * tan(a) + basis.y * tan(b)).normalized()
	var from := cam.global_position
	var q := PhysicsRayQueryParameters3D.create(from, from + dir * range_m)
	var body := _owner_body()
	if body != null:
		q.exclude = [body.get_rid()]
	var hit := get_world_3d().direct_space_state.intersect_ray(q)
	var col: Node = hit.get("collider")
	if col != null:
		if col.has_method("hit_at"):
			col.hit_at(hit["position"], dir)
		var target: Node = col.get_node_or_null("Combat")
		if target != null and "attrs" in target:
			combat.try_ability("gun_" + name, {"kind": "damage", "amount": damage, "element": element}, target, 0.0,
				Time.get_ticks_msec() / 1000.0)
	_recoil_owed += recoil_deg
	_pitch(recoil_deg)
	if _model_node != null:
		_model_node.position.z += kick_m
	fired.emit(hit)
	return hit


func _owner_body() -> CollisionObject3D:
	var n := get_parent()
	while n != null and not (n is CollisionObject3D):
		n = n.get_parent()
	return n as CollisionObject3D
