import importlib.util, pathlib, tempfile, unittest

spec = importlib.util.spec_from_file_location(
    "capture_index", pathlib.Path(__file__).parents[1] / "project_captures.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CaptureIndex(unittest.TestCase):
    def test_registration_and_safe_boundaries(self):
        with tempfile.TemporaryDirectory() as temp:
            base = pathlib.Path(temp)
            projects = base / "projects"
            shared = base / "captures"
            project = projects / "games/demo"
            project.mkdir(parents=True)
            shared.mkdir()
            first = module.register(project, projects, shared)
            self.assertEqual(module.register(project, projects, shared), first)
            self.assertEqual(pathlib.Path(first["view_captures_at"]).resolve(), project / ".opencode/captures")
            outside = base / "outside"
            outside.mkdir()
            with self.assertRaises(ValueError):
                module.register(outside, projects, shared)
            other = projects / "escape/child"
            other.mkdir(parents=True)
            (shared / "escape").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                module.register(other, projects, shared)
            self.assertFalse((outside / "child").exists())


if __name__ == "__main__":
    unittest.main()
