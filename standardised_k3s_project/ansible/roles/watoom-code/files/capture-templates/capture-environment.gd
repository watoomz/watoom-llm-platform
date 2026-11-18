extends RefCounted
## Lit outdoor capture environment for validation renders.
##
## Attaches a WorldEnvironment (procedural-sky background + sky ambient + soft
## fog) plus a key/fill directional-light rig to `parent`, so ground and asset
## captures are never rendered against the flat default-grey void with a hard
## horizon line that pixel reviews (correctly) reject as "featureless background".
##
## Copy to the project and call once from the capture scene's _ready(), before
## adding cameras and after adding the subject:
##
##     const CaptureEnvironment := preload("res://<path>/capture-environment.gd")
##     CaptureEnvironment.attach(self)
##
## It does NOT add cameras or the subject; the scene still owns framing. Lights
## are plain key/fill defaults — override in the scene if the asset needs a
## specific look. Reuse this instead of hand-writing a bare plane + single light.
##
## fog_density: the 0.008 default suits close asset/ground shots (tens of
## metres). For landscape / real-terrain views spanning hundreds of metres pass
## LANDSCAPE_FOG_DENSITY (or 0.0) — 0.008 over 300 m hides ~93% of the scene.
## Never add height fog (fog_height_density) for captures: it buries everything
## below fog_height in one flat colour.
const LANDSCAPE_FOG_DENSITY := 0.0004

static func attach(parent: Node, fog_density: float = 0.008) -> void:
	var sky_material := ProceduralSkyMaterial.new()
	sky_material.sky_top_color = Color(0.36, 0.45, 0.58)
	sky_material.sky_horizon_color = Color(0.70, 0.72, 0.70)
	sky_material.ground_horizon_color = Color(0.64, 0.60, 0.52)
	sky_material.ground_bottom_color = Color(0.32, 0.27, 0.20)
	sky_material.ground_curve = 0.1

	var sky := Sky.new()
	sky.sky_material = sky_material

	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = 1.0
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	# Soft atmospheric fade so the ground-plane edge reads as distance haze
	# rather than a hard horizon line.
	env.fog_enabled = fog_density > 0.0
	env.fog_light_color = Color(0.70, 0.72, 0.70)
	env.fog_density = fog_density

	var world_env := WorldEnvironment.new()
	world_env.environment = env
	parent.add_child(world_env)

	# Key light (warm sun) with shadows for surface relief.
	var key := DirectionalLight3D.new()
	key.rotation_degrees = Vector3(-50, -35, 0)
	key.light_energy = 1.1
	key.light_color = Color(1.0, 0.96, 0.88)
	key.shadow_enabled = true
	parent.add_child(key)

	# Cool fill from the opposite side so shadowed areas keep readable detail.
	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-25, 140, 0)
	fill.light_energy = 0.35
	fill.light_color = Color(0.80, 0.86, 1.0)
	parent.add_child(fill)
