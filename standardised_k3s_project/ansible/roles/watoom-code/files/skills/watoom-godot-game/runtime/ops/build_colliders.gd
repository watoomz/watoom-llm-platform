extends RefCounted
## Builds res://levels/<level>/colliders.tscn: one StaticBody3D holding the SOLID scatter instances (a MultiMesh never collides).
## args: {level, shapes: [[kind, x, y, z, r, h], ...]} kind "cyl" (cylinder, centre at y + h/2) or "box" (r = half extent x/z, h = full height).
const Save := preload("res://addons/gg/lib/save.gd")

func run(_tree: SceneTree, args: Dictionary) -> Dictionary:
	var body := StaticBody3D.new()
	body.name = "Colliders"
	var n := 0
	for s in args["shapes"]:
		var cs := CollisionShape3D.new()
		cs.name = "S%d" % n
		if str(s[0]) == "cyl":
			var cy := CylinderShape3D.new()
			cy.radius = float(s[4])
			cy.height = float(s[5])
			cs.shape = cy
		else:
			var bx := BoxShape3D.new()
			bx.size = Vector3(float(s[4]) * 2.0, float(s[5]), float(s[4]) * 2.0)
			cs.shape = bx
		cs.position = Vector3(float(s[1]), float(s[2]) + float(s[5]) * 0.5, float(s[3]))
		body.add_child(cs)
		n += 1
	if n == 0:
		var empty := Node3D.new()
		empty.name = "Colliders"
		var saved0 := Save.save_scene(empty, "res://levels/%s/colliders.tscn" % args["level"])
		return {"ok": saved0["ok"], "error": saved0.get("error", ""), "data": {"scene": "res://levels/%s/colliders.tscn" % args["level"], "shapes": 0, "reload_count": 0}}
	var out := "res://levels/%s/colliders.tscn" % args["level"]
	var saved := Save.save_scene(body, out)
	if not saved["ok"]:
		return saved
	var back: Node = (ResourceLoader.load(out, "PackedScene", ResourceLoader.CACHE_MODE_IGNORE) as PackedScene).instantiate()
	var got := back.get_child_count()
	back.free()
	if got != n:
		return {"ok": false, "error": "reloaded colliders hold %d shapes, built %d" % [got, n]}
	return {"ok": true, "data": {"scene": out, "shapes": n, "reload_count": got}}
