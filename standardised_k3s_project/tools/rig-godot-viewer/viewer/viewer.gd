extends Node3D
## WatooM asset viewer: opens whatever res://entry.txt names, frames it, and lets you orbit around it.
##   mouse: left = orbit, right/middle = pan, wheel = zoom      F = frame again   R = reset view   Tab = hide/show info
##   1 shaded   2 unshaded (albedo only)   3 wireframe   4 normals   L = cycle lighting   G = grid   B = background   A = play animations
## Command line (after --): --shot=<file.png> saves a screenshot after framing and quits (used for automatic previews).

var _subject: Node3D
var _camera: Camera3D
var _pivot: Node3D
var _label: Label
var _grid: MeshInstance3D
var _sun: DirectionalLight3D
var _fill: DirectionalLight3D
var _env: Environment
var _yaw: float = 0.4
var _pitch: float = -0.15
var _distance: float = 3.0
var _target: Vector3 = Vector3.ZERO
var _extent: float = 1.0
var _light_mode: int = 0
var _backgrounds: Array[Color] = [Color(0.30, 0.32, 0.36), Color(0.05, 0.05, 0.06), Color(0.85, 0.85, 0.87)]
var _background_index: int = 0
var _shot: String = ""
var _info: String = ""
var _hidden: bool = false


func _ready() -> void:
	RenderingServer.set_debug_generate_wireframes(true)
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--shot="):
			_shot = arg.trim_prefix("--shot=")
	_build_environment()
	_pivot = Node3D.new()
	add_child(_pivot)
	_camera = Camera3D.new()
	_camera.fov = 40.0
	_camera.near = 0.01
	_camera.far = 500.0
	_pivot.add_child(_camera)
	_camera.current = true
	_label = Label.new()
	_label.position = Vector2(12.0, 10.0)
	_label.add_theme_color_override("font_outline_color", Color.BLACK)
	_label.add_theme_constant_override("outline_size", 6)
	var layer: CanvasLayer = CanvasLayer.new()
	layer.add_child(_label)
	add_child(layer)
	_load_subject()
	_frame()
	if _shot != "":
		for i: int in range(6):
			await get_tree().process_frame
		await RenderingServer.frame_post_draw
		get_viewport().get_texture().get_image().save_png(_shot)
		get_tree().quit()


func _load_subject() -> void:
	var entry: String = FileAccess.get_file_as_string("res://entry.txt").strip_edges()
	var resource: Resource = load(entry)
	if resource is PackedScene:
		_subject = (resource as PackedScene).instantiate() as Node3D
	if _subject == null:
		_info = "Could not open " + entry + "\n(import it first, or it is not a 3D scene)"
		_label.text = _info
		_subject = Node3D.new()
	add_child(_subject)
	await get_tree().process_frame
	_info = _describe(entry)
	_label.text = _info + "\n\n" + _help()


func _help() -> String:
	return "drag = orbit | right-drag = pan | wheel = zoom | F frame | R reset | 1 shaded 2 unshaded 3 wire 4 normals | L light | G grid | B background | A animate | Tab info"


func _describe(entry: String) -> String:
	var meshes: int = 0
	var surfaces: int = 0
	var textured: int = 0
	var plain: int = 0
	var verts: int = 0
	var skeletons: int = 0
	var bones: int = 0
	var players: Array[String] = []
	for node: Node in _subject.find_children("*", "", true, false):
		if node is MeshInstance3D:
			var mi: MeshInstance3D = node as MeshInstance3D
			if mi.mesh == null:
				continue
			meshes += 1
			for s: int in range(mi.mesh.get_surface_count()):
				surfaces += 1
				verts += (mi.mesh.surface_get_arrays(s)[Mesh.ARRAY_VERTEX] as PackedVector3Array).size()
				var material: Material = mi.get_active_material(s)
				var base: BaseMaterial3D = material as BaseMaterial3D
				if base != null and base.albedo_texture != null:
					textured += 1
				else:
					plain += 1
		elif node is Skeleton3D:
			skeletons += 1
			bones += (node as Skeleton3D).get_bone_count()
		elif node is AnimationPlayer:
			for animation: String in (node as AnimationPlayer).get_animation_list():
				players.append(animation)
	var box: AABB = _bounds()
	return "%s\nmeshes %d | surfaces %d (%d with albedo texture, %d plain) | vertices %d | skeletons %d (%d bones) | animations %d\nsize %.2f x %.2f x %.2f m" % [entry, meshes, surfaces, textured, plain, verts, skeletons, bones, players.size(), box.size.x, box.size.y, box.size.z]


func _bounds() -> AABB:
	var box: AABB = AABB()
	var first: bool = true
	for node: Node in _subject.find_children("*", "VisualInstance3D", true, false):
		var vi: VisualInstance3D = node as VisualInstance3D
		var local: AABB = vi.global_transform * vi.get_aabb()
		if first:
			box = local
			first = false
		else:
			box = box.merge(local)
	if first:
		box = AABB(Vector3(-0.5, 0.0, -0.5), Vector3(1.0, 1.0, 1.0))
	return box


