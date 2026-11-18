extends SceneTree
## watoom-godot-game runner. Launched by scripts/gg_godot.py:
##   godot --path P -s res://addons/gg/gg_runner.gd -- --spec=/abs/spec.json --result=/abs/result.json
## Reads the spec, runs res://addons/gg/ops/<op>.gd (its run(tree, args) -> Dictionary, may await),
## writes the result atomically, prints @@GG_DONE@@ as the LAST line, then quits.
## If this script never prints @@GG_DONE@@ the run FAILED (parse error, runtime error in a coroutine, hang).

func _initialize() -> void:
	_main.call_deferred()

func _arg(name: String) -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--%s=" % name):
			return a.substr(name.length() + 3)
	return ""

func _write(path: String, data: Dictionary) -> void:
	var tmp := path + ".tmp"
	var f := FileAccess.open(tmp, FileAccess.WRITE)
	if f == null:
		printerr("GG cannot write result: ", tmp)
		return
	f.store_string(JSON.stringify(data, "  "))
	f.close()
	DirAccess.rename_absolute(tmp, path)

func _main() -> void:
	var spec_path := _arg("spec")
	var result_path := _arg("result")
	var spec = {}
	var f := FileAccess.open(spec_path, FileAccess.READ)
	if f != null:
		spec = JSON.parse_string(f.get_as_text())
	var op := str(spec.get("op", "")) if spec is Dictionary else ""
	var res := {"schema": 1, "op": op, "job": spec.get("job", "") if spec is Dictionary else "",
		"ok": false, "error": null, "data": {}, "warnings": [], "frames": 0}
	var rm := ""
	var drv := ""
	if RenderingServer.has_method("get_current_rendering_method"):
		rm = str(RenderingServer.call("get_current_rendering_method"))
	if RenderingServer.has_method("get_current_rendering_driver_name"):
		drv = str(RenderingServer.call("get_current_rendering_driver_name"))
	res["engine"] = {"version": Engine.get_version_info().get("string", ""), "rendering_method": rm,
		"driver": drv, "adapter": RenderingServer.get_video_adapter_name()}
	print("@@GG_BEGIN@@ ", op)
	if not (spec is Dictionary) or op == "":
		res["error"] = "bad or missing spec: %s" % spec_path
	else:
		var script = load("res://addons/gg/ops/%s.gd" % op)
		if script == null:
			res["error"] = "unknown op '%s' (no res://addons/gg/ops/%s.gd)" % [op, op]
		else:
			var inst = script.new()
			var out = await inst.run(self, spec.get("args", {}))
			if out is Dictionary:
				res["ok"] = bool(out.get("ok", false))
				res["error"] = out.get("error", null)
				res["data"] = out.get("data", {})
				res["warnings"] = out.get("warnings", [])
			else:
				res["error"] = "op returned no dictionary"
	_write(result_path, res)
	print("@@GG_DONE@@ ok=", res["ok"])
	quit(0 if res["ok"] else 1)
