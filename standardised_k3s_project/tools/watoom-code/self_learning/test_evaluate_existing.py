import unittest, copy
from evaluate_existing import validate_report


class Evaluation(unittest.TestCase):
    def fixture(self):
        suite = {"id": "fixed-cpu-v1", "sha256": "a" * 64, "caseIDs": ["representative", "regression"]}
        cases = []
        for cid in suite["caseIDs"]:
            arms = {}
            for arm, tokens in [("original", 100), ("candidate", 90)]:
                arms[arm] = {
                    "correctness": True,
                    "safety": True,
                    "coverage": ["output", "permissions"],
                    "tokens": tokens,
                    "runs": [
                        {
                            "receipt": cid + arm + str(i),
                            "correctness": True,
                            "safety": True,
                            "coverage": ["output", "permissions"],
                            "tokens": tokens,
                        }
                        for i in range(3)
                    ],
                }
            cases.append({"id": cid, **arms})
        report = {
            "baseline": {"hash": "old", "cases": [{"id": c} for c in suite["caseIDs"]]},
            "comparison": {"baselineHash": "old", "candidateHash": "new", "cases": cases},
        }
        return suite, report

    def test_three_real_replay_records_per_arm(self):
        suite, r = self.fixture()
        _, comparison = validate_report(r, suite, "old", "new")
        self.assertEqual(len(comparison["measurementProtocol"]["verifierReceipts"]), 12)

    def test_missing_case_duplicate_receipt_or_wrong_median_rejected(self):
        for mutate in [
            lambda r: r["comparison"]["cases"].pop(),
            lambda r: r["comparison"]["cases"][0]["candidate"]["runs"].pop(),
            lambda r: r["comparison"]["cases"][0]["candidate"].update(tokens=1),
            lambda r: r["comparison"]["cases"][0]["candidate"]["runs"][0].update(receipt="representativeoriginal0"),
        ]:
            suite, r = self.fixture()
            mutate(r)
            with self.assertRaises(ValueError):
                validate_report(r, suite, "old", "new")

    def test_failed_candidate_never_promoted(self):
        suite, r = self.fixture()
        r["comparison"]["cases"][0]["candidate"]["runs"][0]["correctness"] = False
        with self.assertRaises(ValueError):
            validate_report(r, suite, "old", "new")

    def test_hash_mismatch_rejected(self):
        suite, r = self.fixture()
        with self.assertRaises(ValueError):
            validate_report(r, suite, "changed", "new")


class QueueRecovery(unittest.TestCase):
    def test_stale_first_item_does_not_starve_next_and_worker_uses_journal(self):
        import tempfile, pathlib, json, sqlite3, hashlib, sys, types, subprocess
        from unittest.mock import patch
        from evaluate_existing import evaluate_pending

        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            base = root / "existing-skills"
            base.mkdir()
            suites = base / "suites"
            suites.mkdir()
            script = suites / "suite.py"
            script.write_text('print("bounded evaluator")')
            digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
            suite = {
                "id": "domain-fixture",
                "script": str(script),
                "sha256": digest(script),
                "caseIDs": ["routing"],
                "domainRepresentative": True,
            }
            (base / "evaluator-registry.json").write_text(json.dumps({"suites": {"missing": suite, "present": suite}}))
            data = root / "data"
            (data / "skills").mkdir(parents=True)
            (data / "skills/old.md").write_text("old")
            (data / "skills/new.md").write_text("new")
            scope = {"project": "p", "repository": "/project", "agent": "a"}
            revisions = {
                "old": {
                    "id": "old",
                    "skill": "present",
                    "sha256": digest(data / "skills/old.md"),
                    "path": "/skills/old.md",
                    "state": "baseline",
                },
                "stale": {"id": "stale", "skill": "missing", "previous": "old", "state": "candidate"},
                "fresh": {
                    "id": "fresh",
                    "skill": "present",
                    "previous": "old",
                    "state": "candidate",
                    "path": "/skills/new.md",
                    "sha256": digest(data / "skills/new.md"),
                },
            }
            state = {
                "scope": scope,
                "skills": {
                    "missing": {"baseline": "old"},
                    "present": {"baseline": "old", "sha256": revisions["old"]["sha256"]},
                },
                "revisions": revisions,
            }
            database = root / "db.sqlite"
            db = sqlite3.connect(database)
            db.execute("CREATE TABLE kv(key TEXT,value TEXT)")
            scopehash = hashlib.sha256(json.dumps(scope, separators=(",", ":")).encode()).hexdigest()
            db.execute("INSERT INTO kv VALUES (?,?)", ("optimisation/v1/" + scopehash, json.dumps(state)))
            db.commit()
            db.close()
            calls = []

            class Maintenance:
                def __init__(self, *a):
                    pass

                def request(self, url):
                    self_url = url
                    assert "directory=%2Fproject" in url
                    return {"data": [{"id": "present", "content": "old"}]}

            def run(argv, **kw):
                calls.append(argv)
                return subprocess.CompletedProcess(
                    argv, 1 if argv[0] == "systemd-run" else 0, b"", b"worker fixture failure"
                )

            with patch.dict(sys.modules, {"maintenance_guard": types.SimpleNamespace(Maintenance=Maintenance)}), patch(
                "evaluate_existing.subprocess.run", run
            ):
                result = evaluate_pending(
                    root,
                    [state],
                    {"namespace": "test", "deployment": "test", "data_root": str(data), "evaluations": str(root)},
                    database,
                )
            self.assertEqual(result["revision"], "fresh")
            self.assertEqual(result["status"], "FAIL")
            worker = next(c for c in calls if c[0] == "systemd-run")
            self.assertNotIn("--pipe", worker)
            self.assertIn("StandardOutput=journal", worker)

    def test_generic_contracts_remain_pending_without_execution(self):
        import tempfile, pathlib, json
        from unittest.mock import patch
        from evaluate_existing import evaluate_pending

        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            base = root / "existing-skills"
            base.mkdir()
            (base / "evaluator-registry.json").write_text(
                json.dumps({"suites": {"generic": {"domainRepresentative": False}}})
            )
            state = {
                "skills": {"generic": {"baseline": "old"}},
                "revisions": {"r": {"id": "r", "skill": "generic", "state": "candidate", "previous": "old"}},
            }
            with patch("evaluate_existing.subprocess.run") as run:
                result = evaluate_pending(root, [state], {}, root / "unused")
            self.assertEqual(result["domainSuitesPending"], ["generic"])
            run.assert_not_called()
