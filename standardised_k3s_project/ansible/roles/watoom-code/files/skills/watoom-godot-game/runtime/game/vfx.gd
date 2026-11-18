extends RefCounted
## T-0069: GPUParticles3D recipes from a small spec, the Godot equivalent of watoom-unreal-combat's Niagara
## generator (unreal_niagara_fx.py) -- same recipe names and the same per-damage-type colour table, built
## directly from Godot's own particle material instead of copying an engine template.
##
##   const VFX := preload("res://addons/gg/game/vfx.gd")
##   var particles := VFX.build({"recipe": "impact", "element": "Fire", "scale": 1.5})
##
## recipe: {"recipe": "projectile"|"impact"|"muzzle"|"aura", "element": one of ELEMENTS or an [r,g,b] array,
## "scale": float (size/speed multiplier, default 1.0), "radius": float (aura only, default 1.0)}.
## - projectile: a short, forward-streaming trail that loops for as long as it's attached (a thrown/fired
##   weapon effect that ends when the caller queue_frees it, not on a timer).
## - impact/muzzle: one-shot bursts (Loop Behavior equivalent: GPUParticles3D.one_shot = true), radial for
##   impact, a tight forward cone for muzzle.
## - aura: a slow, looping rise inside a sphere of the given radius (a buff/cast effect owned by something
##   that ends, same caveat as the Niagara version's aura recipe).
const ELEMENTS := {
	"Fire": [8.0, 2.0, 0.3], "Frost": [0.5, 2.0, 8.0], "Lightning": [3.0, 3.0, 10.0], "Poison": [1.0, 6.0, 0.5],
	"Arcane": [5.0, 0.8, 8.0], "Holy": [8.0, 7.0, 3.0], "Physical": [2.0, 2.0, 2.0], "Shadow": [0.6, 0.2, 1.2],
}


static func _colour(element, alpha: float = 1.0) -> Color:
	var rgb: Array
	if element is Array:
		rgb = element
	elif ELEMENTS.has(element):
		rgb = ELEMENTS[element]
	else:
		rgb = ELEMENTS["Physical"]
	# ELEMENTS is HDR (values above 1 bloom under a WorldEnvironment); normalised here since this draws with
	# an unshaded vertex-colour material with no bloom pass guaranteed -- divide by the brightest channel so
	# the colour's hue/ratio survives instead of just clamping to white.
	var peak: float = maxf(maxf(rgb[0], rgb[1]), maxf(rgb[2], 1.0))
	return Color(rgb[0] / peak, rgb[1] / peak, rgb[2] / peak, alpha)


static func build(recipe: Dictionary) -> GPUParticles3D:
	var kind: String = recipe.get("recipe", "impact")
	var scale: float = float(recipe.get("scale", 1.0))
	var radius: float = float(recipe.get("radius", 1.0))
	var col := _colour(recipe.get("element", "Physical"))

	var particles := GPUParticles3D.new()
	var mesh := QuadMesh.new()
	mesh.size = Vector2(0.25, 0.25) * scale
	var surf := StandardMaterial3D.new()
	surf.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	surf.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	surf.albedo_color = col
	surf.billboard_mode = BaseMaterial3D.BILLBOARD_ENABLED
	mesh.material = surf
	particles.draw_pass_1 = mesh

	var mat := ParticleProcessMaterial.new()
	particles.process_material = mat
	particles.local_coords = true

	match kind:
		"projectile":
			particles.one_shot = false
			particles.amount = 16
			particles.lifetime = 0.35
			mat.direction = Vector3(0, 0, 1)
			mat.spread = 6.0
			mat.initial_velocity_min = 0.3 * scale
			mat.initial_velocity_max = 0.8 * scale
			mat.gravity = Vector3.ZERO
		"muzzle":
			particles.one_shot = true
			particles.amount = 12
			particles.lifetime = 0.15
			particles.explosiveness = 1.0   # a burst spawns all at once; the default staggers spawns across the whole lifetime
			mat.direction = Vector3(0, 0, -1)
			mat.spread = 15.0
			mat.initial_velocity_min = 2.0 * scale
			mat.initial_velocity_max = 4.0 * scale
			mat.gravity = Vector3.ZERO
		"aura":
			particles.one_shot = false
			particles.amount = 30
			particles.lifetime = 1.5
			mat.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_SPHERE
			mat.emission_sphere_radius = radius
			mat.direction = Vector3(0, 1, 0)
			mat.spread = 20.0
			mat.initial_velocity_min = 0.1
			mat.initial_velocity_max = 0.3
			mat.gravity = Vector3.ZERO
		_:   # impact, and the fallback for an unrecognised recipe name
			particles.one_shot = true
			particles.amount = 40
			particles.lifetime = 0.5
			particles.explosiveness = 1.0
			mat.direction = Vector3(0, 1, 0)
			mat.spread = 180.0
			mat.initial_velocity_min = 1.0 * scale
			mat.initial_velocity_max = 3.0 * scale
			mat.gravity = Vector3(0, -9.8, 0)
	return particles
