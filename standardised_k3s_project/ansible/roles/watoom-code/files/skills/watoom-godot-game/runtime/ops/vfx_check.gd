extends RefCounted
## T-0069: proves each VFX recipe (game/vfx.gd) actually draws something live -- real GPUParticles3D in a
## real scene with a real Camera3D, rendered for real frames, read back from the viewport and checked for
## non-flat pixels (a blank/invisible recipe would render as one solid background colour).
## args: {fx: {name: {recipe, element, scale?, radius?}}}. data: {checks: [{name, ok, detail}]}.
const VFX := preload("res://addons/gg/game/vfx.gd")


func _luma_std(img: Image) -> float:
	var step := 2
	var sum := 0.0
	var sum_sq := 0.0
	var n := 0
	var w := img.get_width()
	var h := img.get_height()
	for y in range(0, h, step):
		for x in range(0, w, step):
			var c := img.get_pixel(x, y)
			var luma := c.r * 0.299 + c.g * 0.587 + c.b * 0.114
			sum += luma
			sum_sq += luma * luma
			n += 1
	if n == 0:
		return 0.0
	var mean := sum / n
	return sqrt(maxf(sum_sq / n - mean * mean, 0.0))


func run(tree: SceneTree, args: Dictionary) -> Dictionary:
	var holder := Node3D.new()
	tree.root.add_child(holder)
	var cam := Camera3D.new()
	holder.add_child(cam)
	# side-on, not front-on: a projectile/muzzle recipe moves along local Z, which a front camera (looking
	# down Z) reads mostly as depth -- a small quad barely grows/shrinks with it. Side-on reads it as lateral
	# screen movement instead, which any recipe's travel direction shows up as, not just the ones aimed at
	# the lens.
	cam.look_at_from_position(Vector3(2, 1, 0), Vector3.ZERO, Vector3.UP)
	cam.make_current()

	var fx: Dictionary = args.get("fx", {})
	var rows: Array = []
	for name in fx:
		var recipe: Dictionary = fx[name]
		var particles := VFX.build(recipe)
		holder.add_child(particles)
		particles.restart()
		for i in range(3):
			await tree.process_frame
		await RenderingServer.frame_post_draw
		var img: Image = tree.root.get_texture().get_image()
		var std := _luma_std(img)
		rows.append([str(name), std > 0.01, "recipe=%s luma_std=%.4f" % [recipe.get("recipe", "?"), std]])
		particles.queue_free()
		await tree.process_frame

	holder.queue_free()
	var checks: Array = []
	var ok := true
	for row in rows:
		checks.append({"name": row[0], "ok": row[1], "detail": row[2]})
		ok = ok and row[1]
	return {"ok": ok, "error": null if ok else "one or more VFX recipes rendered flat/blank", "data": {"checks": checks}}
