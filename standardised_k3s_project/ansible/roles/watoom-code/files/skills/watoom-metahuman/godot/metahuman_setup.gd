extends Node3D
## MetaHuman built from headless Unreal exports: a skinned full-body mesh plus a skinned head mesh.
## The head skeleton copies the body pose each frame (shared bones only), so animate the body and the head follows.
## Face expressions are not driven here: they come from RigLogic (the .dna files), which Godot does not run.

@export var skin_tone: Color = @SKIN@
@export_group("Head")
@export var albedo_head: Texture2D
@export var normal_head: Texture2D
@export var roughness_head: Texture2D  ## MetaHuman SRMF map; its green channel is read as roughness
@export_group("Head details")
@export var eye_color: Texture2D
@export var eye_normal: Texture2D
@export var teeth_color: Texture2D
@export var teeth_normal: Texture2D
@export var lashes_color: Texture2D  ## RGBA: the alpha channel is the lash strand cut-out
## Role of each head surface (skin, teeth, eye, eyelashes, clear) and the vertex count it was identified by; a surface is only treated
## as its role when its vertex count still matches, so a re-imported or re-ordered mesh falls back safely.
@export var head_surface_roles: PackedStringArray = PackedStringArray()
@export var head_surface_verts: PackedInt32Array = PackedInt32Array()
@export_group("Body")
@export var albedo_body: Texture2D
@export var normal_body: Texture2D
@export var roughness_body: Texture2D
@export_group("")
@export var follow_body_pose: bool = true
@export_group("Animation")
@export var play_idle: bool = true  ## builds and loops a procedural 8 s idle (breathing, weight sway, head drift) on the body skeleton
@export var idle_strength: float = 1.0  ## scales every idle motion; 0 holds the A-pose
@export var arm_drop_degrees: float = 12.0  ## lowers the arms from the export's A-pose toward a relaxed stance
@export_group("")

var _body_skeleton: Skeleton3D
var _head_skeleton: Skeleton3D
var _head_bones: PackedInt32Array = PackedInt32Array()
var _body_bones: PackedInt32Array = PackedInt32Array()


func _ready() -> void:
	_body_skeleton = _find_skeleton($Body)
	_head_skeleton = _find_skeleton($Head)
	_apply_skin($Body, albedo_body, normal_body, roughness_body)
	if head_surface_roles.is_empty():
		_apply_skin($Head, albedo_head, normal_head, roughness_head)
	else:
		_apply_head_parts($Head)
	if _body_skeleton == null or _head_skeleton == null:
		push_warning("MetaHuman: skeleton missing; head will not follow the body")
		return
	for head_index: int in range(_head_skeleton.get_bone_count()):
		var body_index: int = _body_skeleton.find_bone(_head_skeleton.get_bone_name(head_index))
		if body_index >= 0:
			_head_bones.append(head_index)
			_body_bones.append(body_index)
	process_priority = 10  # after the AnimationPlayer, so the head copies the pose the body just received
	if play_idle:
		_build_idle()


func _process(_delta: float) -> void:
	if not follow_body_pose or _body_skeleton == null or _head_skeleton == null:
		return
	for i: int in range(_head_bones.size()):
		var h: int = _head_bones[i]
		var b: int = _body_bones[i]
		_head_skeleton.set_bone_pose_position(h, _body_skeleton.get_bone_pose_position(b))
		_head_skeleton.set_bone_pose_rotation(h, _body_skeleton.get_bone_pose_rotation(b))
		_head_skeleton.set_bone_pose_scale(h, _body_skeleton.get_bone_pose_scale(b))


func _find_skeleton(root: Node) -> Skeleton3D:
	for child: Node in root.find_children("*", "Skeleton3D", true, false):
		return child as Skeleton3D
	return null


func _apply_skin(root: Node, albedo_map: Texture2D, normal_map: Texture2D, roughness_map: Texture2D) -> void:
	# The largest surface of each mesh is the skin; eyes, teeth and lashes keep the glTF default material.
	for node: Node in root.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance: MeshInstance3D = node as MeshInstance3D
		var mesh: Mesh = mesh_instance.mesh
		if mesh == null or mesh.get_surface_count() == 0:
			continue
		var best: int = 0
		var best_count: int = -1
		for surface: int in range(mesh.get_surface_count()):
			var arrays: Array = mesh.surface_get_arrays(surface)
			var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			if vertices.size() > best_count:
				best_count = vertices.size()
				best = surface
		var material: StandardMaterial3D = _skin_material(albedo_map, normal_map, roughness_map)
		mesh_instance.set_surface_override_material(best, material)


