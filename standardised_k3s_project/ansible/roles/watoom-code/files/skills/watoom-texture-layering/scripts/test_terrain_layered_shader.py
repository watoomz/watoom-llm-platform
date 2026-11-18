import os
import pathlib
import subprocess
import tempfile
import unittest

GODOT = os.environ.get("GODOT", "/data/ai/toolchains/godot/4.7.2/godot")
SHADER = pathlib.Path(__file__).resolve().parent.parent / "templates" / "terrain_layered.gdshader"
PROBE = '''extends SceneTree
func _init():
	var sh := Shader.new()
	sh.code = FileAccess.open("res://shader.gdshader", FileAccess.READ).get_as_text()
	var names := []
	for u in sh.get_shader_uniform_list():
		names.append(u["name"])
	print("PROBE uniforms=", names.size(), " ", ",".join(names))
	quit()
'''


def run_probe(code):
    d = tempfile.mkdtemp()
    pathlib.Path(d, "project.godot").write_text('[application]\nconfig/name="shader-probe"\n')
    pathlib.Path(d, "probe.gd").write_text(PROBE)
    pathlib.Path(d, "shader.gdshader").write_text(code)
    p = subprocess.run([GODOT, "--headless", "--path", d, "--script", "res://probe.gd"], capture_output=True, text=True, timeout=120)
    return p.stdout + p.stderr


@unittest.skipUnless(os.path.exists(GODOT), "pinned Godot not installed here")
class LayeredShader(unittest.TestCase):
    def test_layered_terrain_shader_compiles_with_its_uniforms(self):
        out = run_probe(SHADER.read_text())
        self.assertNotIn("SHADER ERROR", out, out[-800:])
        line = next(l for l in out.splitlines() if l.startswith("PROBE uniforms="))
        for u in ("splat_0", "splat_1", "layer_albedo_height", "layer_normal_rough", "blend_depth", "cliff_layer_mask", "terrain_size", "terrain_origin"):
            self.assertIn(u, line)

    def test_the_probe_does_catch_a_broken_shader(self):
        out = run_probe("shader_type spatial;\nvoid fragment(){ ALBEDO = vec3(not_defined); }\n")
        self.assertIn("SHADER ERROR", out)


if __name__ == "__main__":
    unittest.main()
