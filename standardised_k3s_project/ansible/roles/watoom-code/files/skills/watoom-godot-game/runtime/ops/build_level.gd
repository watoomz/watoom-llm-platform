extends RefCounted
## Builds res://levels/<level>/level.tscn: the style environment + sun + every scene in args.scenes INSTANCED by reference + the player at the start.
## args: {level, style, scenes:[res://...], player_scene, start:{position:[x,y,z], yaw_deg}}   Data: scene, instanced [paths], nodes.
const Save := preload("res://addons/gg/lib/save.gd")
const Style := preload("res://addons/gg/lib/style.gd")

func run(_tree: SceneTree, args: Dictionary) -> Dictionary:
	var root := Node3D.new()
	root.name = "Level"
	var we := WorldEnvironment.new()
	we.name = "WorldEnvironment"
	we.environment = Style.environment(args["style"])
	root.add_child(we)
	root.add_child(Style.sun(args["style"]))
	var inst: Array = []
	for s in args["scenes"]:
		var packed = load(str(s))
		if packed == null:
			return {"ok": false, "error": "cannot load %s" % s}
		var n: Node = (packed as PackedScene).instantiate()
		root.add_child(n)
		n.scene_file_path = str(s)
		inst.append(str(s))
	var pp = load(str(args["player_scene"]))
	if pp == null:
		return {"ok": false, "error": "cannot load %s" % args["player_scene"]}
	var player: Node3D = (pp as PackedScene).instantiate()
	var st: Dictionary = args["start"]
	root.add_child(player)
	player.position = Vector3(st["position"][0], st["position"][1], st["position"][2])
	player.rotation_degrees.y = float(st["yaw_deg"])
	var post := Style.palette_layer(args["style"])
	if post != null:
		root.add_child(post)
	var out := "res://levels/%s/level.tscn" % args["level"]
	var saved := Save.save_scene(root, out, true)
	if not saved["ok"]:
		return saved
	return {"ok": true, "data": {"scene": out, "instanced": inst + [str(args["player_scene"])], "nodes": saved["nodes"]}}
