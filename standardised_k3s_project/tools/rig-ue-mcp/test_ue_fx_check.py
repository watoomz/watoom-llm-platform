import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_fx_check as fc  # noqa: E402

CALLS = {"phases": [{"name": "fx NS_A", "calls": [
    ["niagara.create_emitter", {"name": "NE_A_Sparks", "templatePath": "/Niagara/T/OmnidirectionalBurst"}],
    ["niagara.create_emitter", {"name": "NE_A_Flash", "templatePath": "/Niagara/T/OmnidirectionalBurst"}],
    ["niagara.create_emitter", {"name": "NE_A_Trail", "templatePath": "/Niagara/T/LocationBasedRibbon"}],
    ["niagara.create_system_from_spec", {"name": "NS_A", "packagePath": "/Game/G/FX", "emitters": [
        {"path": "/Game/G/FX/Emitters/NE_A_Sparks"}, {"path": "/Game/G/FX/Emitters/NE_A_Flash"}, {"path": "/Game/G/FX/Emitters/NE_A_Trail"}]}],
    ["niagara.set_module_input", {"systemPath": "/Game/G/FX/NS_A", "emitterName": "NE_A_Flash", "inputName": "Lifetime Max", "value": 0.1}],
    ["niagara.set_module_input", {"systemPath": "/Game/G/FX/NS_A", "emitterName": "NE_A_Sparks", "inputName": "Lifetime Max", "value": 0.7}],
]}]}


class FxCheck(unittest.TestCase):
    def setUp(self):
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(CALLS, f)
        f.close()
        self.s = fc.systems_from_calls(f.name)

    def test_systems_emitters_lifetimes_and_ribbons_are_read_from_the_calls(self):
        em = self.s["/Game/G/FX/NS_A"]
        self.assertEqual(sorted(em), ["NE_A_Flash", "NE_A_Sparks", "NE_A_Trail"])
        self.assertEqual(em["NE_A_Flash"]["lifetime_max"], 0.1)
        self.assertTrue(em["NE_A_Trail"]["moves"])

    def test_empty_emitters_fail_unless_a_known_gap_explains_them(self):
        em = self.s["/Game/G/FX/NS_A"]
        self.assertEqual(fc.judge("NE_A_Sparks", em["NE_A_Sparks"], [0, 0])[0], "FAIL")
        self.assertEqual(fc.judge("NE_A_Flash", em["NE_A_Flash"], [0, 0])[0], "SKIP")
        self.assertEqual(fc.judge("NE_A_Trail", em["NE_A_Trail"], [])[0], "FAIL")  # a ribbon with no spawner
        self.assertEqual(fc.judge("NE_A_Sparks", em["NE_A_Sparks"], [0, 120])[0], "OK")


if __name__ == "__main__":
    unittest.main()
