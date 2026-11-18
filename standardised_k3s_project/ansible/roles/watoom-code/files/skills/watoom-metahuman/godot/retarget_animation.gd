extends SceneTree
## Retargets every animation in a source FBX/GLB onto a MetaHuman body skeleton and saves an AnimationLibrary.
##
##   godot --headless --path <project> -s res://metahuman/MHC_Base_Female/retarget_animation.gd -- \
##       --source res://anims/pack/jab_right.fbx --character res://metahuman/MHC_Base_Female/MHC_Base_Female.tscn \
##       [--map auto|identity|mixamo] [--out res://metahuman/MHC_Base_Female/animations/jab.res] [--keep-root] [--fps 30]
##   godot --headless --path <project> -s res://metahuman/MHC_Base_Female/retarget_animation.gd -- --source res://x.fbx --inspect
##
## Method (all in world space): each mapped bone gets the source's rotation change from its rest pose, the whole motion is turned to the
## character's facing, limb bones are then re-aimed so they point where the source bone points (a T-pose source on an A-pose character would
## otherwise leave arms and legs offset), and hips motion is scaled by the height ratio. Rotations are written, plus pelvis position.
## Unmapped bones keep their rest pose. Facial motion is not carried. A Hips node above the skeleton (FBX exporters often do this) is
## treated as the pelvis.

const HIPS_NODE: int = -2
const FINGERS: Dictionary = {"thumb": "thumb", "index": "index", "middle": "middle", "ring": "ring", "pinky": "pinky"}

var _args: Dictionary = {}
var _skel: Skeleton3D
var _hips_node: Node3D
var _current: String = ""


func _init() -> void:
	var raw: PackedStringArray = OS.get_cmdline_user_args()
	var i: int = 0
	while i < raw.size():
		var key: String = raw[i].trim_prefix("--")
		if i + 1 < raw.size() and not raw[i + 1].begins_with("--"):
			_args[key] = raw[i + 1]
			i += 2
		else:
			_args[key] = "true"
			i += 1
	call_deferred("_run")


func _fail(message: String) -> void:
	printerr("RETARGET FAIL: ", message)
	quit(2)


func _find_skeleton(r: Node) -> Skeleton3D:
	for n: Node in r.find_children("*", "Skeleton3D", true, false):
		return n as Skeleton3D
	return null


func _norm(bone: String) -> String:
	var n: String = bone.to_lower()
	if ":" in n:
		n = n.get_slice(":", n.get_slice_count(":") - 1)
	return n.replace("_", "").replace(" ", "")


func _rot(b: Basis) -> Quaternion:
	return b.orthonormalized().get_rotation_quaternion()


func _world(joint: int) -> Transform3D:
	if joint == HIPS_NODE:
		return _hips_node.global_transform
	return _skel.global_transform * _skel.get_bone_global_pose(joint)


