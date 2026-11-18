// Shared by terrain_*.gdshader: weights from two splat maps (layer i -> splat_{i/4}, channel i%4) mix flat layer colours.
// UV convention (measured by gg_terrain.py build): splat uv = (world.xz - terrain_origin) / terrain_size, so image row 0 is the lowest Z.
uniform sampler2D splat_0 : filter_linear, repeat_disable;
uniform sampler2D splat_1 : filter_linear, repeat_disable;
// Eight separate uniforms: an array uniform read back as null after the material was saved and reloaded (measured).
uniform vec3 layer_color_0 : source_color = vec3(0.0);
uniform vec3 layer_color_1 : source_color = vec3(0.0);
uniform vec3 layer_color_2 : source_color = vec3(0.0);
uniform vec3 layer_color_3 : source_color = vec3(0.0);
uniform vec3 layer_color_4 : source_color = vec3(0.0);
uniform vec3 layer_color_5 : source_color = vec3(0.0);
uniform vec3 layer_color_6 : source_color = vec3(0.0);
uniform vec3 layer_color_7 : source_color = vec3(0.0);
uniform int layer_count : hint_range(1, 8) = 4;
uniform vec2 terrain_size = vec2(256.0, 256.0);
uniform vec2 terrain_origin = vec2(0.0, 0.0);
varying vec3 world_pos;

vec3 layer_col(int i) {
	if (i == 0) { return layer_color_0; }
	if (i == 1) { return layer_color_1; }
	if (i == 2) { return layer_color_2; }
	if (i == 3) { return layer_color_3; }
	if (i == 4) { return layer_color_4; }
	if (i == 5) { return layer_color_5; }
	if (i == 6) { return layer_color_6; }
	return layer_color_7;
}

vec3 splat_albedo(vec3 wp) {
	vec2 uv = (wp.xz - terrain_origin) / terrain_size;
	vec4 s0 = texture(splat_0, uv);
	vec4 s1 = texture(splat_1, uv);
	vec3 c = vec3(0.0);
	for (int i = 0; i < 8; i++) {
		if (i >= layer_count) { break; }
		float w = (i < 4) ? s0[i] : s1[i - 4];
		c += layer_col(i) * w;
	}
	return c;
}
