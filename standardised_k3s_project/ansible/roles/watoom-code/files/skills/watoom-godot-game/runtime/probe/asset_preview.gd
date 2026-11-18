extends RefCounted
## Capture builder: a neutral grey ground, the style's sky and sun, and (when ctx.scene is set) one asset at the origin.
## ctx: {style, scene: "res://...tscn" | ""}. Rendering it with and without the scene lets the caller find the asset's pixels by difference.
const Style := preload("res://addons/gg/lib/style.gd")
func build(parent: Node, ctx: Dictionary = {}) -> void:
	var style: Dictionary = ctx["style"]
	var we := WorldEnvironment.new()
	we.name = "WorldEnvironment"
	we.environment = Style.environment(style)
	parent.add_child(we)
	parent.add_child(Style.sun(style))
	var ground := MeshInstance3D.new()
	ground.name = "Ground"
	var pm := PlaneMesh.new()
	pm.size = Vector2(200, 200)
	ground.mesh = pm
	var gm := StandardMaterial3D.new()
	gm.albedo_color = Color(0.5, 0.5, 0.5)
	gm.roughness = 1.0
	ground.material_override = gm
	parent.add_child(ground)
	var s := str(ctx.get("scene", ""))
	if s != "":
		var packed = load(s)
		if packed == null:
			printerr("ERROR: asset_preview cannot load scene ", s)
		else:
			var asset: Node = packed.instantiate()
			parent.add_child(asset)
			# the difference between the empty and the asset render must be the asset's own pixels, not its shadow
			var stack: Array = [asset]
			while not stack.is_empty():
				var n: Node = stack.pop_back()
				if n is GeometryInstance3D:
					(n as GeometryInstance3D).cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
				stack.append_array(n.get_children())
	var post := Style.palette_layer(style)
	if post != null:
		parent.add_child(post)
