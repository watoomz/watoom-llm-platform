extends RefCounted
## Capture builder for a level in progress: instances ctx.scenes and adds the style's environment and sun.
## ctx: {style, scenes: ["res://levels/main/terrain.tscn", ...]}
const Style := preload("res://addons/gg/lib/style.gd")
func build(parent: Node, ctx: Dictionary = {}) -> void:
	var style: Dictionary = ctx["style"]
	var we := WorldEnvironment.new()
	we.name = "WorldEnvironment"
	we.environment = Style.environment(style)
	parent.add_child(we)
	parent.add_child(Style.sun(style))
	for s in ctx.get("scenes", []):
		var packed = load(str(s))
		if packed == null:
			printerr("ERROR: level_preview cannot load scene ", s)
			continue
		parent.add_child(packed.instantiate())
	var post := Style.palette_layer(style)
	if post != null:
		parent.add_child(post)
