extends Resource
## Server-authoritative combat stats for one actor: health/shield/stamina/mana/ammo with clamping, a
## team id, and per-damage-type resist fractions. Pure data + simple mutators; no networking or
## animation here (see game/combat.gd for the damage math this feeds, and references/gg-combat.md
## for how this is meant to sit behind replicated RPCs once that exists).
##
##   var attrs := CombatAttributes.new()
##   attrs.max_health = 100.0; attrs.health = 100.0
##   var dealt := attrs.apply_damage(30.0)   # shield absorbs first, then health

@export var team: int = 0

@export var health: float = 100.0: set = _set_health
@export var max_health: float = 100.0

@export var shield: float = 0.0: set = _set_shield
@export var max_shield: float = 0.0

@export var stamina: float = 100.0: set = _set_stamina
@export var max_stamina: float = 100.0

@export var mana: float = 100.0: set = _set_mana
@export var max_mana: float = 100.0

@export var ammo: int = 0: set = _set_ammo
@export var max_ammo: int = 0

## resist[damage_type] = 0..1 fraction of that damage type absorbed before shield/health; a missing key means 0 resist.
@export var resist: Dictionary = {}

var dead: bool = false

func _set_health(v: float) -> void:
	health = clampf(v, 0.0, max(max_health, 0.0))
	if health <= 0.0:
		dead = true

func _set_shield(v: float) -> void:
	shield = clampf(v, 0.0, max(max_shield, 0.0))

func _set_stamina(v: float) -> void:
	stamina = clampf(v, 0.0, max(max_stamina, 0.0))

func _set_mana(v: float) -> void:
	mana = clampf(v, 0.0, max(max_mana, 0.0))

func _set_ammo(v: int) -> void:
	ammo = clampi(v, 0, max(max_ammo, 0))

## incoming is already resist-adjusted (Combat.calc_damage / Combat.deal_damage does that). Shield absorbs
## first, overflow hits health. Returns {shield_lost, health_lost, died} -- died is true only on the tick health reaches 0.
func apply_damage(incoming: float) -> Dictionary:
	var amount := maxf(incoming, 0.0)
	var shield_lost := minf(amount, shield)
	self.shield = shield - shield_lost
	var remaining := amount - shield_lost
	var health_lost := minf(remaining, health)
	var was_alive := not dead
	self.health = health - health_lost
	return {"shield_lost": shield_lost, "health_lost": health_lost, "died": was_alive and dead}

func apply_heal(amount: float) -> float:
	var before := health
	self.health = health + maxf(amount, 0.0)
	return health - before

func revive(start_health: float = -1.0) -> void:
	dead = false
	self.health = start_health if start_health >= 0.0 else max_health
