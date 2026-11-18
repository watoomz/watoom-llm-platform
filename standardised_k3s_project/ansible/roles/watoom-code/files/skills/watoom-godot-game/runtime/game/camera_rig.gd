extends Node3D
## Camera for the 3D player. mode: first_person | third_person | top_down | isometric. Child of the player. Values come from the profile.
@export var mode := "first_person"
@export var eye_height := 1.6
@export var fov := 75.0
@export var distance := 5.0
@export var pitch_deg := -15.0
@export var ortho_size := 20.0
@export var near := 0.05
@export var far := 1000.0
var camera: Camera3D
var arm: SpringArm3D

func _ready() -> void:
	camera = Camera3D.new()
	camera.name = "Camera3D"
	camera.fov = fov
	camera.near = near
	camera.far = far
	match mode:
		"first_person":
			position = Vector3(0, eye_height, 0)
			add_child(camera)
		"third_person":
			position = Vector3(0, eye_height, 0)
			rotation_degrees.x = pitch_deg
			arm = SpringArm3D.new()
			arm.name = "Arm"
			arm.spring_length = distance
			arm.shape = SphereShape3D.new()
			(arm.shape as SphereShape3D).radius = 0.2
			arm.margin = 0.1
			add_child(arm)
			arm.add_child(camera)
			if get_parent() is CollisionObject3D:
				arm.add_excluded_object((get_parent() as CollisionObject3D).get_rid())
		"top_down", "isometric":
			top_level = true
			if mode == "isometric":
				camera.projection = Camera3D.PROJECTION_ORTHOGONAL
				camera.size = ortho_size
			add_child(camera)
	camera.current = true

func _process(_dt: float) -> void:
	if mode == "top_down" or mode == "isometric":
		var p := (get_parent() as Node3D).global_position
		var yaw := 0.0 if mode == "top_down" else deg_to_rad(45.0)
		var b := Basis.from_euler(Vector3(deg_to_rad(pitch_deg), yaw, 0.0))
		global_transform = Transform3D(b, p + b * Vector3(0, 0, distance))
