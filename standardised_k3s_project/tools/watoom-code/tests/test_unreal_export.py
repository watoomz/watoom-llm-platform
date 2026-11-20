import json, os, pathlib, subprocess, sys, tempfile, unittest
from unittest.mock import patch

HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import game_unreal_export as helper
import game_worker_bridge as bridge
import unreal_export_spec as spec

GAMES = pathlib.Path("/data/ai/projects/games")


class UnrealExport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.packs = pathlib.Path(self.tmp.name) / "fab"
        (self.packs / "wolf-pack/Content").mkdir(parents=True)
        self.project = pathlib.Path(tempfile.mkdtemp(prefix=".unreal-export-test-", dir=GAMES))
        (self.project / ".opencode").mkdir()
        patch.object(spec, "PACKS", self.packs).start()
        self.addCleanup(patch.stopall)

    def tearDown(self):
        (
            subprocess.run(["rm", "-rf", "--", str(self.project)], check=True)
            if self.project.name.startswith(".unreal-export-test-")
            else None
        )
        self.tmp.cleanup()

    def write(self, value, job="wolf"):
        d = self.project / ".opencode/unreal-export-jobs" / job
        d.mkdir(parents=True, exist_ok=True)
        (d / "request.json").write_text(value if isinstance(value, str) else json.dumps(value))

    good = {
        "schema": 1,
        "pack": "wolf-pack",
        "root": "/Game/Wolf",
        "classes": ["SkeletalMesh", "AnimSequence"],
        "include": ["Wolf"],
    }

    def test_valid_manifest_and_defaults(self):
        self.write(self.good)
        v = spec.load(self.project, "wolf")
        self.assertEqual((v["max_assets"], v["memory_gib"], v["exclude"]), (400, 4, None))

    def test_errors_name_the_field(self):
        for bad, field in [
            ({**self.good, "pack": "../etc"}, "pack"),
            ({**self.good, "pack": "missing"}, "pack"),
            ({**self.good, "root": "/Game/Wolf/"}, "root"),
            ({**self.good, "root": "/Game/../x"}, "root"),
            ({**self.good, "classes": ["Blueprint"]}, "classes"),
            ({**self.good, "include": ["a,b"]}, "include"),
            ({**self.good, "max_assets": 0}, "max_assets"),
            ({**self.good, "memory_gib": True}, "memory_gib"),
            ({**self.good, "out": "/etc"}, "unknown fields"),
            ("{", "not valid JSON"),
        ]:
            self.write(bad)
            with self.assertRaisesRegex(ValueError, field):
                spec.load(self.project, "wolf")

    def test_dispatcher_fails_only_the_bad_request(self):
        self.write({**self.good, "classes": []})
        v = {"operation": "unreal-export", "job": "wolf"}
        current, reason = bridge.checked_fingerprint(self.project, v)
        self.assertIsNone(current)
        self.assertIn(".opencode/unreal-export-jobs/wolf/request.json", reason)
        self.assertIn("classes", reason)

    def test_guard_and_dispatcher_fingerprints_agree_and_ignore_game_source(self):
        self.write(self.good)
        guard = HERE.parent.parent / "ansible/roles/watoom-code/files/coordinator-guard/index.js"
        js = subprocess.check_output(
            [
                "node",
                "--input-type=module",
                "-e",
                'const m=await import(process.argv[1]);console.log(await m.unrealExportSpecFingerprint(process.argv[2],"wolf"))',
                str(guard),
                str(self.project),
            ],
            text=True,
        ).strip()
        before = bridge.request_fingerprint(self.project, {"operation": "unreal-export", "job": "wolf"})
        (self.project / "main.gd").write_text("extends Node")
        self.assertEqual(js, before)
        self.assertEqual(
            before, bridge.request_fingerprint(self.project, {"operation": "unreal-export", "job": "wolf"})
        )

    def run_helper(self, result, code=0):
        outs = pathlib.Path(self.tmp.name) / "outs"
        outs.mkdir(exist_ok=True)

        def fake(cmd, **kw):
            out = pathlib.Path(cmd[cmd.index("--out") + 1])
            (out / "exported/Wolf").mkdir(parents=True)
            (out / "exported/Wolf/SK_Wolf.glb").write_bytes(b"glTF")
            os.symlink("/etc/hosts", out / "exported/escape")
            (out / "result.json").write_text(json.dumps(result))
            return subprocess.CompletedProcess(cmd, code)

        evidence = pathlib.Path(tempfile.mkdtemp(dir=self.tmp.name)) / os.urandom(32).hex()
        argv = ["x", "--project", str(self.project), "--evidence", str(evidence), "--i-approve", "--export-job", "wolf"]
        with patch.object(helper, "OUTS", outs), patch.object(helper.subprocess, "run", fake), patch.object(
            sys, "argv", argv
        ), patch("builtins.print"):
            with self.assertRaises(SystemExit) as e:
                helper.main()
        return e.exception.code, json.loads((evidence / "result.json").read_text())

    def test_pass_copies_regular_files_into_the_project(self):
        self.write(self.good)
        code, r = self.run_helper(
            {
                "status": "PORTABLE_EXPORT_PASS",
                "counts": {"SkeletalMesh": 1},
                "failed": [],
                "source_unchanged": True,
                "exported": [
                    {"path": "/Game/Wolf/SK_Wolf", "class": "SkeletalMesh", "file": "exported/Wolf/SK_Wolf.glb"}
                ],
            }
        )
        target = self.project / ".opencode/unreal-exports/wolf"
        self.assertEqual((code, r["status"]), (0, "PASS"))
        self.assertEqual((target / "Wolf/SK_Wolf.glb").read_bytes(), b"glTF")
        self.assertFalse((target / "escape").exists(), "links from the worker are never copied")
        self.assertEqual(r["exported"][0]["file"], ".opencode/unreal-exports/wolf/Wolf/SK_Wolf.glb")
        code, r = self.run_helper({"status": "PORTABLE_EXPORT_PASS"})
        self.assertEqual((code, r["status"]), (1, "FAIL"))
        self.assertIn("new job name", r["failure_reason"])

    def test_export_failure_is_reported(self):
        self.write(self.good)
        code, r = self.run_helper({"status": "FAIL", "reason": "Unreal worker did not finish successfully"}, 1)
        self.assertEqual((code, r["status"]), (1, "FAIL"))
        self.assertIn("did not finish", r["failure_reason"])
        self.assertFalse((self.project / ".opencode/unreal-exports/wolf").exists())


if __name__ == "__main__":
    unittest.main()
