import base64
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rig_build_plugin as rb  # noqa: E402


def decode(remote):
    return base64.b64decode(remote.split(" ")[-1]).decode("utf-16-le")


class R:
    def __init__(self, code=0, out=""):
        self.returncode, self.stdout, self.stderr = code, out, ""


def plugin():
    d = os.path.join(tempfile.mkdtemp(), "WatooMCombat")
    os.makedirs(os.path.join(d, "Source", "WatooMCombat"))
    open(os.path.join(d, "WatooMCombat.uplugin"), "w").write("{}")
    return d


class Build(unittest.TestCase):
    def test_build_command_targets_saved_and_a_fresh_package(self):
        ps = rb.build_ps("WatooMCombat", "F:/P/Game", "F:/UE")
        self.assertIn('-Plugin="F:\\P\\Game\\Saved\\WatooMCombat\\WatooMCombat.uplugin"', ps)
        self.assertIn("Remove-Item -Recurse -Force $pkg", ps)          # never mixes old and new binaries
        self.assertIn("F:\\UE\\Engine\\Build\\BatchFiles\\RunUAT.bat", ps)

    def test_install_refuses_while_this_projects_editor_runs_and_skips_intermediate(self):
        ps = rb.install_ps("WatooMCombat", "F:/P/Game")
        self.assertIn("-like '*Game*'", ps)            # only THIS project's editor blocks, by command line
        self.assertIn("exit 3", ps)
        self.assertIn("/XD Intermediate", ps)
        self.assertLess(ps.index("exit 3"), ps.index("robocopy"))

    def test_errors_are_picked_from_compiler_and_uht_output(self):
        out = ("ok line\nWatooMProjectile.cpp(46,36): error C2664: cannot convert\n"
               "X.h(32): Error: An explicit Category specifier is required\nMarketplace\\Foo.Build.cs: error CS1: x\n")
        errs = rb.build_errors(out)
        self.assertEqual(len(errs), 2)

    def test_failed_build_installs_nothing(self):
        calls = []

        def run(cmd, **kw):
            calls.append(cmd)
            if cmd[0] == "ssh":
                return R(6, "X.cpp(1): error C2065: undeclared\nBUILD FAILED")
            return R(0)
        with self.assertRaises(SystemExit):
            rb.main([plugin(), "--install"], run=run, route_call=lambda *a, **k: self.fail("route used after a failed build"))
        self.assertEqual(sum(1 for c in calls if c[0] == "ssh"), 1)

    def test_install_waits_for_the_editor_to_be_gone_before_copying(self):
        seen, states = [], iter(["RUNNING 42", "RUNNING 42", "STOPPED"])

        def run(cmd, **kw):
            if cmd[0] != "ssh":
                return R(0)
            ps = decode(cmd[-1])
            if "BuildPlugin" in ps:
                seen.append("build")
                return R(0, "AutomationTool exiting with ExitCode=0 (Success)")
            if "robocopy" in ps:
                seen.append("install")
                return R(0, "INSTALLED today")
            seen.append(next(states))
            return R(0, seen[-1])
        route = []

        def call(cat, meth, args, t=600):
            route.append(meth)
            return '{"editorConnected": true, "success": true}'
        self.assertEqual(rb.main([plugin(), "--install"], run=run, sleep=lambda s: None, route_call=call), 0)
        self.assertEqual(seen, ["build", "RUNNING 42", "RUNNING 42", "STOPPED", "install"])
        self.assertEqual(route[:3], ["play_in_editor", "list_dirty_packages", "stop_editor"])
        self.assertIn("start_editor", route)


class Unsaved(unittest.TestCase):
    def test_unsaved_work_stops_the_install_before_any_copy(self):
        ssh = []

        def run(cmd, **kw):
            if cmd[0] == "ssh":
                ssh.append(decode(cmd[-1]))
                return R(0, "AutomationTool exiting with ExitCode=0 (Success)")
            return R(0)

        def call(cat, meth, args, t=600):
            if meth == "stop_editor":
                return '{"success": false, "dialogBlocking": true, "dialogTitle": "Save Content"}'
            return '{"success": true}'
        with self.assertRaises(SystemExit):
            rb.main([plugin(), "--install"], run=run, sleep=lambda s: None, route_call=call)
        self.assertFalse(any("robocopy" in p for p in ssh))


