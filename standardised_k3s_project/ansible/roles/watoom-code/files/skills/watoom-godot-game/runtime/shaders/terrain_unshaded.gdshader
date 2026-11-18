shader_type spatial;
render_mode unshaded;
#include "res://addons/gg/shaders/terrain_splat.gdshaderinc"
void vertex() { world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz; }
void fragment() { ALBEDO = splat_albedo(world_pos); }
