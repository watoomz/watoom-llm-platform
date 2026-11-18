import argparse
import json
import os
import tempfile
import unittest

import ue_project


def parser():
    ap = argparse.ArgumentParser()
    ap.add_argument("--z0", type=float, required=True)
    ap.add_argument("--sea-z", type=float, required=True)
    ap.add_argument("--landscape", required=True)
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("plan")
    p.add_argument("--size-m", type=float, required=True)
    return ap


class Profile(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.f = os.path.join(self.d, "p.json")
        json.dump({"z0": 10, "sea_cm": 99.5, "landscape": "Land", "size_m": 2000, "label_prefix": "G_"}, open(self.f, "w"))
        os.environ.pop("UE_PROJECT", None)

    def test_profile_fills_required_flags_including_subparsers(self):
        argv = ["--project", self.f, "plan"]
        ap = parser(); ue_project.apply(ap, argv)
        a = ap.parse_args(argv)
        self.assertEqual((a.z0, a.sea_z, a.landscape, a.size_m), (10.0, 99.5, "Land", 2000.0))
        self.assertEqual(ue_project.get("label_prefix"), "G_")

    def test_project_flag_after_the_subcommand(self):
        argv = ["plan", "--project", self.f]
        ap = parser(); ue_project.apply(ap, argv)
        a = ap.parse_args(argv)
        self.assertEqual((a.z0, a.landscape, a.size_m), (10.0, "Land", 2000.0))

    def test_command_line_wins(self):
        argv = ["--project", self.f, "--z0", "5", "plan"]
        ap = parser(); ue_project.apply(ap, argv)
        self.assertEqual(ap.parse_args(argv).z0, 5.0)

    def test_rig_connection_details_fill_from_the_profile_too(self):
        json.dump({"z0": 10, "sea_cm": 99.5, "landscape": "Land", "size_m": 2000, "host": "10.9.9.9", "port": 2299, "user": "rig", "key_dir": "/k"},
                  open(self.f, "w"))
        ap = argparse.ArgumentParser()
        ap.add_argument("--z0", type=float, required=True)
        ap.add_argument("--sea-z", type=float, required=True)
        ap.add_argument("--landscape", required=True)
        ap.add_argument("--host", default="10.99.1.44")
        ap.add_argument("--port", type=int, default=2224)
        ap.add_argument("--user", default="uemcp")
        ap.add_argument("--key-dir", default="/data/ai/ue-mcp-ssh")
        argv = ["--project", self.f]
        ue_project.apply(ap, argv)
        a = ap.parse_args(argv)
        self.assertEqual((a.host, a.port, a.user, a.key_dir), ("10.9.9.9", 2299, "rig", "/k"))

    def test_env_var(self):
        os.environ["UE_PROJECT"] = self.f
        try:
            ap = parser(); ue_project.apply(ap, ["plan"])
            self.assertEqual(ap.parse_args(["plan"]).landscape, "Land")
        finally:
            os.environ.pop("UE_PROJECT")

    def test_a_flag_with_plain_choices_is_not_mistaken_for_subcommands(self):
        ap = parser()
        ap.add_argument("--mode", choices=("a", "b"), default="a")
        argv = ["--project", self.f, "plan"]
        ue_project.apply(ap, argv)
        self.assertEqual(ap.parse_args(argv).mode, "a")

    def test_plane_and_river_water_materials_are_separate_keys(self):
        json.dump({"water_material": "/Game/W/MI_River", "plane_water_material": "/Game/P/M_Inst_Water"}, open(self.f, "w"))
        ap = argparse.ArgumentParser()
        ap.add_argument("--material", dest="plane_material", required=True)
        ue_project.apply(ap, ["--project", self.f])
        self.assertEqual(ap.parse_args(["--project", self.f]).plane_material, "/Game/P/M_Inst_Water")
        json.dump({"water_material": "/Game/W/MI_River"}, open(self.f, "w"))
        ap = argparse.ArgumentParser()
        ap.add_argument("--material", dest="plane_material", required=True)
        ue_project.apply(ap, ["--project", self.f])
        with self.assertRaises(SystemExit):   # a Water-plugin river material is never put on plain planes by default
            ap.parse_args(["--project", self.f])

    def test_without_profile_flags_stay_required(self):
        ap = parser(); ue_project.apply(ap, ["plan"])
        with self.assertRaises(SystemExit):
            ap.parse_args(["plan"])
        self.assertIsNone(ue_project.get("label_prefix"))


if __name__ == "__main__":
    unittest.main()