class Dirty(unittest.TestCase):
    def test_project_packages_count_temp_and_engine_do_not(self):
        r = '{"success": true, "content": ["/Game/ZAS/Creatures/A_Walk", "/Engine/Maps/Entry"], "maps": ["/Temp/Untitled_1"]}'
        self.assertEqual(rb.dirty_content(r), ["/Game/ZAS/Creatures/A_Walk"])
        self.assertEqual(rb.dirty_content('{"success": true, "content": [], "maps": []}'), [])

    def test_unsaved_content_stops_the_install_before_the_editor_is_stopped(self):
        seen = []

        def run(cmd, **kw):
            ps = decode(cmd[-1]) if cmd[0] == "ssh" else ""
            return R(0, "ExitCode=0") if "BuildPlugin" in ps else R(0, "")

        def call(cat, meth, args, t=600):
            seen.append(meth)
            if meth == "list_dirty_packages":
                return '{"success": true, "content": ["/Game/X/A_Walk"]}'
            return '{"success": true}'
        with self.assertRaises(SystemExit) as e:
            rb.main([plugin(), "--install"], run=run, sleep=lambda s: None, route_call=call)
        self.assertIn("/Game/X/A_Walk", str(e.exception))
        self.assertNotIn("stop_editor", seen)


class StopReplies(unittest.TestCase):
    def test_a_successful_stop_with_dirty_in_its_log_is_not_a_refusal(self):
        ssh = []

        def run(cmd, **kw):
            if cmd[0] != "ssh":
                return R(0)
            ps = decode(cmd[-1])
            ssh.append(ps)
            if "BuildPlugin" in ps:
                return R(0, "ExitCode=0")
            if "robocopy" in ps:
                return R(0, "INSTALLED now")
            return R(0, "STOPPED")

        def call(cat, meth, args, t=600):
            if meth == "stop_editor":
                return '{"success": true, "log": ["LogX: package marked dirty"]}'
            return '{"editorConnected": true, "success": true}'
        self.assertEqual(rb.main([plugin(), "--install"], run=run, sleep=lambda s: None, route_call=call), 0)
        self.assertTrue(any("robocopy" in p for p in ssh))


if __name__ == "__main__":
    unittest.main()


class Repin(unittest.TestCase):
    def test_launcher_is_repinned_after_the_stop_and_before_the_copy(self):
        seen = []

        def run(cmd, **kw):
            if cmd[0] != "ssh":
                return R(0)
            ps = decode(cmd[-1])
            if "BuildPlugin" in ps:
                return R(0, "AutomationTool exiting with ExitCode=0 (Success)")
            if "ue-mcp@" in ps:
                seen.append("pin")
                self.assertIn("ue-mcp@1.4.14", ps)
                return R(0, "PINNED 1.4.13 -> 1.4.14")
            if "robocopy" in ps:
                seen.append("install")
                return R(0, "INSTALLED today")
            seen.append("STOPPED")
            return R(0, "STOPPED")
        call = lambda cat, meth, args, t=600: '{"editorConnected": true, "success": true}'
        self.assertEqual(rb.main([plugin(), "--install", "--ue-mcp-version", "1.4.14"], run=run, sleep=lambda s: None,
                                 route_call=call), 0)
        self.assertEqual(seen, ["STOPPED", "pin", "install"])

    def test_a_failed_repin_installs_nothing(self):
        def run(cmd, **kw):
            if cmd[0] != "ssh":
                return R(0)
            ps = decode(cmd[-1])
            if "BuildPlugin" in ps:
                return R(0, "ExitCode=0")
            if "ue-mcp@" in ps:
                return R(5, "PIN FAILED: no ue-mcp@ in launcher")
            if "robocopy" in ps:
                raise AssertionError("copied after a failed re-pin")
            return R(0, "STOPPED")
        call = lambda cat, meth, args, t=600: '{"editorConnected": true, "success": true}'
        with self.assertRaises(SystemExit):
            rb.main([plugin(), "--install", "--ue-mcp-version", "1.4.14"], run=run, sleep=lambda s: None, route_call=call)

    def test_only_exact_versions_are_accepted(self):
        for bad in ("latest", "^1.4.14", "1.4"):
            with self.assertRaises(ValueError):
                rb.pin_ps(bad)
        with self.assertRaises(SystemExit):
            rb.main([plugin(), "--ue-mcp-version", "1.4.14"])


