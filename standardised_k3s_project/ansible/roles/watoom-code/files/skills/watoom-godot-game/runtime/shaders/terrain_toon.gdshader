shader_type spatial;
render_mode diffuse_burley, specular_disabled;
#include "res://addons/gg/shaders/terrain_splat.gdshaderinc"
uniform float bands : hint_range(2.0, 6.0) = 2.0;
uniform float softness : hint_range(0.0, 1.0) = 0.15;
uniform float shade_floor : hint_range(0.0, 1.0) = 0.45;
void vertex() { world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz; }
void fragment() { ALBEDO = splat_albedo(world_pos); }
void light() {
	float nl = clamp(dot(NORMAL, LIGHT) * ATTENUATION, 0.0, 1.0);
	float step_w = max(softness / bands, 0.001);
	float q = floor(nl * bands) / bands;
	float f = fract(nl * bands);
	float ramp = q + smoothstep(0.0, step_w * bands, f) / bands;
	ramp = mix(shade_floor, 1.0, clamp(ramp, 0.0, 1.0));
	DIFFUSE_LIGHT += LIGHT_COLOR * ramp * ALBEDO / PI;
}
