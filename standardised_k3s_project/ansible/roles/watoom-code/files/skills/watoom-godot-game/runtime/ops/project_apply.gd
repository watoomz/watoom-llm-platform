extends RefCounted
## args: {settings: [{key, type, value}], actions: {name: [keycodes...]}}  types: int float bool string vec2i color
## Sets typed ProjectSettings and saves project.godot. Python never hand-writes typed settings.
static func to_typed(t: String, v):
	match t:
		"int": return int(v)
		"float": return float(v)
		"bool": return bool(v)
		"string": return str(v)
		"vec2i": return Vector2i(int(v[0]), int(v[1]))
		"color": return Color(float(v[0]), float(v[1]), float(v[2]))
	return null

static func action(keys: Array) -> Dictionary:
	var evs: Array = []
	for k in keys:
		var e := InputEventKey.new()
		e.physical_keycode = OS.find_keycode_from_string(str(k))
		evs.append(e)
	return {"deadzone": 0.5, "events": evs}

func run(_tree: SceneTree, args: Dictionary) -> Dictionary:
	var n := 0
	for s in args.get("settings", []):
		var v = to_typed(str(s["type"]), s["value"])
		if v == null:
			return {"ok": false, "error": "unknown setting type '%s' for %s" % [s["type"], s["key"]]}
		ProjectSettings.set_setting(str(s["key"]), v)
		n += 1
	var actions: Dictionary = args.get("actions", {})
	for a in actions:
		ProjectSettings.set_setting("input/" + str(a), action(actions[a]))
		n += 1
	var err := ProjectSettings.save()
	if err != OK:
		return {"ok": false, "error": "ProjectSettings.save failed (%d)" % err}
	return {"ok": true, "data": {"set": n}}
