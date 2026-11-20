import pathlib, sys, unittest, importlib.util

sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
spec = importlib.util.spec_from_file_location("platform_build", pathlib.Path(__file__).parents[1] / "build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class BuildEnvironment(unittest.TestCase):
    def test_exact_source_trust_is_inherited_without_global_wildcard(self):
        base = {
            "HOME": "/private",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "existing.setting",
            "GIT_CONFIG_VALUE_0": "preserved",
        }
        env = build.source_environment(pathlib.Path("/owned/source with spaces"), base)
        self.assertEqual(env["GIT_CONFIG_KEY_1"], "safe.directory")
        self.assertEqual(env["GIT_CONFIG_VALUE_1"], "/owned/source with spaces")
        self.assertEqual(env["GIT_CONFIG_COUNT"], "2")
        self.assertEqual(env["GIT_CONFIG_VALUE_0"], "preserved")
        self.assertEqual(base["GIT_CONFIG_COUNT"], "1")
        self.assertNotIn("*", env.values())

    def test_invalid_environment_count_fails_closed(self):
        for count in ("-1", "33", "bad"):
            with self.assertRaises(ValueError):
                build.source_environment(pathlib.Path("/owned"), {"GIT_CONFIG_COUNT": count})


if __name__ == "__main__":
    unittest.main()
