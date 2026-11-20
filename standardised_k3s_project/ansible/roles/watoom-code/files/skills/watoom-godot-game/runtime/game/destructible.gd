extends StaticBody3D
## A breakable prop made from a PRE-FRACTURED model (blender-simulation/scripts/fracture.py: one "Intact" mesh plus
## "Piece_000".. meshes, each piece's origin at its own centre, placed where it sits in the intact mesh).
## T-0066. Godot 4 has no runtime fracture, so the pieces are made offline and this node swaps them in.
##
## It is a StaticBody3D with a child "Combat" (CombatComponent) exactly like a fighter, so every existing weapon
## (gg_combat: a raycast hit -> collider.get_node("Combat") -> try_ability) damages it with no new code. While whole
## it collides with the Intact mesh's convex hull. When its health reaches 0 it breaks: the Intact mesh is hidden,
## its collider disabled, and every piece becomes a RigidBody3D (convex hull of the piece, mass from its volume)
## at the piece's exact transform -- no jump -- pushed away from the last hit.
##
##   var wall := Destructible.new(); wall.model = preload("res://assets/destruction/box_wall.glb"); wall.max_health = 100.0
##   add_child(wall)          # builds the collider and the Combat child in _ready
##   wall.hit_at(point, dir)  # optional: where the shot landed, so the break pushes pieces from there
##
## signal broken(pieces: Array[RigidBody3D])
const CombatComponent := preload("res://addons/gg/game/combat_component.gd")

signal broken(pieces: Array)

@export var model: PackedScene
@export var max_health: float = 100.0
@export var density: float = 2000.0          ## kg/m^3 (masonry ~2000); piece mass = density * hull AABB volume * 0.5
@export var break_impulse: float = 6.0       ## m/s given to a piece at the hit, falling off to 0 at impulse_radius
@export var impulse_radius: float = 1.5      ## m around the hit that the push reaches
@export var debris_lifetime_s: float = 0.0   ## 0 = pieces stay; else they are freed after this many seconds
@export var hull_shrink: float = 0.9         ## piece colliders are scaled this much toward the piece centre (see _hull)

var combat: Node
var intact: MeshInstance3D
var pieces_src: Array = []                   ## the Piece_* MeshInstance3D templates (hidden until the break)
var pieces: Array = []                       ## the RigidBody3D pieces after the break
var is_broken := false
var _shape: CollisionShape3D
var _hit_point = null
var _hit_dir := Vector3.ZERO


func _ready() -> void:
	if model != null:
		var inst := model.instantiate()
		inst.name = "Model"
		add_child(inst)
	_collect(self)
	if intact == null or pieces_src.size() < 2:
		push_error("Destructible %s: model needs an 'Intact' mesh and at least two 'Piece_*' meshes (fracture.py makes both)" % name)
		return
	for p in pieces_src:
		p.visible = false
	_shape = CollisionShape3D.new()
	_shape.name = "IntactShape"
	_shape.shape = intact.mesh.create_convex_shape()
	add_child(_shape)
	_shape.global_transform = intact.global_transform
	combat = CombatComponent.new()
	combat.name = "Combat"
	combat.attrs.team = -1
	combat.attrs.max_health = max_health
	combat.attrs.health = max_health
	add_child(combat)


func _collect(n: Node) -> void:
	for c in n.get_children():
		if c is MeshInstance3D:
			if c.name == "Intact" or String(c.name).begins_with("Intact"):
				intact = c
			elif String(c.name).begins_with("Piece_"):
				pieces_src.append(c)
		_collect(c)


## Tell the prop where the last shot landed (world space) and its direction, so the break pushes from there.
func hit_at(point: Vector3, dir: Vector3) -> void:
	_hit_point = point
	_hit_dir = dir.normalized()


func _physics_process(_dt: float) -> void:
	if not is_broken and combat != null and combat.attrs.dead:
		shatter()


func shatter() -> Array:
	if is_broken or intact == null:
		return pieces
	is_broken = true
	intact.visible = false
	# off NOW, not deferred: deferred, the intact hull still exists in the break frame with every piece inside it,
	# and depenetration flings them (measured T-0066: 34 m in one frame). shatter() runs from _physics_process.
	_shape.disabled = true
	var parent := get_parent()
	var centre: Vector3 = intact.global_transform * intact.get_aabb().get_center()
	var from: Vector3 = _hit_point if _hit_point != null else centre
	for src in pieces_src:
		var body := RigidBody3D.new()
		body.name = "Debris_" + String(src.name).trim_prefix("Piece_")
		var xf: Transform3D = src.global_transform
		var mesh := MeshInstance3D.new()
		mesh.mesh = src.mesh
		body.add_child(mesh)
		var col := CollisionShape3D.new()
		col.shape = _hull(src.mesh)
		body.add_child(col)
		var size: Vector3 = src.get_aabb().size
		body.mass = max(0.05, density * size.x * size.y * size.z * 0.5)
		body.add_collision_exception_with(self)
		parent.add_child(body)
		body.global_transform = xf
		var away: Vector3 = xf.origin - from
		var d := away.length()
		if d < impulse_radius:
			var push := (_hit_dir if _hit_dir != Vector3.ZERO else Vector3.ZERO) + away.normalized() * 0.5
			# a velocity, not apply_central_impulse(v * mass): an impulse on a body added this frame acted on the default
			# 1 kg, not the mass just set (measured T-0066: a 486 kg piece left at ~2000 m/s instead of 4.5 m/s)
			body.linear_velocity = push.normalized() * break_impulse * (1.0 - d / impulse_radius)
		if debris_lifetime_s > 0.0:
			get_tree().create_timer(debris_lifetime_s).timeout.connect(body.queue_free)
		pieces.append(body)
	broken.emit(pieces)
	return pieces


## Collision hull of one piece, shrunk toward the piece's own origin (its centre). Neighbouring Voronoi pieces share
## faces exactly and the bottom row touches the ground, so full-size hulls start out in contact and keep nudging each
## other (measured T-0066 on the 24-piece test wall: 22 of 24 at rest after 4 s at 1.0, 24 of 24 at 0.9).
func _hull(mesh: Mesh) -> ConvexPolygonShape3D:
	var src := mesh.create_convex_shape() as ConvexPolygonShape3D
	var pts := PackedVector3Array()
	for v in src.points:
		pts.append(v * hull_shrink)
	var shape := ConvexPolygonShape3D.new()
	shape.points = pts
	return shape
