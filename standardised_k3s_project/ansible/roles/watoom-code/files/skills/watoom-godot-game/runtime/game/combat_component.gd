extends Node
## Per-actor combat component: owns one CombatAttributes resource and gates ability use by a per-ability
## cooldown. Attach to any Node that fights (CharacterBody3D for a real actor, or a plain Node for tests).
## Pure game logic only -- no animation, VFX, hit detection or networking here yet (see game/combat.gd and
## references/gg-combat.md). Networking note: call try_ability only where authority has already been
## checked (the server in a replicated game); this component does not check multiplayer authority itself.
##
##   var a := CombatComponent.new(); a.attrs.team = 0
##   var b := CombatComponent.new(); b.attrs.team = 1; b.attrs.max_health = 100.0; b.attrs.health = 100.0
##   a.try_ability("sword_swing", {"kind": "damage", "amount": 20.0}, b, 1.0, now)

const Combat := preload("res://addons/gg/game/combat.gd")
const CombatAttributes := preload("res://addons/gg/game/combat_attributes.gd")

var attrs: CombatAttributes = CombatAttributes.new()
var _last_used: Dictionary = {}   # ability_id (String) -> last-used time in seconds


## target: another CombatComponent (or this one, for a self-effect like a heal or a mana cost); null
## defaults to self. allow_friendly_fire only matters for a "damage" effect against a different target.
## now must be the same clock/unit the caller uses everywhere (e.g. Time.get_ticks_msec() / 1000.0).
func try_ability(ability_id: String, effect: Dictionary, target: Node = null, cooldown_s: float = 0.0, now: float = 0.0, allow_friendly_fire: bool = false) -> Dictionary:
	var last: float = _last_used.get(ability_id, -1.0)
	if not Combat.cooldown_ready(last, now, cooldown_s):
		return {"ok": false, "reason": "on cooldown", "remaining": cooldown_s - (now - last)}
	var dest: Node = target if target != null else self
	if effect.get("kind", "") == "damage" and dest != self and not Combat.can_damage(attrs.team, dest.attrs.team, allow_friendly_fire):
		return {"ok": false, "reason": "blocked by friendly fire rule"}
	var result: Dictionary = Combat.apply_effect(dest.attrs, effect)
	if result.get("ok", true) != false:
		_last_used[ability_id] = now
	return result


## T-0072: the thin network-authority wrapper try_ability's own docstring calls for. A client calls this via
## rpc_id(1, ...) to request an ability on the server; is_multiplayer_authority() is only true for the peer
## this node's authority is set to (the server, by Godot's "unset = 1" convention), so a client that instead
## calls this directly (no RPC, bypassing the network) or any peer that isn't the authority gets silently
## ignored -- the same no-authority-no-effect rule applies whether the call arrived over the wire or not.
## target_path resolves relative to this node (NodePath("") means self, matching try_ability's own default).
@rpc("any_peer", "call_local", "reliable")
func request_ability(ability_id: String, effect: Dictionary, target_path: NodePath, cooldown_s: float = 0.0, now: float = 0.0, allow_friendly_fire: bool = false) -> void:
	if not is_multiplayer_authority():
		return
	var target: Node = get_node_or_null(target_path) if target_path != NodePath("") else null
	try_ability(ability_id, effect, target, cooldown_s, now, allow_friendly_fire)
