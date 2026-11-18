extends RefCounted
## Turns a resolved style dictionary (presets/*.json after merge) into Godot objects. Stateless, static.
## Colours in the preset are sRGB 0..1 triples; Godot treats Color(r,g,b) as sRGB-authored, so they pass through.

const TONEMAP := {"linear": 0, "reinhard": 1, "filmic": 2, "aces": 3, "agx": 4}
const SHADERS := "res://addons/gg/shaders/"

static func col(a: Array, alpha := 1.0) -> Color:
	return Color(float(a[0]), float(a[1]), float(a[2]), alpha)

static func hexcol(h: String) -> Color:
	return Color.html("#" + h.trim_prefix("#"))

static func sun(style: Dictionary) -> DirectionalLight3D:
	var L: Dictionary = style["lighting"]
	var s := DirectionalLight3D.new()
	s.name = "Sun"
	s.light_energy = float(L["sun_energy"])
	s.light_color = col(L["sun_color"])
	s.rotation_degrees = Vector3(-float(L["sun_elevation_deg"]), float(L["sun_azimuth_deg"]), 0.0)
	s.shadow_enabled = bool(L["shadows"])
	s.shadow_blur = float(L.get("shadow_blur", 1.0))
	return s

static func environment(style: Dictionary) -> Environment:
	var L: Dictionary = style["lighting"]
	var P: Dictionary = style["post"]
	var e := Environment.new()
	var sky: Dictionary = L["sky"]
	if sky["kind"] == "color":
		e.background_mode = Environment.BG_COLOR
		e.background_color = col(sky["color"])
	else:
		var m := ProceduralSkyMaterial.new()
		m.sky_top_color = col(sky["top"])
		m.sky_horizon_color = col(sky["horizon"])
		m.ground_horizon_color = col(sky["horizon"])
		m.ground_bottom_color = col(sky["top"]).darkened(0.4)
		var s := Sky.new()
		s.sky_material = m
		e.sky = s
		e.background_mode = Environment.BG_SKY
	if L["ambient_source"] == "sky" and e.sky != null:
		e.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	else:
		e.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
		e.ambient_light_color = col(L["ambient_color"])
	e.ambient_light_energy = float(L["ambient_energy"])
	e.tonemap_mode = int(TONEMAP.get(P["tonemap"], 0))
	e.tonemap_exposure = float(P["exposure"])
	e.tonemap_white = float(P["white"])
	e.glow_enabled = bool(P["glow"]["on"])
	if e.glow_enabled:
		e.glow_intensity = float(P["glow"]["intensity"])
		e.glow_hdr_threshold = float(P["glow"]["threshold"])
	e.fog_enabled = bool(P["fog"]["on"])
	if e.fog_enabled:
		e.fog_density = float(P["fog"]["density"])
		e.fog_aerial_perspective = float(P["fog"]["aerial"])
		e.fog_light_color = col(sky["horizon"]) if sky["kind"] != "color" else col(sky["color"])
	var A: Dictionary = P["adjust"]
	e.adjustment_enabled = true
	e.adjustment_brightness = float(A["brightness"])
	e.adjustment_contrast = float(A["contrast"])
	e.adjustment_saturation = float(A["saturation"])
	if RenderingServer.has_method("get_current_rendering_method") and str(RenderingServer.call("get_current_rendering_method")) == "forward_plus":
		e.ssao_enabled = bool(P["ssao"])
		e.ssil_enabled = bool(P["ssil"])
		e.sdfgi_enabled = bool(P["sdfgi"])
	return e

## One surface material for the style. kind: "solid" (opaque colour), "water", "emissive".
static func material(style: Dictionary, color: Color, kind := "solid") -> Material:
	var M: Dictionary = style["material"]
	var mat: Material
	match M["shading"]:
		"toon":
			var sm := ShaderMaterial.new()
			sm.shader = load(SHADERS + "toon.gdshader")
			sm.set_shader_parameter("albedo", color)
			sm.set_shader_parameter("softness", float(M.get("toon_softness", 0.15)))
			if M["outline"]["on"]:
				var om := ShaderMaterial.new()
				om.shader = load(SHADERS + "outline.gdshader")
				om.set_shader_parameter("outline_color", hexcol(M["outline"]["color"]))
				om.set_shader_parameter("thickness", float(M["outline"]["px"]) * 0.02)
				sm.next_pass = om
			mat = sm
		"flat":
			var fm := ShaderMaterial.new()
			fm.shader = load(SHADERS + "flat.gdshader")
			fm.set_shader_parameter("albedo", color)
			mat = fm
		"unshaded":
			var um := StandardMaterial3D.new()
			um.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
			um.albedo_color = color
			um.texture_filter = BaseMaterial3D.TEXTURE_FILTER_NEAREST
			mat = um
		_:
			var pm := StandardMaterial3D.new()
			pm.albedo_color = color
			pm.roughness = float(M["roughness"]) if typeof(M["roughness"]) != TYPE_STRING else 0.7
			pm.metallic_specular = float(M["specular"]) if typeof(M["specular"]) != TYPE_STRING else 0.5
			mat = pm
	return mat

## Palette post-process (canvas layer with a full-rect shader). Returns null when the style has no quantiser.
static func palette_layer(style: Dictionary) -> CanvasLayer:
	var M: Dictionary = style["material"]
	if not bool(M.get("palette_quantize", false)) or M.get("palette") == null:
		return null
	var layer := CanvasLayer.new()
	layer.name = "PalettePost"
	layer.layer = 100
	var rect := ColorRect.new()
	rect.set_anchors_preset(Control.PRESET_FULL_RECT)
	var sm := ShaderMaterial.new()
	sm.shader = load(SHADERS + "palette_post.gdshader")
	var pal := PackedVector3Array()
	for h in M["palette"]:
		var c := hexcol(h)
		pal.append(Vector3(c.r, c.g, c.b))
	var count := pal.size()
	while pal.size() < 32:
		pal.append(Vector3.ZERO)
	sm.set_shader_parameter("palette", pal)
	sm.set_shader_parameter("palette_count", count)
	rect.material = sm
	layer.add_child(rect)
	return layer

static func water_color(style: Dictionary, deep := false) -> Color:
	var W: Dictionary = style["water"]
	var v = W["deep"] if deep else W["shallow"]
	if typeof(v) == TYPE_STRING:
		return hexcol(v)
	return col(v)