func _skin_material(albedo_map: Texture2D, normal_map: Texture2D, roughness_map: Texture2D) -> StandardMaterial3D:
	var material: StandardMaterial3D = StandardMaterial3D.new()
	material.albedo_color = skin_tone
	if albedo_map != null:
		material.albedo_texture = albedo_map
		material.albedo_color = Color.WHITE   # the real skin map replaces the flat tone
	material.roughness = 0.6
	if roughness_map != null:
		material.roughness_texture = roughness_map
		material.roughness_texture_channel = BaseMaterial3D.TEXTURE_CHANNEL_GREEN
		material.roughness = 1.0
	material.subsurf_scatter_enabled = true
	material.subsurf_scatter_strength = 0.25
	if normal_map != null:
		material.normal_enabled = true
		material.normal_texture = normal_map
	return material


func _apply_head_parts(root: Node) -> void:
	for node: Node in root.find_children("*", "MeshInstance3D", true, false):
		var mesh_instance: MeshInstance3D = node as MeshInstance3D
		var mesh: Mesh = mesh_instance.mesh
		if mesh == null:
			continue
		for surface: int in range(mesh.get_surface_count()):
			if surface >= head_surface_roles.size():
				break
			var arrays: Array = mesh.surface_get_arrays(surface)
			var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			if surface >= head_surface_verts.size() or vertices.size() != head_surface_verts[surface]:
				push_warning("MetaHuman: head surface %d does not match the identified mesh; left unchanged" % surface)
				continue
			var material: Material = _part_material(head_surface_roles[surface])
			if material != null:
				mesh_instance.set_surface_override_material(surface, material)


func _part_material(role: String) -> Material:
	var material: StandardMaterial3D = StandardMaterial3D.new()
	match role:
		"skin":
			return _skin_material(albedo_head, normal_head, roughness_head)
		"eye":
			material.albedo_texture = eye_color
			material.roughness = 0.15
			if eye_normal != null:
				material.normal_enabled = true
				material.normal_texture = eye_normal
		"teeth":
			material.albedo_texture = teeth_color
			material.roughness = 0.4
			if teeth_normal != null:
				material.normal_enabled = true
				material.normal_texture = teeth_normal
		"eyelashes":
			material.albedo_texture = lashes_color
			material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
			material.alpha_scissor_threshold = 0.5
			material.cull_mode = BaseMaterial3D.CULL_DISABLED
			material.roughness = 0.8
		"clear":
			# saliva, eye shell, eye edge, cartilage: glossy and nearly transparent so they never cover the eyes
			material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
			material.albedo_color = Color(1.0, 1.0, 1.0, 0.05)
			material.roughness = 0.05
		_:
			return null
	return material


const IDLE_LENGTH: float = 8.0
const IDLE_STEP: float = 0.25
## bone, axis in character space (x right, y up, z forward), amplitude in degrees, whole cycles per loop, phase in cycles.
## An axis written as (0, 0, 1) on a left/right pair is mirrored by the side of the bone, so both sides lift together.
const IDLE_MOTIONS: Array = [
	["spine_01", Vector3(0, 0, 1), 0.8, 1, 0.0, false],
	["spine_02", Vector3(1, 0, 0), 0.7, 2, 0.0, false],
	["spine_02", Vector3(0, 1, 0), 0.9, 1, 0.25, false],
	["spine_03", Vector3(1, 0, 0), 0.9, 2, 0.02, false],
	["spine_04", Vector3(1, 0, 0), 0.8, 2, 0.04, false],
	["spine_05", Vector3(1, 0, 0), 0.6, 2, 0.06, false],
	["spine_03", Vector3(0, 0, 1), -0.6, 1, 0.1, false],
	["clavicle_l", Vector3(0, 0, 1), 1.2, 2, 0.05, true],
	["clavicle_r", Vector3(0, 0, 1), 1.2, 2, 0.05, true],
	["neck_01", Vector3(0, 1, 0), 1.5, 1, 0.3, false],
	["neck_02", Vector3(0, 1, 0), 1.5, 1, 0.38, false],
	["head", Vector3(0, 1, 0), 1.5, 1, 0.46, false],
	["head", Vector3(1, 0, 0), 1.2, 3, 0.1, false],
	["head", Vector3(0, 0, 1), 0.8, 2, 0.6, false],
]


