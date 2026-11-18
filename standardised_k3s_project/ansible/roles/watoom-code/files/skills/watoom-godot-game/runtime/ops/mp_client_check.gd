extends RefCounted
## T-0072, client half (see ops/mp_server_check.gd for the other side and what this pairs with). Builds the
## identical Dummy/Combat path locally (Godot's multiplayer RPCs route by matching NodePath across peers, no
## spawner needed for a two-node fixed-topology check like this), connects to the server, then:
## 1. calls CombatComponent.request_ability DIRECTLY (no rpc_id -- a local, non-networked call, the shape a
##    client-side cheat/bug would take) and confirms its own local health is untouched, since this client's
##    peer id is never the authority (1) regardless of whether the call reached the network at all.
## 2. calls it properly via rpc_id(1, ...), the real request that should reach and change the SERVER.
## args: {port, host, timeout_s}. data: {checks: [{name, ok, detail}]}.
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
	var err := peer.create_client(str(args.get("host", "127.0.0.1")), int(args.get("port", 29123)))
	if err != OK:
		return {"ok": false, "error": "create_client failed: %d" % err}
	tree.get_multiplayer().multiplayer_peer = peer

	var timeout_ms := int(float(args.get("timeout_s", 20.0)) * 1000.0)
	var start_ms := Time.get_ticks_msec()
	var connected := false
	while Time.get_ticks_msec() - start_ms < timeout_ms:
		await tree.process_frame
		if peer.get_connection_status() == MultiplayerPeer.CONNECTION_CONNECTED:
			connected = true
			break

	var checks: Array = [{"name": "client: connected to the server", "ok": connected, "detail": "status=%s" % peer.get_connection_status()}]

	if connected:
		# 1. the cheat/bug shape: call the RPC method directly, no network involved at all.
		combat.request_ability("cheat", {"kind": "damage", "amount": 999.0}, NodePath(""), 0.0, 0.0)
		checks.append({"name": "client: a direct local call with no authority leaves health untouched", "ok": combat.attrs.health == 100.0, "detail": "health=%s" % combat.attrs.health})

		# 2. the real request: an RPC to the server (peer id 1), which IS the authority on its own copy.
		combat.rpc_id(1, "request_ability", "sword", {"kind": "damage", "amount": 30.0}, NodePath(""), 1.0, 0.0)
		# give the server a short window to receive, apply and report it before this process exits -- the
		# server's own wait (independently timeout-bounded, see mp_server_check.gd) is what actually proves
		# the change happened; this is just "don't vanish mid-flight", not the assertion itself.
		var grace_start := Time.get_ticks_msec()
		while Time.get_ticks_msec() - grace_start < 3000:
			await tree.process_frame

	peer.close()
	var ok: bool = connected and combat.attrs.health == 100.0
	return {"ok": ok, "error": null if ok else "client-side checks failed", "data": {"checks": checks}}
