import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unreal_niagara_fx as fx  # noqa: E402

ROOT = "/Game/G/Combat"


def calls_of(phases, method):
    return [a for p in phases for m, a in p["calls"] if m == method]


class Fx(unittest.TestCase):
    def test_every_recipe_builds_template_copies_a_system_and_checks_it(self):
        for r in ("projectile", "impact", "muzzle", "area", "aura", "tracer", "lightning"):
            phases, paths = fx.fx_calls(ROOT, {"NS_X": {"recipe": r, "element": "Frost"}})
            methods = [m for m, a in phases[0]["calls"]]
            self.assertEqual(methods[-3:], ["niagara.compile", "asset.save", "niagara.validate"], r)  # edits persisted
            created = calls_of(phases, "niagara.create_emitter")
            self.assertTrue(created and all(c["templatePath"].startswith(fx.TEMPLATES) for c in created), r)
            sysc, = calls_of(phases, "niagara.create_system_from_spec")
            self.assertEqual([e["path"] for e in sysc["emitters"]], [ROOT + "/FX/Emitters/" + c["name"] for c in created])
            self.assertEqual(paths["NS_X"], ROOT + "/FX/NS_X")

    def test_inputs_target_the_named_emitter_module_and_stack(self):
        phases, _ = fx.fx_calls(ROOT, {"NS_Fireball_Impact": {"recipe": "impact", "element": "Fire"}})
        col = [a for a in calls_of(phases, "niagara.set_module_input") if a["inputName"] == "Color"]
        self.assertEqual({a["emitterName"] for a in col}, {"NE_Fireball_Impact_Sparks", "NE_Fireball_Impact_Flash"})
        self.assertTrue(all(a["stackContext"] == "ParticleSpawn" and a["moduleName"] == "InitializeParticle" for a in col))
        self.assertGreater(col[0]["value"]["r"], col[0]["value"]["b"])  # fire is red-hot, not blue

    def test_one_shot_effects_use_burst_templates_only(self):
        for r in ("impact", "muzzle", "area"):
            for l in fx.recipe_layers({"recipe": r}):
                self.assertIn(l["template"], ("OmnidirectionalBurst", "DirectionalBurst"), r)  # these loop once

    def test_ribbon_trail_gets_a_spawn_module_before_its_inputs(self):
        phases, _ = fx.fx_calls(ROOT, {"NS_B": {"recipe": "projectile"}})
        calls = phases[0]["calls"]
        i = [k for k, (m, a) in enumerate(calls) if m == "niagara.add_module"]
        self.assertEqual(len(i), 1)
        self.assertEqual(calls[i[0]][1]["emitterName"], "NE_B_Trail")
        self.assertEqual(calls[i[0] - 1], ["niagara.remove_module", {"systemPath": ROOT + "/FX/NS_B", "emitterName": "NE_B_Trail",
                                                                     "stackContext": "EmitterUpdate", "moduleName": "SpawnPerFrame"}])
        self.assertLess(i[0], min(k for k, (m, a) in enumerate(calls) if m == "niagara.set_module_input" and a["emitterName"] == "NE_B_Trail"))

    def test_aura_plays_once_for_its_duration(self):
        phases, _ = fx.fx_calls(ROOT, {"NS_A": {"recipe": "aura", "duration": 3}})
        sw, = calls_of(phases, "niagara.set_static_switch")
        self.assertEqual((sw["moduleName"], sw["switchName"], sw["value"]), ("EmitterState", "Loop Behavior", fx.ONCE))
        d, = [a for a in calls_of(phases, "niagara.set_module_input") if a["inputName"] == "Loop Duration"]
        self.assertEqual(d["value"], 3.0)

    def test_scale_and_radius_change_the_numbers(self):
        small = fx.recipe_layers({"recipe": "area", "radius": 100})[0]["inputs"]
        big = fx.recipe_layers({"recipe": "area", "radius": 600})[0]["inputs"]
        k = "ParticleSpawn/ShapeLocation/Sphere Radius"
        self.assertLess(small[k], big[k])

    def test_custom_layers_and_rgb_colours(self):
        phases, _ = fx.fx_calls(ROOT, {"NS_C": {"layers": [{"template": "Fountain", "inputs": {"EmitterUpdate/SpawnRate/SpawnRate": 30}}]}})
        a, = calls_of(phases, "niagara.set_module_input")
        self.assertEqual((a["emitterName"], a["moduleName"], a["inputName"], a["value"]), ("NE_C_L0", "SpawnRate", "SpawnRate", 30))
        self.assertEqual(fx.colour([1, 2, 3], 2)["b"], 6)

    def test_beams_end_at_the_world_hit_point_and_play_once(self):
        for r, n in (("tracer", 1), ("lightning", 2)):
            phases, _ = fx.fx_calls(ROOT, {"NS_T": {"recipe": r, "element": "Lightning"}})
            uv, = calls_of(phases, "niagara.epic_add_user_variables")
            self.assertEqual([v["name"] for v in uv["variablesToAdd"]], ["BeamEnd"])  # once per system, no "User." prefix
            ex = calls_of(phases, "niagara.epic_set_stack_input_data")
            self.assertEqual(len(ex), 2 * n)  # Beam End + Beam Width per beam
            ex = [e for e in ex if e["stackInputRef"]["inputNameStack"] == ["Beam End"]]
            ref = ex[0]["stackInputRef"]
            self.assertEqual((ref["scriptName"], ref["moduleName"], ref["inputNameStack"]), ("EmitterUpdateScript", "BeamEmitterSetup", ["Beam End"]))
            self.assertIn("SystemWorldToLocal", ex[0]["inputData"]["value"]["hlslExpression"])
            methods = [m for m, a in phases[0]["calls"]]
            self.assertLess(methods.index("niagara.epic_add_user_variables"), methods.index("niagara.epic_set_stack_input_data"))
            once = [a for a in calls_of(phases, "niagara.set_static_switch") if a["switchName"] == "Loop Behavior"]
            self.assertEqual(len(once), n)

    def test_bad_specs_fail_loudly(self):
        with self.assertRaises(ValueError):
            fx.recipe_layers({"recipe": "laser"})
        with self.assertRaises(ValueError):
            fx.colour("Plasma")
        with self.assertRaises(ValueError):
            fx.fx_calls(ROOT, {"NS bad": {"recipe": "aura"}})


if __name__ == "__main__":
    unittest.main()
