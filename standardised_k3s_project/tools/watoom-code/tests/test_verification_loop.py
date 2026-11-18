import pathlib, sys, tempfile, unittest
from unittest.mock import patch
HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import verification_loop as vl


class GraderSelection(unittest.TestCase):
    def names(self, rel):
        return [g[0] for g in vl.graders_for(rel)]

    def test_file_types_map_to_the_right_graders(self):
        self.assertEqual(self.names("ansible/roles/x/tasks/main.yml"), ["ansible-lint"])
        self.assertEqual(self.names("ansible/playbooks/p.yml"), ["ansible-lint", "ansible-syntax"])
        self.assertEqual(self.names("scripts/do.sh"), ["bash-n"])
        self.assertEqual(self.names("tools/x.py"), ["py-compile"])
        self.assertEqual(self.names("config/x.json"), ["json-parse"])
        self.assertEqual(self.names("README.md"), [])  # unsupported type → no grader

    def test_non_ansible_yaml_parses_and_lints_only_with_a_config(self):
        with patch.object(vl, "yamllint_config", return_value=None):
            self.assertEqual(self.names("config/x.yaml"), ["yaml-parse"])
        with patch.object(vl, "yamllint_config", return_value="/repo/.yamllint"):
            self.assertEqual(self.names("config/x.yaml"), ["yaml-parse", "yamllint"])


class Grading(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        patch.object(vl, "ROOT", self.root).start()
        self.addCleanup(patch.stopall)
        self.addCleanup(self.tmp.cleanup)

    def write(self, rel, text):
        file = self.root / rel
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text)

    def test_valid_and_invalid_files_get_the_grader_verdict(self):
        self.write("tools/good.py", "x = 1\n")
        self.write("tools/bad.py", "def (:\n")
        self.write("config/good.json", '{"a": 1}')
        self.write("config/bad.json", "{not json")
        self.write("scripts/good.sh", "echo hi\n")
        self.write("scripts/bad.sh", "if then fi\n")
        self.assertEqual(vl.grade("tools/good.py")["status"], "PASS")
        self.assertEqual(vl.grade("tools/bad.py")["status"], "FAIL")
        self.assertEqual(vl.grade("config/good.json")["status"], "PASS")
        self.assertEqual(vl.grade("config/bad.json")["status"], "FAIL")
        self.assertEqual(vl.grade("scripts/good.sh")["status"], "PASS")
        self.assertEqual(vl.grade("scripts/bad.sh")["status"], "FAIL")
        # A failing grader carries its output back so the harness can feed it to a fix step.
        self.assertTrue(vl.grade("tools/bad.py")["graders"][0]["detail"])

    def test_missing_and_unsupported_files_are_skipped_not_failed(self):
        self.assertEqual(vl.grade("tools/absent.py")["status"], "SKIP")
        self.write("notes.md", "# hi\n")
        self.assertEqual(vl.grade("notes.md")["status"], "SKIP")


if __name__ == "__main__":
    unittest.main()
