extends RefCounted
## Reads the real scenes and reports every instance of every MultiMeshInstance3D (family = meta gg_family, else the node name).
## args: {scenes:["res://levels/main/scatter.tscn", ...], out_json:"/abs/path.json"}. Writes {family:{count, positions:[[x,y,z]...], scales:[...], classified:bool}}
func _walk(n: Node, xf: Transform3D, fams: Dictionary) -> void:
	var t := xf
	if n is Node3D:
		t = xf * (n as Node3D).transform
	if n is MultiMeshInstance3D and (n as MultiMeshInstance3D).multimesh != null:
		var mm := (n as MultiMeshInstance3D).multimesh
		var nm: String = str(n.get_meta("gg_family")) if n.has_meta("gg_family") else str(n.name)
		if not fams.has(nm):
			fams[nm] = {"count": 0, "positions": [], "scales": [], "classified": n.has_meta("gg_family")}
		for i in range(mm.instance_count):
			var it := t * mm.get_instance_transform(i)
			fams[nm]["positions"].append([snappedf(it.origin.x, 0.001), snappedf(it.origin.y, 0.001), snappedf(it.origin.z, 0.001)])
			fams[nm]["scales"].append(snappedf(it.basis.get_scale().y, 0.001))
			fams[nm]["count"] += 1
	for k in n.get_children():
		_walk(k, t, fams)

func run(tree: SceneTree, args: Dictionary) -> Dictionary:
	var fams := {}
	for s in args["scenes"]:
		var packed = load(str(s))
		if packed == null:
			return {"ok": false, "error": "cannot load %s" % s}
		var inst: Node = (packed as PackedScene).instantiate()
		_walk(inst, Transform3D.IDENTITY, fams)
		inst.free()
	var f := FileAccess.open(str(args["out_json"]), FileAccess.WRITE)
	if f == null:
		return {"ok": false, "error": "cannot write %s" % args["out_json"]}
	f.store_string(JSON.stringify(fams))
	f.close()
	var counts := {}
	for k in fams.keys():
		counts[k] = fams[k]["count"]
	return {"ok": true, "data": {"families": counts}}
