import importlib.util
import pathlib
import unittest

spec = importlib.util.spec_from_file_location("usf", pathlib.Path(__file__).with_name("unreal_scale_fit.py"))
usf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(usf)


class Fit(unittest.TestCase):
    def test_house_is_shrunk_to_a_human_scale(self):
        out, bad = usf.fit({"H": {"class": "house", "height_cm": 1847, "scale": 1.0}})
        self.assertEqual(bad, [])
        self.assertAlmostEqual(out["H"]["scale"], 800 / 1847, places=3)

    def test_measurement_of_a_scaled_actor_composes_with_its_current_scale(self):
        out, _ = usf.fit({"W": {"class": "wizard", "height_cm": 295, "scale": 1.6}})
        self.assertAlmostEqual(out["W"]["scale"], 1.6 * 185 / 295, places=3)
        self.assertLess(out["W"]["scale"], 1.1)

    def test_unknown_class_and_missing_metric_are_reported_not_guessed(self):
        out, bad = usf.fit({"A": {"class": "ufo", "height_cm": 10}, "B": {"class": "house"}})
        self.assertEqual(out, {})
        self.assertEqual(len(bad), 2)

    def test_custom_targets_override_defaults(self):
        out, _ = usf.fit({"H": {"class": "house", "height_cm": 1000}}, {"house": {"metric": "height_cm", "cm": 500}})
        self.assertAlmostEqual(out["H"]["scale"], 0.5, places=3)


if __name__ == "__main__":
    unittest.main()
