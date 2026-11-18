import importlib.util, pathlib, unittest
spec = importlib.util.spec_from_file_location("rvf", pathlib.Path(__file__).with_name("rig_vault_fetch.py"))
rvf = importlib.util.module_from_spec(spec); spec.loader.exec_module(rvf)


class Pick(unittest.TestCase):
    def test_matches_on_the_first_eight_characters_of_the_uuid(self):
        names = ["Swamp_Monster-618e8e5f", "Snake_Robotic_Warrior-ba92ee1f", "Birds-a34b6ed1"]
        self.assertEqual(rvf.pick(names, ["618e8e5f-99fa-41ad-8cf8-ddffed96f8d1"]), ["Swamp_Monster-618e8e5f"])
        self.assertEqual(rvf.pick(names, ["BA92EE1F"]), ["Snake_Robotic_Warrior-ba92ee1f"])
        self.assertEqual(rvf.pick(names, ["deadbeef"]), [])


if __name__ == "__main__":
    unittest.main()
