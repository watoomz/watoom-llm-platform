extends RefCounted
## T-0072, server half: a real ENetMultiplayerPeer server (a second, concurrently-running godot process is
## the client -- see ops/mp_client_check.gd and gg_combat.py's `mp` subcommand, which launches both and
## combines their checks). Builds a Dummy/Combat node at a fixed path (the client builds the identical path
## so Godot's by-path RPC routing finds it), waits for the client to connect, then waits for its OWN health
## to actually change -- proof that the client's authoritative-RPC request (not a local call) is what moved
## state, since this process never calls try_ability/request_ability itself.
## args: {port, timeout_s}. data: {checks: [{name, ok, detail}]}.
const CombatComponent := preload("res://addons/gg/game/combat_component.gd")


func run(tree: SceneTree, args: Dictionary) -> Dictionary:
	var dummy := CharacterBody3D.new()
	dummy.name = "Dummy"
	var combat := CombatComponent.new()
	combat.name = "Combat"
	combat.attrs.max_health = 100.0
	combat.attrs.health = 100.0
	dummy.add_child(combat)
	tree.root.add_child(dummy)
	combat.set_multiplayer_authority(1)

	var peer := ENetMultiplayerPeer.new()
	var err := peer.create_server(int(args.get("port", 29123)), 2)
	if err != OK:
		return {"ok": false, "error": "create_server failed: %d" % err}
	tree.get_multiplayer().multiplayer_peer = peer

	var timeout_ms := int(float(args.get("timeout_s", 20.0)) * 1000.0)
	var start_ms := Time.get_ticks_msec()
	var connected := false
	while Time.get_ticks_msec() - start_ms < timeout_ms:
		await tree.process_frame
		if tree.get_multiplayer().get_peers().size() > 0:
			connected = true
			break

	var changed := false
	if connected:
		while Time.get_ticks_msec() - start_ms < timeout_ms:
			await tree.process_frame
			if combat.attrs.health != 100.0:
				changed = true
				break

	var checks: Array = [
		{"name": "server: a client peer connected", "ok": connected, "detail": "peers=%s" % [tree.get_multiplayer().get_peers()]},
		{"name": "server: the authoritative RPC actually changed this process's own health", "ok": changed, "detail": "health=%s" % combat.attrs.health},
	]
	peer.close()
	var ok := connected and changed
	return {"ok": ok, "error": null if ok else "server-side checks failed", "data": {"checks": checks}}
