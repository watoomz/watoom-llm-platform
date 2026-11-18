shader_type canvas_item;
// Snap every screen pixel to the nearest colour of a palette (max 32).
uniform sampler2D screen_tex : hint_screen_texture, filter_nearest;
uniform vec3 palette[32];
uniform int palette_count = 16;
void fragment() {
	vec3 c = texture(screen_tex, SCREEN_UV).rgb;
	vec3 best = palette[0];
	float bd = 1e9;
	for (int i = 0; i < 32; i++) {
		if (i >= palette_count) { break; }
		vec3 d = c - palette[i];
		float dd = dot(d, d);
		if (dd < bd) { bd = dd; best = palette[i]; }
	}
	COLOR = vec4(best, 1.0);
}
