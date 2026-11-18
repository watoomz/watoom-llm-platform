extends RefCounted
## Stateless combat math + a tiny effect dispatcher, in the same style as lib/style.gd. Operates on a
## game/combat_attributes.gd resource. This is the first slice of T-0065 (Godot combat pipeline, the
## equivalent of the Unreal/GAS epic T-0063): generic attribute/damage/effect math only. Weapon/spell/item
## specs, animation, VFX, items and multiplayer replication are NOT built yet -- see references/gg-combat.md.
##
##   const Combat := preload("res://addons/gg/game/combat.gd")
##   Combat.deal_damage(attrs, 30.0, "fire", 1.5)

## base * multiplier (e.g. a headshot/zone bonus) * (1 - resist), floored at 0. multiplier/resist outside
## their sane ranges are clamped rather than trusted: a spec typo should never produce negative damage/healing.
static func calc_damage(base: float, multiplier: float = 1.0, resist: float = 0.0) -> float:
	var mult := maxf(multiplier, 0.0)
	var res := clampf(resist, 0.0, 1.0)
	return maxf(base, 0.0) * mult * (1.0 - res)

## Looks up attrs.resist[damage_type] (0 if absent or damage_type == ""), rolls calc_damage, applies it.
## Returns CombatAttributes.apply_damage's dict plus "amount" (the resist-adjusted damage actually rolled).
static func deal_damage(attrs, base: float, damage_type: String = "", multiplier: float = 1.0) -> Dictionary:
	var res: float = attrs.resist.get(damage_type, 0.0) if damage_type != "" else 0.0
	var amount := calc_damage(base, multiplier, res)
	var result: Dictionary = attrs.apply_damage(amount)
	result["amount"] = amount
	return result

## Same team id is friendly. Team -1 means "no team" (always hostile: a neutral hazard or a target dummy).
static func is_friendly(team_a: int, team_b: int) -> bool:
	return team_a == team_b and team_a != -1

## False exactly when attacker/target are friendly and allow_friendly_fire is false (T-0063's no-friendly-fire default).
static func can_damage(attacker_team: int, target_team: int, allow_friendly_fire: bool = false) -> bool:
	return allow_friendly_fire or not is_friendly(attacker_team, target_team)

## now/last_used/cooldown_s share one time unit (seconds). last_used < 0 means "never used yet" (always ready).
static func cooldown_ready(last_used: float, now: float, cooldown_s: float) -> bool:
	return last_used < 0.0 or now - last_used >= maxf(cooldown_s, 0.0)

## effect: {"kind": "damage"|"heal"|"cost"|"grant", ...}. The four generic Gameplay-Effect kinds T-0063's plan
## uses (GE_Damage/GE_Heal/GE_Cost/GE_Cooldown) map to the first three; "grant" (a pickup/regen tick adding a
## resource back, clamped at max via the attrs setter) is cost's mirror image, same resource names. Cooldown
## gating itself is the caller's job via cooldown_ready() since it needs per-ability state this function is
## not given. Unknown kind -> {"ok": false, "reason": ...}.
static func apply_effect(attrs, effect: Dictionary) -> Dictionary:
	var kind: String = effect.get("kind", "")
	if kind == "damage":
		return deal_damage(attrs, float(effect.get("amount", 0.0)), str(effect.get("damage_type", "")), float(effect.get("multiplier", 1.0)))
	if kind == "heal":
		return {"ok": true, "healed": attrs.apply_heal(float(effect.get("amount", 0.0)))}
	if kind == "cost":
		return _apply_cost(attrs, str(effect.get("resource", "stamina")), float(effect.get("amount", 0.0)))
	if kind == "grant":
		return _apply_grant(attrs, str(effect.get("resource", "stamina")), float(effect.get("amount", 0.0)))
	return {"ok": false, "reason": "unknown effect kind '%s'" % kind}

static func _apply_cost(attrs, resource: String, amount: float) -> Dictionary:
	if resource == "stamina":
		if attrs.stamina < amount:
			return {"ok": false, "reason": "insufficient stamina"}
		attrs.stamina -= amount
		return {"ok": true}
	if resource == "mana":
		if attrs.mana < amount:
			return {"ok": false, "reason": "insufficient mana"}
		attrs.mana -= amount
		return {"ok": true}
	if resource == "ammo":
		if attrs.ammo < int(amount):
			return {"ok": false, "reason": "insufficient ammo"}
		attrs.ammo -= int(amount)
		return {"ok": true}
	return {"ok": false, "reason": "unknown resource '%s'" % resource}

## Mirror of _apply_cost: adds amount to the named resource, clamped at its max by the attrs setter. Returns
## the actual amount gained (may be less than requested if already near max), so a pickup can report "topped
## off" vs "fully refilled".
static func _apply_grant(attrs, resource: String, amount: float) -> Dictionary:
	if resource == "stamina":
		var before: float = attrs.stamina
		attrs.stamina = before + amount
		return {"ok": true, "granted": attrs.stamina - before}
	if resource == "mana":
		var before: float = attrs.mana
		attrs.mana = before + amount
		return {"ok": true, "granted": attrs.mana - before}
	if resource == "ammo":
		var before: int = attrs.ammo
		attrs.ammo = before + int(amount)
		return {"ok": true, "granted": attrs.ammo - before}
	return {"ok": false, "reason": "unknown resource '%s'" % resource}
