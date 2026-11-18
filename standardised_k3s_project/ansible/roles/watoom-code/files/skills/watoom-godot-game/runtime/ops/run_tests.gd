extends RefCounted
## Run every test_*.gd under a folder. Each test_* method is one test; see lib/gg_test.gd.
## args: {dir: "res://tests", filter: ""}   data: {files, tests, passed, failed, checks, results: [{file, name, ok, failures}]}
func run(tree: SceneTree, args: Dictionary) -> Dictionary:
	var dir_path := str(args.get("dir", "res://tests"))
	var filter := str(args.get("filter", ""))
	var da := DirAccess.open(dir_path)
	if da == null:
		return {"ok": false, "error": "cannot open %s" % dir_path}
	var names: Array = []
	for f in da.get_files():
		if f.begins_with("test_") and f.ends_with(".gd"):
			names.append(f)
	names.sort()
	var results: Array = []
	var passed := 0
	var failed := 0
	var checks := 0
	var files := 0
	for fname in names:
		var script = load("%s/%s" % [dir_path, fname])
		if script == null:
			results.append({"file": fname, "name": "(load)", "ok": false, "failures": ["script did not load: parse error, see the engine log"]})
			failed += 1
			continue
		files += 1
		var inst = script.new()
		if not ("_failures" in inst):
			results.append({"file": fname, "name": "(base)", "ok": false, "failures": ["must extend res://addons/gg/lib/gg_test.gd"]})
			failed += 1
			continue
		var methods: Array = []
		for m in script.get_script_method_list():
			if str(m["name"]).begins_with("test_") and (filter == "" or filter in str(m["name"])):
				methods.append(str(m["name"]))
		methods.sort()
		for mname in methods:
			inst._failures = []
			inst._checks = 0
			if inst.has_method("before_each"):
				await inst.before_each()
			await inst.call(mname)
			if inst._checks == 0:
				inst._failures.append("the test made no assertions")
			checks += int(inst._checks)
			var good: bool = inst._failures.is_empty()
			if good:
				passed += 1
			else:
				failed += 1
			results.append({"file": fname, "name": mname, "ok": good, "failures": inst._failures.slice(0, 8)})
	return {"ok": failed == 0, "error": null if failed == 0 else "%d of %d tests failed" % [failed, passed + failed],
		"data": {"files": files, "tests": passed + failed, "passed": passed, "failed": failed, "checks": checks, "results": results}}
