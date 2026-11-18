extends RefCounted
func run(_tree: SceneTree, args: Dictionary) -> Dictionary:
	return {"ok": true, "data": {"echo": args}}