## Returns source joint (bone index, or HIPS_NODE) -> target bone index.
func _build_map(target: Skeleton3D, mode: String) -> Dictionary:
	var keys: Dictionary = {}
	for b: int in range(_skel.get_bone_count()):
		keys[_norm(_skel.get_bone_name(b))] = b
	if mode == "auto":
		mode = "identity" if (_skel.find_bone("pelvis") >= 0 and _skel.find_bone("upperarm_l") >= 0) else "mixamo"
	var map: Dictionary = {}
	if mode == "identity":
		for b: int in range(_skel.get_bone_count()):
			var t: int = target.find_bone(_skel.get_bone_name(b))
			if t >= 0:
				map[b] = t
		return map
	var names: Dictionary = {"hips": "pelvis", "neck": "neck_01", "neck1": "neck_01", "neck2": "neck_02", "head": "head",
		"leftshoulder": "clavicle_l", "leftarm": "upperarm_l", "leftforearm": "lowerarm_l", "lefthand": "hand_l",
		"rightshoulder": "clavicle_r", "rightarm": "upperarm_r", "rightforearm": "lowerarm_r", "righthand": "hand_r",
		"leftupleg": "thigh_l", "leftfoot": "foot_l", "lefttoebase": "ball_l", "rightupleg": "thigh_r", "rightfoot": "foot_r", "righttoebase": "ball_r"}
	# Spine: Mixamo has Spine/Spine1/Spine2; some packs drop Spine and add Chest (Spine1/Spine2/Chest). Spread over the 5 MetaHuman spine bones.
	var spine: Array = ["spine", "spine1", "spine2"] if keys.has("spine") else ["spine1", "spine2", "chest"]
	for k: int in range(spine.size()):
		names[spine[k]] = ["spine_01", "spine_03", "spine_05"][k]
	if keys.has("spine3"):  # four-bone spine (Spine..Spine3): spread over the five MetaHuman spine bones
		names["spine"] = "spine_01"
		names["spine1"] = "spine_02"
		names["spine2"] = "spine_03"
		names["spine3"] = "spine_05"
	if keys.has("neck") and keys.has("neck1"):
		names["neck1"] = "neck_02"
	# Legs: standard Mixamo is UpLeg/Leg(calf); the Shin variant is Leg(thigh)/Shin(calf).
	if keys.has("leftshin"):
		names["leftleg"] = "thigh_l"
		names["leftshin"] = "calf_l"
		names["rightleg"] = "thigh_r"
		names["rightshin"] = "calf_r"
	else:
		names["leftleg"] = "calf_l"
		names["rightleg"] = "calf_r"
	for key: String in keys.keys():
		var tname: String = ""
		if names.has(key):
			tname = names[key]
		else:
			for side: String in ["left", "right"]:
				if key.begins_with(side + "hand"):
					var rest: String = key.trim_prefix(side + "hand")
					for finger: String in FINGERS.keys():
						if rest.begins_with(finger):
							var number: int = int(rest.trim_prefix(finger))
							if number >= 1 and number <= 3:
								tname = "%s_%02d_%s" % [FINGERS[finger], number, side.left(1)]
		if tname != "" and target.find_bone(tname) >= 0:
			map[keys[key]] = target.find_bone(tname)
	if not map.values().has(target.find_bone("pelvis")) and _hips_node != null:
		map[HIPS_NODE] = target.find_bone("pelvis")
	return map


## Is the source's rest pose a usable neutral (T/A) pose? Baked mocap files use the first animation frame as "rest", which is not.
func _rest_is_neutral(map: Dictionary, target: Skeleton3D) -> bool:
	var t_left: int = target.find_bone("upperarm_l")
	var t_right: int = target.find_bone("upperarm_r")
	var t_elbow: int = target.find_bone("lowerarm_l")
	var s_of_t: Dictionary = {}
	for sj: int in map.keys():
		s_of_t[map[sj]] = sj
	if not (s_of_t.has(t_left) and s_of_t.has(t_right) and s_of_t.has(t_elbow)):
		return true
	var left_xf: Transform3D = _skel.global_transform * _skel.get_bone_global_rest(s_of_t[t_left])
	var right_xf: Transform3D = _skel.global_transform * _skel.get_bone_global_rest(s_of_t[t_right])
	var elbow_xf: Transform3D = _skel.global_transform * _skel.get_bone_global_rest(s_of_t[t_elbow])
	var axis: Vector3 = right_xf.origin - left_xf.origin
	var arm: Vector3 = elbow_xf.origin - left_xf.origin
	if axis.length() < 1e-4 or arm.length() < 1e-4:
		return true
	var flat: Vector3 = Vector3(axis.x, 0.0, axis.z)
	var axis_ok: bool = absf(axis.normalized().y) < 0.2 and (absf(flat.normalized().x) > 0.96 or absf(flat.normalized().z) > 0.96)
	var arm_out: bool = arm.normalized().dot(-axis.normalized()) > 0.7
	return axis_ok and arm_out


## Two-vector orientation change: rotation taking a rest frame (aim a0, side s0) to a current frame (a1, s1).
func _frame_rotation(a0: Vector3, s0: Vector3, a1: Vector3, s1: Vector3) -> Quaternion:
	var b0: Basis = _frame_basis(a0, s0)
	var b1: Basis = _frame_basis(a1, s1)
	return (b1 * b0.inverse()).get_rotation_quaternion()


func _frame_basis(aim: Vector3, side: Vector3) -> Basis:
	var y: Vector3 = aim.normalized()
	var x: Vector3 = (side - y * side.dot(y))
	if x.length() < 1e-5:
		x = y.cross(Vector3.FORWARD) if absf(y.dot(Vector3.FORWARD)) < 0.9 else y.cross(Vector3.RIGHT)
	x = x.normalized()
	return Basis(x, y, x.cross(y).normalized())


