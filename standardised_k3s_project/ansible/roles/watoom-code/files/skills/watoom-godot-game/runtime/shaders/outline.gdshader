shader_type spatial;
// Inverted-hull outline: used as next_pass of a material.
render_mode unshaded, cull_front;
uniform vec4 outline_color : source_color = vec4(0.1, 0.07, 0.15, 1.0);
uniform float thickness = 0.03;
void vertex() { VERTEX += NORMAL * thickness; }
void fragment() { ALBEDO = outline_color.rgb; }
