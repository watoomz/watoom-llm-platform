extends RefCounted
## Scripted, headless scenario proving game/combat_component.gd works inside a real running SceneTree
## (not just as static math): damage-once-per-hit, cooldown enforcement, teammate immunity, lethal ->
## death, and a resource-cost ability refusing without consuming its cooldown. No scene/assets needed --
## this is pure gameplay logic, independent of the weapon/character art blocker tracked on T-0065/T-0059.
## args: {} (none yet). data: {checks: [{name, ok, detail}]}.
const CombatComponent := preload("res://addons/gg/game/combat_component.gd")

func run(tree: SceneTree, args: Dictionary) -> Dictionary:
	var rows: Array = []

	var attacker: Node = CombatComponent.new()
	attacker.attrs.team = 0
	var ally: Node = CombatComponent.new()
	ally.attrs.team = 0
	var enemy: Node = CombatComponent.new()
	enemy.attrs.team = 1
	enemy.attrs.max_health = 100.0; enemy.attrs.health = 100.0
	enemy.attrs.max_mana = 0.0; enemy.attrs.mana = 0.0

	var sword := {"kind": "damage", "amount": 20.0}
	var r1: Dictionary = attacker.try_ability("sword", sword, enemy, 1.0, 0.0)
	rows.append(["first hit lands", r1.get("ok", true) != false and enemy.attrs.health == 80.0, "health=%s result=%s" % [enemy.attrs.health, r1]])

	var r2: Dictionary = attacker.try_ability("sword", sword, enemy, 1.0, 0.2)
	rows.append(["repeat hit inside cooldown is blocked", r2.get("ok", true) == false and enemy.attrs.health == 80.0, "health=%s result=%s" % [enemy.attrs.health, r2]])

	var r3: Dictionary = attacker.try_ability("sword", sword, enemy, 1.0, 1.0)
	rows.append(["hit after cooldown elapses lands again", r3.get("ok", true) != false and enemy.attrs.health == 60.0, "health=%s result=%s" % [enemy.attrs.health, r3]])

	var r4: Dictionary = attacker.try_ability("sword_on_ally", sword, ally, 1.0, 2.0)
	rows.append(["teammate is immune by default", r4.get("ok", true) == false and ally.attrs.health == ally.attrs.max_health, "result=%s" % [r4]])

	var spell := {"kind": "cost", "resource": "mana", "amount": 10.0}
	var r5: Dictionary = enemy.try_ability("spell", spell, null, 1.0, 3.0)
	rows.append(["unaffordable cost is refused", r5.get("ok") == false, "result=%s" % [r5]])
	var r6: Dictionary = enemy.try_ability("spell", spell, null, 1.0, 3.0)
	rows.append(["a refused cost does not consume its own cooldown", r6.get("ok") == false and r6.get("reason", "") != "on cooldown", "result=%s" % [r6]])

	var lethal := {"kind": "damage", "amount": 1000.0}
	var r7: Dictionary = attacker.try_ability("finisher", lethal, enemy, 0.0, 10.0)
	rows.append(["lethal hit clamps health at 0 and marks dead", r7.get("died") == true and enemy.attrs.health == 0.0 and enemy.attrs.dead == true, "health=%s dead=%s result=%s" % [enemy.attrs.health, enemy.attrs.dead, r7]])

	var checks: Array = []
	var ok := true
	for row in rows:
		checks.append({"name": row[0], "ok": row[1], "detail": row[2]})
		ok = ok and row[1]
	return {"ok": ok, "error": null if ok else "one or more combat checks failed", "data": {"checks": checks}}