## Pose solver for sources whose rest pose is not neutral: rebuilds each bone's orientation from the source's joint POSITIONS (aim along the
## limb, torso twist from the hip and shoulder lines, leaf bones follow their parent). Roll about a limb's own axis is not recovered.
func _pose_globals(order: Array, s_of_t: Dictionary, target: Skeleton3D, t_children: Dictionary, t_rest_global: Array[Quaternion], yaw: Quaternion, t_frame: Quaternion) -> Dictionary:
	var out: Dictionary = {}
	var fix: Dictionary = {}
	var hip_l: int = target.find_bone("thigh_l")
	var hip_r: int = target.find_bone("thigh_r")
	var sh_l: int = target.find_bone("upperarm_l")
	var sh_r: int = target.find_bone("upperarm_r")
	var have_lines: bool = s_of_t.has(hip_l) and s_of_t.has(hip_r) and s_of_t.has(sh_l) and s_of_t.has(sh_r)
	var hip_t: Vector3 = Vector3.ZERO
	var sh_t: Vector3 = Vector3.ZERO
	var hip_s: Vector3 = Vector3.ZERO
	var sh_s: Vector3 = Vector3.ZERO
	if have_lines:
		hip_t = target.get_bone_global_rest(hip_r).origin - target.get_bone_global_rest(hip_l).origin
		sh_t = target.get_bone_global_rest(sh_r).origin - target.get_bone_global_rest(sh_l).origin
		hip_s = _src_pos(s_of_t, hip_r, yaw, t_frame) - _src_pos(s_of_t, hip_l, yaw, t_frame)
		sh_s = _src_pos(s_of_t, sh_r, yaw, t_frame) - _src_pos(s_of_t, sh_l, yaw, t_frame)
	var chain: Array = []
	for n: String in ["pelvis", "spine_01", "spine_02", "spine_03", "spine_04", "spine_05", "neck_01", "neck_02", "head"]:
		var b: int = target.find_bone(n)
		if b >= 0 and order.has(b):
			chain.append(b)
	for tb: int in order:
		var kids: Array = t_children.get(tb, [])
		var ci: int = chain.find(tb)
		if ci >= 0:
			kids = [chain[ci + 1]] if ci + 1 < chain.size() else []
		if kids.is_empty():
			continue
		var aim_t: Vector3 = Vector3.ZERO
		var aim_s: Vector3 = Vector3.ZERO
		for k: int in kids:
			aim_t += target.get_bone_global_rest(k).origin
			aim_s += _src_pos(s_of_t, k, yaw, t_frame)
		aim_t = aim_t / float(kids.size()) - target.get_bone_global_rest(tb).origin
		aim_s = aim_s / float(kids.size()) - _src_pos(s_of_t, tb, yaw, t_frame)
		if aim_t.length() < 1e-4 or aim_s.length() < 1e-4:
			continue
		var q: Quaternion
		if ci >= 0 and have_lines:
			var f: float = float(ci) / float(maxi(chain.size() - 1, 1))
			q = _frame_rotation(aim_t, hip_t.lerp(sh_t, f), aim_s, hip_s.lerp(sh_s, f))
		else:
			var a: Vector3 = aim_t.normalized()
			var b2: Vector3 = aim_s.normalized()
			q = Quaternion(a, b2) if a.dot(b2) < 0.99999 else Quaternion.IDENTITY
		fix[tb] = q
		out[tb] = q * t_rest_global[tb]
	for tb: int in order:
		if out.has(tb):
			continue
		var tp: int = target.get_bone_parent(tb)
		while tp >= 0 and not fix.has(tp):
			tp = target.get_bone_parent(tp)
		out[tb] = ((fix[tp] as Quaternion) if tp >= 0 else Quaternion.IDENTITY) * t_rest_global[tb]
	return out


func _src_pos(s_of_t: Dictionary, target_bone: int, yaw: Quaternion, t_frame: Quaternion) -> Vector3:
	return t_frame.inverse() * (yaw * _world(s_of_t[target_bone]).origin)


