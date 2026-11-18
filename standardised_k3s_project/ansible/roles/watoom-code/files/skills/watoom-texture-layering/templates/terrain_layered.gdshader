shader_type spatial;
// watoom-texture-layering: splat-driven layered terrain material (up to 8 layers, 2 splat maps).
// Pair with scripts/layer_masks.py: splat_0.png / splat_1.png are the weight maps it writes (layer i -> splat_{i/4},
// channel i%4). Every layer is a pair of Texture2DArray slices: layer_albedo_height (RGB albedo sRGB, A height) and
// layer_normal_rough (RG tangent-space normal, B roughness, A ambient occlusion), all Non-Color except albedo.
//
// What makes this read as a professional terrain rather than a flat blend:
//   * height-blend: each layer's weight is biased by its own height channel, so pebbles/grass tufts poke through
//     and boundaries follow the surface detail instead of a straight cross-fade (`blend_depth`)
//   * triplanar on steep ground: planar XZ mapping stretches on cliffs; above `cliff_start` the cliff layers use
//     world-space triplanar sampling (`cliff_layer_mask` bit i = layer i is a rock/cliff layer)
//   * anti-tiling: a second sample at a rotated, different scale is mixed in by a low-frequency macro noise
//   * macro variation: a large-scale tint/roughness wobble over the whole terrain (`macro_scale`, `macro_tint`)
//   * detail fade: fine normal/colour detail fades with distance to save fill-rate and avoid shimmer

uniform sampler2D splat_0 : filter_linear, repeat_disable;
uniform sampler2D splat_1 : filter_linear, repeat_disable;
uniform sampler2DArray layer_albedo_height : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2DArray layer_normal_rough : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D macro_noise : filter_linear_mipmap, repeat_enable;      // any tileable greyscale noise

uniform int layer_count : hint_range(1, 8) = 4;
uniform vec2 terrain_size = vec2(1000.0, 1000.0);         // world XZ extent the splat maps cover
uniform vec2 terrain_origin = vec2(0.0, 0.0);             // world XZ of the splat maps' (0,0) corner
uniform vec4 layer_uv_scale_0 = vec4(0.25);              // texture repeats per metre, layers 0-3
uniform vec4 layer_uv_scale_1 = vec4(0.25);              // layers 4-7
uniform float blend_depth : hint_range(0.01, 0.6) = 0.15; // 0.01 = crisp height-blend, 0.6 = soft
uniform int cliff_layer_mask = 2;                         // bit i set -> layer i uses triplanar on cliffs (default: layer 1)
uniform float cliff_start : hint_range(0.0, 1.0) = 0.45;  // 1 - normal.y where triplanar starts
uniform float cliff_end : hint_range(0.0, 1.0) = 0.7;
uniform float macro_scale = 0.004;
uniform vec3 macro_tint = vec3(0.92, 0.95, 0.88);
uniform float macro_strength : hint_range(0.0, 1.0) = 0.3;
uniform float detail_fade_start = 40.0;
uniform float detail_fade_end = 160.0;

varying vec3 world_pos;
varying vec3 world_norm;

void vertex() {
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	world_norm = normalize((MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz);
}

float scale_of(int i) {
	if (i < 4) { return layer_uv_scale_0[i]; }
	return layer_uv_scale_1[i - 4];
}

float weight_of(vec4 s0, vec4 s1, int i) {
	if (i < 4) { return s0[i]; }
	return s1[i - 4];
}

vec4 sample_layer(sampler2DArray tex, int i, vec2 uv, vec3 w, vec3 tri_w, bool cliff, float tiling) {
	if (cliff) {
		vec4 x = texture(tex, vec3(w.zy * tiling, float(i)));
		vec4 y = texture(tex, vec3(w.xz * tiling, float(i)));
		vec4 z = texture(tex, vec3(w.xy * tiling, float(i)));
		return x * tri_w.x + y * tri_w.y + z * tri_w.z;
	}
	return texture(tex, vec3(uv * tiling, float(i)));
}

void fragment() {
	vec2 splat_uv = (world_pos.xz - terrain_origin) / terrain_size;
	vec4 s0 = texture(splat_0, splat_uv);
	vec4 s1 = texture(splat_1, splat_uv);

	float slope = clamp(1.0 - world_norm.y, 0.0, 1.0);
	float cliff = smoothstep(cliff_start, cliff_end, slope);
	vec3 tri_w = pow(abs(world_norm), vec3(4.0));
	tri_w /= max(tri_w.x + tri_w.y + tri_w.z, 1e-4);

	float macro = texture(macro_noise, world_pos.xz * macro_scale).r;
	float dist = length(VERTEX);
	float detail = 1.0 - smoothstep(detail_fade_start, detail_fade_end, dist);

	// pass 1: heights, to find the tallest weighted layer (height-blend)
	float w_a[8];
	float h_a[8];
	vec4 ah[8];
	vec4 nr[8];
	float top = 0.0;
	for (int i = 0; i < 8; i++) {
		if (i >= layer_count) { w_a[i] = 0.0; h_a[i] = 0.0; continue; }
		float tiling = scale_of(i);
		bool is_cliff = ((cliff_layer_mask >> i) & 1) == 1 && cliff > 0.001;
		vec2 uv = world_pos.xz;
		vec4 a = sample_layer(layer_albedo_height, i, uv, world_pos, tri_w, is_cliff, tiling);
		// anti-tiling: rotated, differently scaled second sample, mixed in by macro noise
		vec2 uv2 = vec2(uv.x * 0.8 - uv.y * 0.6, uv.x * 0.6 + uv.y * 0.8) + vec2(37.0, 11.0);
		vec4 a2 = texture(layer_albedo_height, vec3(uv2 * tiling * 0.37, float(i)));
		ah[i] = mix(a, a2, smoothstep(0.35, 0.65, macro) * 0.5);
		nr[i] = sample_layer(layer_normal_rough, i, uv, world_pos, tri_w, is_cliff, tiling);
		w_a[i] = weight_of(s0, s1, i);
		h_a[i] = ah[i].a;
		top = max(top, w_a[i] + h_a[i] * w_a[i]);
	}
	// pass 2: height-biased weights, renormalised
	float total = 0.0;
	for (int i = 0; i < 8; i++) {
		float b = max(w_a[i] + h_a[i] * w_a[i] - (top - blend_depth), 0.0) * step(0.0001, w_a[i]);
		w_a[i] = b;
		total += b;
	}
	vec3 albedo = vec3(0.0);
	vec3 normal_ts = vec3(0.0);
	float rough = 0.0;
	float ao = 0.0;
	for (int i = 0; i < 8; i++) {
		float k = w_a[i] / max(total, 1e-4);
		albedo += ah[i].rgb * k;
		normal_ts += vec3(nr[i].rg * 2.0 - 1.0, 0.0) * k;
		rough += nr[i].b * k;
		ao += nr[i].a * k;
	}
	albedo = mix(albedo, albedo * macro_tint, macro_strength * (macro - 0.5) * 2.0 + macro_strength * 0.5);
	vec2 nxy = normal_ts.xy * detail;
	vec3 n_ts = vec3(nxy, sqrt(max(1.0 - dot(nxy, nxy), 0.0)));   // rebuild Z so the blended normal stays unit length
	NORMAL_MAP = n_ts * 0.5 + 0.5;
	NORMAL_MAP_DEPTH = 1.0;
	ALBEDO = albedo;
	ROUGHNESS = clamp(rough + (macro - 0.5) * 0.15, 0.04, 1.0);
	AO = ao;
	AO_LIGHT_AFFECT = 0.4;
	SPECULAR = 0.3;
}
