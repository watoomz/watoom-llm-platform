extends RefCounted
## Runs INSIDE an exported pack (godot --main-pack X.pck -s res://addons/gg/gg_runner.gd): proves the shipped level loads and its player and camera exist.
## args: {scene: "res://levels/<level>/level.tscn"}. Data: nodes, has_player, has_camera, main_scene, has_gg_data.
func _count(n: Node) -> int:
	var c := 1
	for k in n.get_children():
		c += _count(k)
	return c

func run(tree: SceneTree, args: Dictionary) -> Dictionary:
	var packed = load(str(args["scene"]))
	if packed == null:
		return {"ok": false, "error": "the pack cannot load %s" % args["scene"]}
	var level: Node = (packed as PackedScene).instantiate()
	tree.root.add_child(level)
	await tree.process_frame
	var player := level.get_node_or_null("Player") as CharacterBody3D
	var cams := level.find_children("*", "Camera3D", true, false)
	var data := {"nodes": _count(level), "has_player": player != null, "has_camera": not cams.is_empty(),
		"main_scene": str(ProjectSettings.get_setting("application/run/main_scene", "")),
		"has_gg_data": DirAccess.dir_exists_absolute("res://gg_data")}
	if player == null:
		return {"ok": false, "error": "the shipped level has no node named Player", "data": data}
	if cams.is_empty():
		return {"ok": false, "error": "the shipped level has no Camera3D", "data": data}
	return {"ok": true, "data": data}