## Retargets every clip of one source file into `library`; returns the clip count, or -1 when the file is skipped.
func _retarget_one(source_path: String, character_path: String, character: Node3D, library: AnimationLibrary, stem_names: bool) -> int:
	_current = source_path.get_file()
	var source_packed: PackedScene = load(source_path) as PackedScene
	if source_packed == null:
		_skip("cannot load source " + source_path + " (import it first: godot --headless --import)")
		return -1
	var source_root: Node3D = source_packed.instantiate() as Node3D
	root.add_child(source_root)
	_skel = _find_skeleton(source_root)
	var player: AnimationPlayer = null
	for n: Node in source_root.find_children("*", "AnimationPlayer", true, false):
		player = n as AnimationPlayer
		break
	if _skel == null:
		_skip("source has no Skeleton3D")
		return -1
	var parent: Node = _skel.get_parent()
	if parent is Node3D and _norm(parent.name) == "hips":
		_hips_node = parent as Node3D
	if _args.has("inspect"):
		var listed: PackedStringArray = []
		for b: int in range(min(_skel.get_bone_count(), 14)):
			listed.append(_skel.get_bone_name(b))
		print("INSPECT bones=", _skel.get_bone_count(), " first=", listed, " hips_node=", _hips_node != null)
		if player != null:
			for clip: String in player.get_animation_list():
				print("INSPECT clip ", clip, " length ", player.get_animation(clip).length)
		return 0
	var target: Skeleton3D = _find_skeleton(character.get_node("Body"))
	if target == null or player == null:
		_skip("character body skeleton or source animations missing")
		return -1
	var map: Dictionary = _build_map(target, _args.get("map", "auto"))
	print("MAPPED joints: ", map.size())
	if map.size() < 8:
		_skip("too few bones mapped (" + str(map.size()) + "); try --map mixamo|identity or --inspect the source")
		return -1
	var fps: float = float(_args.get("fps", "30"))
	var keep_root: bool = _args.has("keep-root")
	var t_frame: Quaternion = _rot(character.global_transform.basis.inverse() * target.global_transform.basis)  # target skeleton space -> character space
	var count: int = target.get_bone_count()
	var t_rest_global: Array[Quaternion] = []
	var t_rest_local: Array[Quaternion] = []
	for b: int in range(count):
		t_rest_global.append(_rot(target.get_bone_global_rest(b).basis))
		t_rest_local.append(target.get_bone_rest(b).basis.get_rotation_quaternion())
	# Rest data of the source, taken before any animation runs.
	var s_rest_rot: Dictionary = {}
	var s_rest_origin: Dictionary = {}
	for sj: int in map.keys():
		var rest_xf: Transform3D = _world(sj) if sj == HIPS_NODE else _skel.global_transform * _skel.get_bone_global_rest(sj)
		s_rest_rot[sj] = _rot(rest_xf.basis)
		s_rest_origin[sj] = rest_xf.origin
	var s_of_t: Dictionary = {}
	for sj: int in map.keys():
		s_of_t[map[sj]] = sj
	var order: Array = map.values()
	order.sort()
	var pelvis: int = target.find_bone("pelvis")
	var pose_mode: bool = _args.get("solver", "auto") == "pose" or (_args.get("solver", "auto") == "auto" and not _rest_is_neutral(map, target))
	print("SOLVER ", "pose (source rest is not a neutral pose)" if pose_mode else "delta")
	var first_clip: String = ""
	for cn: String in player.get_animation_list():
		if cn != "RESET":
			first_clip = cn
			break
	if pose_mode and first_clip != "":
		player.play(first_clip)
		player.seek(0.0, true)
		player.advance(0.0)
	# Facing: the clip's left->right shoulder axis (its first frame in pose mode, the rest pose otherwise) turned onto the character's.
	var yaw: Quaternion = Quaternion.IDENTITY
	var t_left: int = target.find_bone("upperarm_l")
	var t_right: int = target.find_bone("upperarm_r")
	if pose_mode and s_of_t.has(target.find_bone("thigh_l")) and s_of_t.has(target.find_bone("thigh_r")):
		t_left = target.find_bone("thigh_l")  # the hips face the direction of travel; the shoulders may be mid-twist at frame 0
		t_right = target.find_bone("thigh_r")
	if s_of_t.has(t_left) and s_of_t.has(t_right):
		var t_axis: Vector3 = t_frame * (target.get_bone_global_rest(t_right).origin - target.get_bone_global_rest(t_left).origin)
		var s_axis: Vector3 = (_world(s_of_t[t_right]).origin - _world(s_of_t[t_left]).origin) if pose_mode else ((s_rest_origin[s_of_t[t_right]] as Vector3) - (s_rest_origin[s_of_t[t_left]] as Vector3))
		t_axis.y = 0.0
		s_axis.y = 0.0
		if t_axis.length() > 1e-5 and s_axis.length() > 1e-5:
			yaw = Quaternion(Vector3.UP, s_axis.normalized().signed_angle_to(t_axis.normalized(), Vector3.UP))
	var height_ratio: float = 1.0
	var t_thigh: int = target.find_bone("thigh_l")
	var t_calf: int = target.find_bone("calf_l")
	var t_foot: int = target.find_bone("foot_l")
	if s_of_t.has(t_thigh) and s_of_t.has(t_calf) and s_of_t.has(t_foot):
		var s_len: float = ((_world(s_of_t[t_calf]).origin - _world(s_of_t[t_thigh]).origin).length() + (_world(s_of_t[t_foot]).origin - _world(s_of_t[t_calf]).origin).length())
		var t_len: float = (target.get_bone_global_rest(t_calf).origin - target.get_bone_global_rest(t_thigh).origin).length() + (target.get_bone_global_rest(t_foot).origin - target.get_bone_global_rest(t_calf).origin).length()
		if s_len > 0.05:
			height_ratio = t_len / s_len  # leg length is stable even when the source "rest" is a crouch or mid-stride
	# mapped child of each mapped target bone (single-child chains get re-aimed)
	var t_children: Dictionary = {}
	for tb: int in order:
		var tp: int = target.get_bone_parent(tb)
		while tp >= 0 and not order.has(tp):
			tp = target.get_bone_parent(tp)
		if tp >= 0:
			t_children[tp] = t_children.get(tp, []) + [tb]
	var skeleton_path: String = str(character.get_path_to(target))
	var done: int = 0
	var usable: int = 0
	for cn: String in player.get_animation_list():
		if cn != "RESET":
			usable += 1
	for clip_name: String in player.get_animation_list():
		if clip_name == "RESET":
			continue
		var clip: Animation = player.get_animation(clip_name)
		var out: Animation = Animation.new()
		out.length = clip.length
		var tracks: Dictionary = {}
		for tb: int in order:
			var track: int = out.add_track(Animation.TYPE_ROTATION_3D)
			out.track_set_path(track, NodePath(skeleton_path + ":" + target.get_bone_name(tb)))
			tracks[tb] = track
		var pos_track: int = -1
		if s_of_t.has(pelvis):
			pos_track = out.add_track(Animation.TYPE_POSITION_3D)
			out.track_set_path(pos_track, NodePath(skeleton_path + ":pelvis"))
		var steps: int = maxi(int(ceil(clip.length * fps)), 1)
		var first_hip: Vector3 = Vector3.ZERO
		player.play(clip_name)
		for step: int in range(steps + 1):
			var t: float = minf(float(step) / fps, clip.length)
			player.seek(t, true)
			player.advance(0.0)
			var global_target: Dictionary = {}
			if pose_mode:
				global_target = _pose_globals(order, s_of_t, target, t_children, t_rest_global, yaw, t_frame)
			else:
				for tb: int in order:
					var sj: int = s_of_t[tb]
					var anim_rot: Quaternion = _rot(_world(sj).basis)
					var delta_world: Quaternion = yaw * (anim_rot * (s_rest_rot[sj] as Quaternion).inverse()) * yaw.inverse()
					var delta_target: Quaternion = t_frame.inverse() * delta_world * t_frame
					global_target[tb] = delta_target * t_rest_global[tb]
				var correction: Dictionary = {}
				for tb: int in order:
					var kids: Array = t_children.get(tb, [])
					if kids.size() != 1:
						continue
					var kid: int = kids[0]
					var dir_world: Vector3 = _world(s_of_t[kid]).origin - _world(s_of_t[tb]).origin
					if dir_world.length() < 1e-6:
						continue
					var s_dir: Vector3 = (t_frame.inverse() * (yaw * dir_world.normalized())).normalized()
					var rest_vec: Vector3 = target.get_bone_global_rest(kid).origin - target.get_bone_global_rest(tb).origin
					if rest_vec.length() < 1e-4 or s_dir.length() < 0.5:
						continue  # helper bones that share a position have no direction to aim
					var rest_dir: Vector3 = rest_vec.normalized()
					var current: Vector3 = ((global_target[tb] as Quaternion) * (t_rest_global[tb].inverse() * rest_dir)).normalized()
					if current.length() > 0.5 and current.dot(s_dir) < 0.99999:
						var fix: Quaternion = Quaternion(current, s_dir)
						correction[tb] = fix
						global_target[tb] = fix * (global_target[tb] as Quaternion)
				for tb: int in order:
					if correction.has(tb):
						continue
					var tp: int = target.get_bone_parent(tb)
					while tp >= 0 and not correction.has(tp):
						tp = target.get_bone_parent(tp)
					if tp >= 0:
						global_target[tb] = (correction[tp] as Quaternion) * (global_target[tb] as Quaternion)
			var final_global: Array[Quaternion] = []
			final_global.resize(count)
			for b: int in range(count):
				var par: int = target.get_bone_parent(b)
				var par_global: Quaternion = final_global[par] if par >= 0 else Quaternion.IDENTITY
				final_global[b] = global_target[b] if global_target.has(b) else par_global * t_rest_local[b]
			for tb: int in order:
				var par: int = target.get_bone_parent(tb)
				var par_global: Quaternion = final_global[par] if par >= 0 else Quaternion.IDENTITY
				out.rotation_track_insert_key(tracks[tb], t, par_global.inverse() * final_global[tb])
			if pos_track >= 0:
				var hips_pos: Vector3 = _world(s_of_t[pelvis]).origin
				if step == 0:
					first_hip = hips_pos
				var delta: Vector3 = yaw * (hips_pos - first_hip) * height_ratio
				if not keep_root:
					delta.x = 0.0
					delta.z = 0.0
				out.position_track_insert_key(pos_track, t, target.get_bone_rest(pelvis).origin + t_frame.inverse() * delta)
		player.stop()
		var clip_key: String = clip_name.replace(".", "_").replace(":", "_").replace("/", "_").replace("|", "_")
		if stem_names:
			clip_key = source_path.get_file().get_basename() if usable == 1 else source_path.get_file().get_basename() + "_" + clip_key
		library.add_animation(StringName(clip_key), out)
		done += 1
	print("RETARGET FILE ", source_path.get_file(), " clips=", done, " mapped=", map.size(), " solver=", "pose" if pose_mode else "delta", " height_ratio=", snappedf(height_ratio, 0.001), " yaw_deg=", snappedf(rad_to_deg(yaw.get_angle()), 0.1))
	return done


