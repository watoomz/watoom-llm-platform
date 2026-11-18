extends RefCounted
## Reads settings back from disk (a fresh process) and compares with the requested typed values.
## args: same as project_apply. Returns data.mismatches = [{key, want, got}].
const Apply := preload("res://addons/gg/ops/project_apply.gd")
func run(_tree: SceneTree, args: Dictionary) -> Dictionary:
	var bad: Array = []
	for s in args.get("settings", []):
		var want = Apply.to_typed(str(s["type"]), s["value"])
		var key := str(s["key"])
		if not ProjectSettings.has_setting(key):
			bad.append({"key": key, "want": var_to_str(want), "got": "(unset)"})
		elif ProjectSettings.get_setting(key) != want:
			bad.append({"key": key, "want": var_to_str(want), "got": var_to_str(ProjectSettings.get_setting(key))})
	for a in args.get("actions", {}):
		if not ProjectSettings.has_setting("input/" + str(a)):
			bad.append({"key": "input/" + str(a), "want": "action", "got": "(unset)"})
	return {"ok": true, "data": {"mismatches": bad}}
