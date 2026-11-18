shader_type spatial;
#include "res://addons/gg/shaders/terrain_splat.gdshaderinc"
uniform float roughness_value : hint_range(0.0, 1.0) = 0.8;
void vertex() { world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz; }
void fragment() { ALBEDO = splat_albedo(world_pos); ROUGHNESS = roughness_value; }
