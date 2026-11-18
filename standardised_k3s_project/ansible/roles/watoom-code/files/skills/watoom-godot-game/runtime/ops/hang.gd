extends RefCounted
## Selftest op: never finishes. Proves the launcher's timeout produces exit 4.
func run(tree: SceneTree, _args: Dictionary) -> Dictionary:
	while true:
		await tree.process_frame
	return {"ok": true}