func _build_idle() -> void:
	var skeleton: Skeleton3D = _body_skeleton
	var to_skeleton: Basis = global_transform.basis.inverse() * skeleton.global_transform.basis
	var from_character: Basis = to_skeleton.inverse()
	var steps: int = int(IDLE_LENGTH / IDLE_STEP)
	var animation: Animation = Animation.new()
	animation.length = IDLE_LENGTH
	animation.loop_mode = Animation.LOOP_LINEAR
	var skeleton_path: String = str(get_path_to(skeleton))
	var bones: Dictionary = {}
	for motion: Array in IDLE_MOTIONS:
		bones[motion[0]] = true
	bones["upperarm_l"] = true
	bones["upperarm_r"] = true
	for bone_name: String in bones.keys():
		var index: int = skeleton.find_bone(bone_name)
		if index < 0:
			continue
		var rest_local: Quaternion = skeleton.get_bone_rest(index).basis.get_rotation_quaternion()
		var rest_global_basis: Basis = skeleton.get_bone_global_rest(index).basis.orthonormalized()
		var rest_global: Quaternion = rest_global_basis.get_rotation_quaternion()
		var side: float = 1.0 if (to_skeleton * skeleton.get_bone_global_rest(index).origin).x >= 0.0 else -1.0
		var track: int = animation.add_track(Animation.TYPE_ROTATION_3D)
		animation.track_set_path(track, NodePath(skeleton_path + ":" + bone_name))
		animation.track_set_interpolation_type(track, Animation.INTERPOLATION_CUBIC)
		animation.track_set_interpolation_loop_wrap(track, true)
		for step: int in range(steps + 1):
			var cycle: float = float(step) / float(steps)  # 0..1 through the loop; the last key equals the first
			var delta: Quaternion = Quaternion.IDENTITY
			for motion: Array in IDLE_MOTIONS:
				if motion[0] != bone_name:
					continue
				var amplitude: float = deg_to_rad(motion[2] as float) * idle_strength
				var mirror: float = side if (motion[5] as bool) else 1.0
				var angle: float = amplitude * mirror * sin(TAU * ((motion[3] as float) * cycle + (motion[4] as float)))
				delta = Quaternion(from_character * (motion[1] as Vector3).normalized(), angle) * delta
			if bone_name.begins_with("upperarm_"):
				delta = Quaternion(from_character * Vector3(0, 0, 1), -side * deg_to_rad(arm_drop_degrees) * idle_strength) * delta
			var local_delta: Quaternion = rest_global.inverse() * delta * rest_global
			animation.rotation_track_insert_key(track, cycle * IDLE_LENGTH, rest_local * local_delta)
	var library: AnimationLibrary = AnimationLibrary.new()
	library.add_animation(&"idle", animation)
	var player: AnimationPlayer = AnimationPlayer.new()
	player.name = "IdleAnimation"
	add_child(player)
	player.root_node = NodePath("..")
	player.add_animation_library(&"", library)
	_load_animation_packs(player, library)
	player.play(&"idle")


## Libraries saved by retarget_animation.gd under <character folder>/animations/ are added automatically: a library holding one clip
## becomes a plain animation named after its file ("jab_right"); a library with several clips keeps them under "<file>/<clip>".
func _load_animation_packs(player: AnimationPlayer, default_library: AnimationLibrary) -> void:
	var folder: String = scene_file_path.get_base_dir() + "/animations"
	if not DirAccess.dir_exists_absolute(folder):
		return
	for file_name: String in ResourceLoader.list_directory(folder):
		if not (file_name.ends_with(".res") or file_name.ends_with(".tres")):
			continue
		var pack: AnimationLibrary = load(folder + "/" + file_name) as AnimationLibrary
		if pack == null:
			continue
		var base: StringName = StringName(file_name.get_basename())
		var clips: PackedStringArray = pack.get_animation_list()
		if clips.size() == 1:
			default_library.add_animation(base, pack.get_animation(clips[0]))
		elif clips.size() > 1:
			player.add_animation_library(base, pack)
