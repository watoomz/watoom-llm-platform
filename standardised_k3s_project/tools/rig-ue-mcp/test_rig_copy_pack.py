import os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rig_copy_pack as rc


class Copy(unittest.TestCase):
    def test_one_scp_per_content_folder(self):
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "Content", "PN_Banana"))
        os.makedirs(os.path.join(d, "Content", "Other"))
        open(os.path.join(d, "Content", "stray.txt"), "w").close()
        cmds = rc.scp_args(d, dest="F:/Proj/Content/")
        self.assertEqual(len(cmds), 2)
        self.assertTrue(cmds[0][-2].endswith("Other") and "migrate@" in cmds[0][-1] and "F:/Proj/Content/" in cmds[0][-1])
        self.assertIn("-P", cmds[0])

    def test_dry_run_is_the_default_and_apply_copies(self):
        import contextlib, io
        from unittest import mock
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "Content", "PN_Banana"))
        ran = []
        fake = lambda cmd, **kw: ran.append(cmd) or type("R", (), {"returncode": 0})()
        for argv in ([d, "--dest", "F:/Proj/Content/"], [d, "--dest", "F:/Proj/Content/", "--dry-run"], [d, "--dest", "F:/Proj/Content/", "--apply", "--dry-run"]):
            out = io.StringIO()
            with mock.patch.object(rc.subprocess, "run", fake), contextlib.redirect_stdout(out):
                self.assertEqual(rc.main(argv), 0)
            self.assertEqual(ran, [], argv)                      # the live Content folder is not touched without --apply
            self.assertIn("scp -r", out.getvalue())
            self.assertIn("nothing copied", out.getvalue())
        with mock.patch.object(rc.subprocess, "run", fake), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(rc.main([d, "--dest", "F:/Proj/Content/", "--apply"]), 0)
        self.assertEqual(len(ran), 1)
        self.assertEqual(ran[0][:3], ["nice", "-n", "10"])
        self.assertTrue(ran[0][-1].endswith("F:/Proj/Content/"))

    def test_non_ue_pack_is_refused(self):
        with self.assertRaises(ValueError):
            rc.scp_args(tempfile.mkdtemp())


class Plugin(unittest.TestCase):
    def make(self, name="WatooMCombat", uplugin="WatooMCombat"):
        root = tempfile.mkdtemp()
        d = os.path.join(root, name)
        os.makedirs(os.path.join(d, "Source", name))
        open(os.path.join(d, uplugin + ".uplugin"), "w").write("{}")
        return d

    def test_plugin_is_one_scp_of_the_whole_folder(self):
        d = self.make()
        (cmd,) = rc.plugin_scp_args(d + "/", dest="F:/Proj/Plugins/")
        self.assertEqual(cmd[-2], d)
        self.assertTrue(cmd[-1].endswith(":F:/Proj/Plugins/"))

    def test_bad_plugin_folders_are_refused(self):
        with self.assertRaises(ValueError):
            rc.plugin_scp_args(tempfile.mkdtemp(), dest="x")             # no .uplugin
        with self.assertRaises(ValueError):
            rc.plugin_scp_args(self.make(uplugin="Other"), dest="x")    # folder name != plugin name
        d = self.make()
        os.makedirs(os.path.join(d, "Binaries"))
        with self.assertRaises(ValueError):
            rc.plugin_scp_args(d, dest="x")                              # prebuilt binaries: build on the rig

    def test_plugin_mode_skips_the_content_check_and_stays_a_dry_run(self):
        import contextlib, io
        from unittest import mock
        d = self.make()
        ran = []
        fake = lambda cmd, **kw: ran.append(cmd) or type("R", (), {"returncode": 0})()
        with mock.patch.object(rc.subprocess, "run", fake), mock.patch.object(rc.ue_asset_check, "check_packs", side_effect=AssertionError), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(rc.main(["--plugin", d, "--dest", "F:/Proj/Plugins/"]), 0)
            self.assertEqual(ran, [])
            self.assertEqual(rc.main(["--plugin", "--apply", d, "--dest", "F:/Proj/Plugins/"]), 0)
        self.assertEqual(len(ran), 1)


class External(unittest.TestCase):
    def test_world_partition_external_folders_are_not_copied(self):
        d = tempfile.mkdtemp()
        for f in ("Content/Rogue/A.uasset", "Content/__ExternalActors__/ThirdPerson/Maps/M/0/x.uasset",
                  "Content/__ExternalObjects__/ThirdPerson/Maps/M/0/y.uasset"):
            os.makedirs(os.path.dirname(os.path.join(d, f)), exist_ok=True)
            open(os.path.join(d, f), "w").close()
        cmds = rc.scp_args(d, dest="F:/Proj/Content/")
        self.assertEqual([os.path.basename(c[-2]) for c in cmds], ["Rogue"])


if __name__ == "__main__":
    unittest.main()
