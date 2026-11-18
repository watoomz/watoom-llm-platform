shader_type spatial;
// Rural terrain material for watoom-terrain-map meshes. Blends grass / dirt /
// rock by slope and elevation with procedural detail, so real DEM landforms read
// as countryside without any external textures. Pair with terrain.gd, which sets
// world_min_y / world_max_y from the heightmap's real elevation range.

uniform float world_min_y = 0.0;
uniform float world_max_y = 200.0;
uniform vec3 grass_low  = vec3(0.26, 0.34, 0.16);
uniform vec3 grass_high = vec3(0.40, 0.44, 0.22);
uniform vec3 dirt_col   = vec3(0.34, 0.25, 0.14);
uniform vec3 rock_col   = vec3(0.38, 0.37, 0.35);
uniform float detail_scale = 0.35;   // metres^-1 for fine grain

varying vec3 world_pos;
varying vec3 world_norm;

void vertex() {
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	world_norm = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
}

float hash21(vec2 p) {
	p = fract(p * vec2(123.34, 456.21));
	p += dot(p, p + 45.32);
	return fract(p.x * p.y);
}

float noise2(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	vec2 u = f * f * (3.0 - 2.0 * f);
	float a = hash21(i);
	float b = hash21(i + vec2(1.0, 0.0));
	float c = hash21(i + vec2(0.0, 1.0));
	float d = hash21(i + vec2(1.0, 1.0));
	return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}

float fbm(vec2 p) {
	float v = 0.0;
	float a = 0.5;
	for (int i = 0; i < 5; i++) {
		v += a * noise2(p);
		p = p * 2.13 + vec2(11.7, 5.3);
		a *= 0.5;
	}
	return v;
}

void fragment() {
	vec2 uv = world_pos.xz;
	// rotate to break axis alignment on the procedural detail
	vec2 rot = vec2(uv.x * 0.7071 + uv.y * 0.7071, -uv.x * 0.7071 + uv.y * 0.7071);

	float slope = clamp(1.0 - world_norm.y, 0.0, 1.0);          // 0 flat, 1 vertical
	float elev = clamp((world_pos.y - world_min_y) / max(1.0, world_max_y - world_min_y), 0.0, 1.0);

	float patch = fbm(rot * 0.01);                              // large grass/dry variation
	vec3 grass = mix(grass_low, grass_high, clamp(patch * 1.3, 0.0, 1.0));

	// dirt appears on moderate slopes and dry high patches; rock on steep ground
	float dirt_m = smoothstep(0.18, 0.4, slope) * (1.0 - smoothstep(0.55, 0.85, slope));
	dirt_m = max(dirt_m, smoothstep(0.7, 1.0, elev) * 0.5);
	float rock_m = smoothstep(0.55, 0.8, slope);

	vec3 col = grass;
	col = mix(col, dirt_col, clamp(dirt_m, 0.0, 1.0));
	col = mix(col, rock_col, clamp(rock_m, 0.0, 1.0));

	// fine grain so close-up ground is not flat
	float grain = fbm(rot * detail_scale) - 0.5;
	col *= 1.0 + grain * 0.18;

	ALBEDO = col;
	ROUGHNESS = mix(0.95, 0.75, rock_m);
	SPECULAR = 0.02;
}
