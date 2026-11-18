extends Area3D
## T-0071: a pickup that grants an ability or applies an effect to whatever CombatComponent child walks into
## it, using the existing Combat.apply_effect plumbing (same effect dict shape as CombatComponent.try_ability,
## e.g. {"kind": "grant", "resource": "ammo", "amount": 30} for ammo, {"kind": "grant", "resource": "mana",
## "amount": 50} for a mana potion, {"kind": "heal", "amount": 25} for a health pickup, or {"kind": "damage",
## ...} for a hazard). Minimal inventory scope (T-0063-equivalent): weapon pickups use the same effect shape
## with a caller-side "equip" step this op does not own.
## respawn_s <= 0: one-shot, the node frees itself once collected. respawn_s > 0: hides/disables monitoring,
## then reappears after respawn_s seconds (a real SceneTreeTimer, not a physics tick count, since a pickup's
## respawn is gameplay-paced, not physics-paced).
const Combat := preload("res://addons/gg/game/combat.gd")

@export var effect: Dictionary = {}
@export var respawn_s: float = 0.0

signal collected(body: Node, result: Dictionary)


func _ready() -> void:
	body_entered.connect(_on_body_entered)


func _on_body_entered(body: Node) -> void:
	if not monitoring:
		return
	var combat: Node = body.get_node_or_null("Combat")
	if combat == null:
		return
	var result: Dictionary = Combat.apply_effect(combat.attrs, effect)
	if result.get("ok", true) == false:
		return
	collected.emit(body, result)
	_consume()


func _consume() -> void:
	set_deferred("monitoring", false)
	visible = false
	if respawn_s <= 0.0:
		queue_free()
	else:
		get_tree().create_timer(respawn_s).timeout.connect(_respawn)


func _respawn() -> void:
	monitoring = true
	visible = true