class ReuseBuild(unittest.TestCase):
    def test_reuse_skips_staging_and_build_and_checks_the_package_first(self):
        seen = []

        def run(cmd, **kw):
            if cmd[0] != "ssh":
                raise AssertionError("staged although --reuse-build")
            ps = decode(cmd[-1])
            if "BuildPlugin" in ps:
                raise AssertionError("built although --reuse-build")
            if "Pkg\\Binaries" in ps and "Test-Path" in ps:
                seen.append("package")
                return R(0, "PACKAGE today")
            if "robocopy" in ps:
                seen.append("install")
                return R(0, "INSTALLED today")
            return R(0, "STOPPED")
        call = lambda cat, meth, args, t=600: '{"editorConnected": true, "success": true}'
        self.assertEqual(rb.main([plugin(), "--install", "--reuse-build"], run=run, sleep=lambda s: None, route_call=call), 0)
        self.assertEqual(seen, ["package", "install"])

    def test_no_package_stops_before_the_editor_is_touched(self):
        route = []

        def run(cmd, **kw):
            return R(6, "NO PACKAGE")
        with self.assertRaises(SystemExit):
            rb.main([plugin(), "--install", "--reuse-build"], run=run, sleep=lambda s: None,
                    route_call=lambda *a, **k: route.append(a) or "{}")
        self.assertEqual(route, [])


class ProjectPlugins(unittest.TestCase):
    def test_project_plugins_are_applied_while_the_editor_is_stopped(self):
        seen = []

        def run(cmd, **kw):
            if cmd[0] != "ssh":
                return R(0)
            ps = decode(cmd[-1])
            if "BuildPlugin" in ps:
                return R(0, "ExitCode=0")
            if ps.startswith("$ProgressPreference") and "Get-Content" in ps:
                seen.append("read")
                return R(0, '{"Plugins": []}')
            if "WriteAllText" in ps and "FromBase64String" in ps:
                seen.append("write")
                return R(0, "WRITTEN")
            if "robocopy" in ps:
                seen.append("install")
                return R(0, "INSTALLED today")
            seen.append("STOPPED")
            return R(0, "STOPPED")
        call = lambda cat, meth, args, t=600: '{"editorConnected": true, "success": true}'
        self.assertEqual(rb.main([plugin(), "--install", "--project-plugins"], run=run, sleep=lambda s: None, route_call=call), 0)
        self.assertEqual(seen, ["STOPPED", "read", "write", "install"])


class StopInProgress(unittest.TestCase):
    def test_an_exiting_editor_is_waited_for_not_refused(self):
        def run(cmd, **kw):
            if cmd[0] != "ssh":
                return R(0)
            ps = decode(cmd[-1])
            if "BuildPlugin" in ps:
                return R(0, "ExitCode=0")
            if "robocopy" in ps:
                return R(0, "INSTALLED today")
            return R(0, "STOPPED")

        def call(cat, meth, args, t=600):
            if meth == "stop_editor":
                return '{"success": false, "error": "dirty state unknown", "log": {"exiting": true}}'
            return '{"editorConnected": true, "success": true}'
        self.assertEqual(rb.main([plugin(), "--install"], run=run, sleep=lambda s: None, route_call=call), 0)