func _frame() -> void:
	var box: AABB = _bounds()
	_target = box.get_center()
	_extent = maxf(box.size.length() * 0.5, 0.05)
	_distance = _extent / tan(deg_to_rad(_camera.fov) * 0.5) * 1.15
	_update_camera()
	var ground: float = box.position.y
	if _grid == null:
		_grid = MeshInstance3D.new()
		var plane: PlaneMesh = PlaneMesh.new()
		plane.size = Vector2(1.0, 1.0)
		_grid.mesh = plane
		var material: StandardMaterial3D = StandardMaterial3D.new()
		material.albedo_color = Color(1.0, 1.0, 1.0, 0.07)
		material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		_grid.material_override = material
		add_child(_grid)
	_grid.scale = Vector3.ONE * _extent * 8.0
	_grid.position = Vector3(_target.x, ground - 0.001, _target.z)


func _update_camera() -> void:
	_pivot.position = _target
	_pivot.rotation = Vector3(_pitch, _yaw, 0.0)
	_camera.position = Vector3(0.0, 0.0, _distance)


func _build_environment() -> void:
	_sun = DirectionalLight3D.new()
	_sun.rotation_degrees = Vector3(-40.0, 30.0, 0.0)
	_sun.light_energy = 1.2
	_sun.shadow_enabled = true
	add_child(_sun)
	_fill = DirectionalLight3D.new()
	_fill.rotation_degrees = Vector3(-15.0, -150.0, 0.0)
	_fill.light_energy = 0.5
	add_child(_fill)
	_env = Environment.new()
	_env.background_mode = Environment.BG_COLOR
	_env.background_color = _backgrounds[0]
	_env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	_env.ambient_light_color = Color(0.8, 0.8, 0.85)
	_env.ambient_light_energy = 0.6
	var world: WorldEnvironment = WorldEnvironment.new()
	world.environment = _env
	add_child(world)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion:
		var motion: InputEventMouseMotion = event as InputEventMouseMotion
		if Input.is_mouse_button_pressed(MOUSE_BUTTON_LEFT):
			_yaw -= motion.relative.x * 0.006
			_pitch = clampf(_pitch - motion.relative.y * 0.006, -1.5, 1.5)
			_update_camera()
		elif Input.is_mouse_button_pressed(MOUSE_BUTTON_RIGHT) or Input.is_mouse_button_pressed(MOUSE_BUTTON_MIDDLE):
			var right: Vector3 = _camera.global_transform.basis.x
			var up: Vector3 = _camera.global_transform.basis.y
			_target += (-right * motion.relative.x + up * motion.relative.y) * _distance * 0.0012
			_update_camera()
	elif event is InputEventMouseButton:
		var button: InputEventMouseButton = event as InputEventMouseButton
		if button.pressed and button.button_index == MOUSE_BUTTON_WHEEL_UP:
			_distance = maxf(_distance * 0.9, 0.02)
			_update_camera()
		elif button.pressed and button.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			_distance *= 1.1
			_update_camera()
	elif event is InputEventKey and (event as InputEventKey).pressed and not (event as InputEventKey).echo:
		_key((event as InputEventKey).keycode)


func _key(code: Key) -> void:
	var viewport: Viewport = get_viewport()
	match code:
		KEY_F:
			_frame()
		KEY_R:
			_yaw = 0.4
			_pitch = -0.15
			_frame()
		KEY_1:
			viewport.debug_draw = Viewport.DEBUG_DRAW_DISABLED
		KEY_2:
			viewport.debug_draw = Viewport.DEBUG_DRAW_UNSHADED
		KEY_3:
			viewport.debug_draw = Viewport.DEBUG_DRAW_WIREFRAME
		KEY_4:
			viewport.debug_draw = Viewport.DEBUG_DRAW_NORMAL_BUFFER
		KEY_L:
			_light_mode = (_light_mode + 1) % 3
			_sun.visible = _light_mode != 2
			_fill.visible = _light_mode != 2
			_env.ambient_light_energy = [0.6, 1.4, 0.15][_light_mode]
		KEY_G:
			_grid.visible = not _grid.visible
		KEY_B:
			_background_index = (_background_index + 1) % _backgrounds.size()
			_env.background_color = _backgrounds[_background_index]
		KEY_A:
			for node: Node in _subject.find_children("*", "AnimationPlayer", true, false):
				var player: AnimationPlayer = node as AnimationPlayer
				var names: PackedStringArray = player.get_animation_list()
				if names.size() > 0:
					player.play(names[0])
		KEY_TAB:
			_hidden = not _hidden
			_label.visible = not _hidden
