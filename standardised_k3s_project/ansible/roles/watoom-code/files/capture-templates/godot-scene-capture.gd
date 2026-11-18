extends Node3D
## Copy into the selected project. Configure actual scene/views before running.
## Execute ONLY through the approved rendered external worker, not --headless.
@export var scene_path: String = ""
@export var output_dir: String = "res://.opencode/captures/review"
@export var settle_frames: int = 8
@export var views: Array[Dictionary] = []
# Each view: {"name":"wide", "position":Vector3(...), "target":Vector3(...), "fov":60.0}

func _ready() -> void:
	if scene_path.is_empty() or views.is_empty():
		_fail("Configure scene_path and explicit scene-relative views; no guessed defaults")
		return
	if DisplayServer.get_name() == "headless":
		_fail("Rendered capture needs a framebuffer; use approved Xvfb/rendered worker")
		return
	var packed = load(scene_path) as PackedScene
	if packed == null:
		_fail("Scene could not be loaded")
		return
	var scene = packed.instantiate()
	add_child(scene)
	# Capture actual project scene, preserving its terrain/materials/environment.
	# For moving scenes use explicit deterministic scene pause/setup hooks.
	var abs_dir := ProjectSettings.globalize_path(output_dir)
	if DirAccess.make_dir_recursive_absolute(abs_dir) != OK:
		_fail("Cannot create capture directory")
		return
	for view in views:
		if not _valid_view(view):
			_fail("Invalid view: name, distinct position/target, sensible fov required")
			return
		var camera := Camera3D.new()
		add_child(camera)
		camera.global_transform = Transform3D(Basis.IDENTITY, view.position).looking_at(view.target, Vector3.UP)
		camera.fov = float(view.get("fov", 60.0))
		camera.make_current()
		for frame in range(maxi(settle_frames, 2)):
			await get_tree().process_frame
		await RenderingServer.frame_post_draw
		if get_viewport().get_camera_3d() != camera:
			_fail("Scene replaced capture camera; inspect scene camera controller")
			return
		var image := get_viewport().get_texture().get_image()
		if image == null or image.is_empty():
			_fail("No rendered pixels")
			return
		var path := abs_dir.path_join(str(view.name) + ".png")
		if image.save_png(path) != OK:
			_fail("PNG save failed")
			return
		var receipt := {"status":"CAPTURED_NOT_VISUALLY_REVIEWED", "scene":scene_path,
			"image_path":path, "sha256":FileAccess.get_sha256(path),
			"size":[image.get_width(), image.get_height()], "camera_position":str(camera.global_position),
			"camera_basis":str(camera.global_basis), "target":str(view.target), "fov":camera.fov,
			"renderer":RenderingServer.get_current_rendering_method(), "engine":Engine.get_version_info()}
		var file := FileAccess.open(path + ".capture.json", FileAccess.WRITE)
		if file == null:
			_fail("Capture receipt save failed")
			return
		file.store_string(JSON.stringify(receipt, "  "))
		file.close()
		print("CAPTURE_RECEIPT " + JSON.stringify(receipt))
		camera.queue_free()
		await get_tree().process_frame
	get_tree().quit(0)

func _valid_view(view: Dictionary) -> bool:
	if not view.has("name") or not view.has("position") or not view.has("target"):
		return false
	var name := str(view.name)
	if name.is_empty() or name.contains("/") or name.contains("\\") or name.contains(".."):
		return false
	if not view.position is Vector3 or not view.target is Vector3:
		return false
	var direction: Vector3 = view.target - view.position
	return direction.is_finite() and view.position.is_finite() and direction.length() > 0.01 and absf(direction.normalized().dot(Vector3.UP)) < 0.999 and float(view.get("fov", 60.0)) >= 5.0 and float(view.get("fov", 60.0)) <= 120.0

func _fail(message: String) -> void:
	push_error("CAPTURE_FAILED: " + message)
	get_tree().quit(1)
