shader_type spatial;
// Per-triangle (faceted) lambert. No specular, no normal maps.
render_mode diffuse_lambert, specular_disabled;
uniform vec4 albedo : source_color = vec4(1.0);
void fragment() {
	ALBEDO = albedo.rgb;
	NORMAL = normalize(cross(dFdx(VERTEX), dFdy(VERTEX)));
}
