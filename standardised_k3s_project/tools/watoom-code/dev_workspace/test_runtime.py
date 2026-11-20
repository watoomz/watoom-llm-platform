import importlib.util, pathlib, tempfile, unittest

spec = importlib.util.spec_from_file_location("dev_runtime", pathlib.Path(__file__).with_name("runtime.py"))
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


class Boundary(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        p = pathlib.Path(self.temp.name)
        (p / "workspace/.git").mkdir(parents=True)
        self.runtime = r.Runtime(
            {"workspace": str(p / "workspace"), "state": str(p / "state"), "enabled": True, "uid": 65534, "gid": 65534}
        )

    def test_requests_fail_before_execution(self):
        for value in [
            {"op": "deploy", "job": "owned", "session": "owned-session"},
            {"op": "run", "job": "../../production", "session": "owned-session"},
            {"op": "status", "job": "owned", "session": None},
            {"op": "status", "job": "owned", "session": "owned-session", "uid": 0},
        ]:
            with self.assertRaises((PermissionError, ValueError)):
                self.runtime.request(value)

    def test_sandbox_has_no_host_paths_or_network(self):
        args = self.runtime.sandbox(["/usr/bin/true"])
        self.assertIn("--unshare-all", args)
        self.assertIn("--disable-userns", args)
        self.assertNotIn("--share-net", args)
        self.assertNotIn("/data/github", args)
        self.assertEqual(args[-4:], ["--remount-ro", "/", "--", "/usr/bin/true"])
        self.assertIn(str(self.runtime.workspace / " .git").replace("/ .git", "/.git"), args)


if __name__ == "__main__":
    unittest.main()