func _skip(message: String) -> void:
	printerr("RETARGET SKIP: ", _current, ": ", message)


func _collect(dir_path: String, out: PackedStringArray) -> void:
	for sub: String in DirAccess.get_directories_at(dir_path):
		_collect(dir_path.path_join(sub), out)
	for file_name: String in DirAccess.get_files_at(dir_path):
		var low: String = file_name.to_lower()
		if low.ends_with(".fbx") or low.ends_with(".glb") or low.ends_with(".gltf"):
			out.append(dir_path.path_join(file_name))


func _run() -> void:
	var character_path: String = _args.get("character", "")
	var inspect: bool = _args.has("inspect")
	var files: PackedStringArray = PackedStringArray()
	if _args.has("source-dir"):
		_collect(_args["source-dir"], files)
		files.sort()
	elif _args.has("source"):
		files.append(_args["source"])
	if files.is_empty() or (character_path == "" and not inspect):
		_fail("--source <file> or --source-dir <folder>, and --character, are required")
		return
	var character: Node3D = null
	if not inspect:
		character = (load(character_path) as PackedScene).instantiate() as Node3D
		root.add_child(character)
	var library: AnimationLibrary = AnimationLibrary.new()
	var total: int = 0
	var failed: PackedStringArray = PackedStringArray()
	var folder: bool = _args.has("source-dir")
	for file_path: String in files:
		var n: int = _retarget_one(file_path, character_path, character, library, folder)
		for c: Node in root.get_children():
			if c != character:
				c.queue_free()
		await process_frame
		_skel = null
		_hips_node = null
		if n < 0:
			failed.append(file_path.get_file())
		else:
			total += n
	if inspect:
		quit(0)
		return
	var out_path: String = _args.get("out", "")
	if out_path == "":
		var stem: String = (_args["source-dir"] as String).trim_suffix("/").get_file() if folder else (files[0] as String).get_file().get_basename()
		out_path = character_path.get_base_dir() + "/animations/" + stem + ".res"
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(out_path.get_base_dir()))
	var err: int = ResourceSaver.save(library, out_path, ResourceSaver.FLAG_COMPRESS)
	print("RETARGET OK files=", files.size() - failed.size(), "/", files.size(), " clips=", total, " saved=", out_path, " err=", err, " skipped=", failed)
	quit(0 if err == OK and total > 0 else 3)
