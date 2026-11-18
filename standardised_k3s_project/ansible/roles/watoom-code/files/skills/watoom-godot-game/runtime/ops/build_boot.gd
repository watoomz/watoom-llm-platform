extends RefCounted
## Builds the style probe into res://levels/_boot/boot.tscn with the save protocol:
## build, set owner on every node, pack, save <name>.new.tscn, reload (ignore cache), compare node counts, rename over the final.
## args: {style, dimension, out: "res://levels/_boot/boot.tscn"}
const Probe := preload("res://addons/gg/probe/probe_scene.gd")

static func count(n: Node) -> int:
	var c := 1
	for k in n.get_children():
		c += count(k)
	return c

static func set_owner_rec(n: Node, owner_node: Node) -> void:
	for k in n.get_children():
		k.owner = owner_node
		set_owner_rec(k, owner_node)

func run(_tree: SceneTree, args: Dictionary) -> Dictionary:
	var out := str(args["out"])
	var tmp := out.replace(".tscn", ".new.tscn")
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(out.get_base_dir()))
	var root: Node = Node3D.new() if str(args.get("dimension", "3d")) == "3d" else Node2D.new()
	root.name = "Boot"
	Probe.new().build(root, {"style": args["style"], "dimension": args.get("dimension", "3d")})
	set_owner_rec(root, root)
	var want := count(root)
	var packed := PackedScene.new()
	var err := packed.pack(root)
	if err != OK:
		return {"ok": false, "error": "pack failed (%d)" % err}
	err = ResourceSaver.save(packed, tmp)
	if err != OK:
		return {"ok": false, "error": "save failed (%d): %s" % [err, tmp]}
	var back = ResourceLoader.load(tmp, "PackedScene", ResourceLoader.CACHE_MODE_IGNORE)
	if back == null:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(tmp))
		return {"ok": false, "error": "reload of %s failed" % tmp}
	var inst: Node = back.instantiate()
	var got := count(inst)
	inst.free()
	if got != want:
		DirAccess.remove_absolute(ProjectSettings.globalize_path(tmp))
		return {"ok": false, "error": "reload mismatch: built %d nodes, reloaded %d (nodes without owner are dropped on save)" % [want, got]}
	DirAccess.rename_absolute(ProjectSettings.globalize_path(tmp), ProjectSettings.globalize_path(out))
	root.free()
	return {"ok": true, "data": {"scene": out, "nodes": got}}
