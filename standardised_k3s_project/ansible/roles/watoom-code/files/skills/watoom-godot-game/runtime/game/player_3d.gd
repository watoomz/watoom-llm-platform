extends CharacterBody3D
## 3D walker. Origin = the feet. Reads the project's fixed actions move_forward/back/left/right and jump; mouse motion turns it.
## Forward is -Z of the body (yaw 0 faces -Z). `world_relative` (top-down / isometric cameras): WASD move along the world axes instead.
## Everything is set from the profile by build_player.gd; the model never edits this file.
@export var speed := 5.0
@export var accel := 40.0
@export var jump_velocity := 0.0
@export var gravity := 9.8
@export var floor_angle_deg := 45.0
@export var mouse_sens := 0.15
@export var world_relative := false
var action_seen := {}
var mouse_events := 0

func _ready() -> void:
	floor_max_angle = deg_to_rad(floor_angle_deg)
	floor_snap_length = 0.3
	floor_constant_speed = true
	floor_stop_on_slope = true

func _unhandled_input(e: InputEvent) -> void:
	if e is InputEventMouseMotion:
		mouse_events += 1
		if not world_relative:
			rotate_y(-deg_to_rad(look_delta(e as InputEventMouseMotion).x * mouse_sens))


## Mouse movement in SCREEN pixels: screen_relative is not scaled by the viewport's stretch transform, relative is (T-0066:
## in a stretched 640x360 project a 90 degree turn came out as 180 and 10 degrees of look as 56). Falls back to relative for
## events that only set it (older injected test events).
static func look_delta(e: InputEventMouseMotion) -> Vector2:
	return e.screen_relative if e.screen_relative != Vector2.ZERO else e.relative

func _physics_process(dt: float) -> void:
	for a in ["move_forward", "move_back", "move_left", "move_right", "jump"]:
		if Input.is_action_pressed(a):
			action_seen[a] = true
	var fwd := Input.get_action_strength("move_forward") - Input.get_action_strength("move_back")
	var side := Input.get_action_strength("move_right") - Input.get_action_strength("move_left")
	var dir := Vector3(side, 0.0, -fwd)
	if not world_relative:
		dir = global_transform.basis * dir
	if dir.length() > 1.0:
		dir = dir.normalized()
	var target := dir * speed
	var h := Vector2(velocity.x, velocity.z).move_toward(Vector2(target.x, target.z), accel * dt)
	velocity.x = h.x
	velocity.z = h.y
	if is_on_floor():
		if jump_velocity > 0.0 and Input.is_action_pressed("jump"):
			velocity.y = jump_velocity
		elif velocity.y < 0.0:
			velocity.y = 0.0
	else:
		velocity.y -= gravity * dt
	move_and_slide()
