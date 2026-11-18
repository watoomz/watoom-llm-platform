extends RefCounted
## T-0068: merges separately-exported animation glbs onto a character mesh's skeleton and drives an
## AnimationTree state machine across them. No BoneMap/SkeletonProfile retargeting is needed here (checked
## first, see references/gg-combat.md once T-0073 writes it): the rogue's mesh and all its MM_* animation
## glbs share one identical 161-bone armature by name (Unreal's export convention when mesh and animations
## come from the same Skeletal Mesh), so an animation's tracks apply directly once copied onto the mesh's own
## AnimationPlayer with matching relative paths.
## args: {mesh: "res://...", states: {state_name: anim_glb_res_path, ...}, transitions: [[from, to], ...]}
## data: {checks: [{name, ok, detail}]}.

## The source glb's own node hierarchy (e.g. "Mesh/Skeleton3D") can differ from the target skeleton's actual
## path in the character being driven -- different exporters (Unreal's own GLTFExporter vs a Blender
## re-export, see T-0067) name/nest the wrapper node around Skeleton3D differently even when the bones
## themselves are identical. Every track still points at exactly one Skeleton3D with a bone subname, so
## rewriting each track's path onto the REAL target skeleton's path (keeping the bone subname) makes the
## animation apply regardless of how the source file happened to be structured.
func _load_anim_from_glb(tree: SceneTree, glb_path: String, target_skeleton_path: NodePath) -> Animation:
	var packed = load(glb_path)
	if packed == null:
		return null
	var temp: Node = (packed as PackedScene).instantiate()
	tree.root.add_child(temp)
	var player: AnimationPlayer = null
	for c in temp.get_children():
		if c is AnimationPlayer:
			player = c
	var anim: Animation = null
	if player != null:
		for lib_name in player.get_animation_library_list():
			var lib := player.get_animation_library(lib_name)
			var names := lib.get_animation_list()
			if names.size() > 0:
				anim = lib.get_animation(names[0])
				break
	if anim != null:
		for i in range(anim.get_track_count()):
			var bone := anim.track_get_path(i).get_concatenated_subnames()
			anim.track_set_path(i, NodePath(str(target_skeleton_path) + ":" + bone))
	temp.queue_free()
	return anim


func run(tree: SceneTree, args: Dictionary) -> Dictionary:
	var packed = load(str(args["mesh"]))
	if packed == null:
		return {"ok": false, "error": "cannot load mesh %s" % args["mesh"]}
	var character: Node = (packed as PackedScene).instantiate()
	tree.root.add_child(character)

	var skeleton: Skeleton3D = character.find_child("Skeleton3D", true, false)
	if skeleton == null:
		return {"ok": false, "error": "no Skeleton3D found under the mesh"}
	var pose_bone := skeleton.find_bone("pelvis")   # root motion is usually baked at the pelvis, not the root bone itself
	if pose_bone < 0:
		pose_bone = 0

	var player := AnimationPlayer.new()
	player.name = "AnimationPlayer"
	character.add_child(player)
	var lib := AnimationLibrary.new()
	player.add_animation_library("", lib)

	var skeleton_rel_path := character.get_path_to(skeleton)
	var states: Dictionary = args.get("states", {})
	var missing: Array = []
	for state_name in states:
		var anim := _load_anim_from_glb(tree, str(states[state_name]), skeleton_rel_path)
		if anim == null:
			missing.append(state_name)
			continue
		lib.add_animation(state_name, anim)
	await tree.process_frame

	var checks: Array = []
	checks.append({"name": "every requested animation was found and merged onto the shared skeleton", "ok": missing.is_empty(), "detail": "missing=%s" % [missing]})

	var sm := AnimationNodeStateMachine.new()
	for state_name in states:
		if missing.has(state_name):
			continue
		var node := AnimationNodeAnimation.new()
		node.animation = state_name
		sm.add_node(state_name, node)
	for pair in args.get("transitions", []):
		if sm.has_node(pair[0]) and sm.has_node(pair[1]):
			sm.add_transition(pair[0], pair[1], AnimationNodeStateMachineTransition.new())

	var anim_tree := AnimationTree.new()
	character.add_child(anim_tree)
	anim_tree.tree_root = sm
	anim_tree.anim_player = anim_tree.get_path_to(player)
	anim_tree.active = true
	await tree.process_frame

	var playback: AnimationNodeStateMachinePlayback = anim_tree.get("parameters/playback")
	var first_state: String = states.keys()[0] if states.size() > 0 else ""
	if not missing.has(first_state):
		playback.start(first_state)

	for state_name in states.keys():
		if missing.has(state_name):
			continue
		playback.travel(state_name)
		for i in range(6):
			await tree.process_frame
		var travelled: bool = playback.get_current_node() == state_name
		var pose_a := skeleton.get_bone_global_pose(pose_bone)
		for i in range(10):
			await tree.process_frame
		var pose_b := skeleton.get_bone_global_pose(pose_bone)
		# a looping or long clip visibly moves the root/pelvis bone over a few more frames; if it doesn't,
		# the AnimationTree is driving nothing and the rig is sitting in whatever pose it last had (a
		# T-pose, most likely, since that's the Skeleton3D's import-time rest pose).
		var moved := not pose_a.origin.is_equal_approx(pose_b.origin) or not pose_a.basis.is_equal_approx(pose_b.basis)
		checks.append({"name": "state machine transitions to '%s' and it visibly animates (not a frozen T-pose)" % state_name,
			"ok": travelled and moved, "detail": "travelled=%s moved=%s current=%s" % [travelled, moved, playback.get_current_node()]})

	character.queue_free()
	var checks_ok := true
	for row in checks:
		checks_ok = checks_ok and row["ok"]
	return {"ok": checks_ok, "error": null if checks_ok else "one or more animation checks failed", "data": {"checks": checks}}
