import json, pathlib, subprocess, sys, tempfile, unittest
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import memory_curator as mc

AGENT = "codex@agent.example"
OWNER = "garthcordery@gmail.com"


def git(repo, *args, email=None, name="t"):
    env = {"GIT_AUTHOR_NAME": name, "GIT_COMMITTER_NAME": name}
    if email:
        env.update(GIT_AUTHOR_EMAIL=email, GIT_COMMITTER_EMAIL=email)
    subprocess.run(["git", "-C", str(repo), *args], check=True, env={**_base_env(), **env},
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _base_env():
    import os
    return {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}


class Curator(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = pathlib.Path(self.tmp.name)
        self.store = self.base / "learn" / "lessons.sqlite"
        self.repo = self.base / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        # agent authors a file, then the owner (different email) revises it
        (self.repo / "role.yml").write_text("key: original\n")
        git(self.repo, "add", "role.yml")
        git(self.repo, "commit", "-qm", "agent adds role", email=AGENT)
        (self.repo / "role.yml").write_text("key: owner-corrected\n")
        git(self.repo, "add", "role.yml")
        git(self.repo, "commit", "-qm", "owner fixes role", email=OWNER)

    def db(self):
        return mc.connect(self.store.resolve())

    def test_owner_fix_becomes_an_active_procedural_lesson_and_rolls_back(self):
        db = self.db()
        result = mc.curate(db, self.store.parent, self.repo, None, (OWNER,), (AGENT,), 3650, apply=True)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["inserted"], 1)
        self.assertEqual(mc.summary(db)["by_kind"]["procedural"], 1)
        # recall finds it and bumps the usage counter
        found = mc.recall(db, "owner revised", 10)
        self.assertEqual(len(found), 1)
        self.assertIn("owner-corrected", found[0]["fix"])
        # rollback reverts the whole transaction
        mc.rollback(db, result["txn"])
        self.assertEqual(mc.summary(db)["total"], 0)
        db.close()

    def test_kill_switch_makes_curate_a_noop(self):
        (self.store.parent).mkdir(parents=True, exist_ok=True)
        (self.store.parent / "curator-disabled").write_text("off")
        db = self.db()
        result = mc.curate(db, self.store.parent, self.repo, None, (OWNER,), (AGENT,), 3650, apply=True)
        self.assertEqual(result["status"], "DISABLED")
        self.assertFalse(result["applied"])
        self.assertEqual(mc.summary(db)["total"], 0)
        db.close()

    def test_dry_run_writes_nothing(self):
        db = self.db()
        result = mc.curate(db, self.store.parent, self.repo, None, (OWNER,), (AGENT,), 3650, apply=False)
        self.assertFalse(result["applied"])
        self.assertGreaterEqual(result["candidates"], 1)
        self.assertEqual(mc.summary(db)["total"], 0)
        db.close()

    def test_verification_failures_ingest_as_episodic_pending(self):
        ev = self.base / "evidence" / "run1"
        ev.mkdir(parents=True)
        (ev / "verification.json").write_text(json.dumps({
            "status": "FAIL",
            "files": [{"file": "a.yml", "status": "FAIL",
                       "graders": [{"grader": "ansible-lint", "status": "FAIL", "detail": "line too long"}]}],
        }))
        db = self.db()
        result = mc.curate(db, self.store.parent, None, str(self.base / "evidence"), (OWNER,), (AGENT,), 30, apply=True)
        self.assertEqual(result["inserted"], 1)
        self.assertEqual(mc.summary(db)["by_kind"]["episodic"], 1)
        self.assertEqual(mc.summary(db)["by_status"].get("pending"), 1)
        db.close()

    def _chat_db(self, rows):
        import sqlite3, time as _t
        path = self.base / "app.sqlite"
        db = sqlite3.connect(path)
        db.execute("CREATE TABLE session_v2(id TEXT, title TEXT, agent TEXT)")
        db.execute("CREATE TABLE session_message(id TEXT, session_id TEXT, type TEXT, data TEXT, time_created INTEGER)")
        db.execute("INSERT INTO session_v2 VALUES('s1','Zombie game','watoom-workflow')")
        now = int(_t.time() * 1000)
        for i, (kind, data) in enumerate(rows):
            db.execute("INSERT INTO session_message VALUES(?,?,?,?,?)", ("m%d" % i, "s1", kind, json.dumps(data), now - i))
        db.commit(); db.close()
        return path

    def test_only_marked_chat_lines_become_lessons_and_secrets_system_text_do_not(self):
        rule = "Never fix engine API errors from memory; verify them against the docs first."
        path = self._chat_db([
            ("user", {"metadata": {"displayText": "Build the sky now.\n+ " + rule + "\n+ short", "agent": "watoom-workflow"}}),
            ("user", {"metadata": {"displayText": "Never do this unmarked rule that is long enough to matter"}}),
            ("user", {"metadata": {"displayText": "+ use token=abcd1234abcd1234 for the upload every time"}}),
            ("user", {"metadata": {"displayText": "++ doubled marker is not a lesson line at all"}}),
            ("user", {"text": "+ system dispatch text without displayText is ignored entirely"}),
            ("system", {"metadata": {"displayText": "+ system message type is ignored entirely too"}}),
        ])
        lessons = mc.owner_chat_lessons(path, 30)
        self.assertEqual([l["fix"] for l in lessons], [rule])
        self.assertEqual(lessons[0]["kind"], "procedural")
        self.assertIn("Zombie game", lessons[0]["problem"])
        self.assertEqual(mc.owner_chat_lessons(path, 30, marker="!"), [])
        db = self.db()
        r = mc.curate(db, self.store.parent, None, None, (OWNER,), (AGENT,), 30, True, str(path))
        self.assertEqual(r["inserted"], 1)
        again = mc.curate(db, self.store.parent, None, None, (OWNER,), (AGENT,), 30, True, str(path))
        self.assertEqual((again["inserted"], again["already_present"]), (0, 1))
        self.assertEqual(mc.rollback(db, r["txn"])["status"], "ROLLED_BACK")
        self.assertEqual(mc.summary(db)["total"], 0)
        self.assertEqual(mc.owner_chat_lessons(self.base / "missing.sqlite", 30), [])

    def _critic_db(self, sessions):
        """sessions: list of (session_id, title, [(finish, text), ...] final-to-first not required, any order)."""
        import sqlite3, time as _t
        path = self.base / "critic.sqlite"
        db = sqlite3.connect(path)
        db.execute("CREATE TABLE session_v2(id TEXT, title TEXT, agent TEXT)")
        db.execute("CREATE TABLE session_message(id TEXT, session_id TEXT, type TEXT, data TEXT, time_created INTEGER)")
        now = int(_t.time() * 1000)
        mid = 0
        for session_id, title, turns in sessions:
            db.execute("INSERT INTO session_v2 VALUES(?,?,?)", (session_id, title, "watoom-critic"))
            for i, (finish, text) in enumerate(turns):
                data = {"finish": finish, "content": [{"type": "text", "text": text}]}
                db.execute("INSERT INTO session_message VALUES(?,?,?,?,?)",
                          ("m%d" % mid, session_id, "assistant", json.dumps(data), now + mid))
                mid += 1
        db.commit(); db.close()
        return path

    def test_critic_revise_becomes_pending_incident_and_proceed_does_not(self):
        path = self._critic_db([
            ("s1", "Diagnose ESP32 build failures", [
                ("tool-calls", "investigating..."),  # earlier turn, ignored even though it has no DECISION=
                ("stop", "DECISION=REVISE\nCRITICAL_FINDING=worker double-nests sources under sketch/src/src\n"
                         "ONE_BEST_NEXT_ACTION=flatten compiled sources into the sketch root"),
            ]),
            ("s2", "Check capture-scene manifest", [
                ("stop", "DECISION=PROCEED\nCRITICAL_FINDING=no issue found"),
            ]),
            ("s3", "Cut off mid-reasoning", [
                ("tool-calls", "DECISION=REVISE\nCRITICAL_FINDING=this never finished, must not count"),
            ]),
        ])
        lessons = mc.critic_fix_lessons(path, 30)
        self.assertEqual(len(lessons), 1)
        lesson = lessons[0]
        self.assertEqual(lesson["kind"], "episodic")
        self.assertEqual(lesson["status"], "pending")
        self.assertIn("sketch/src/src", lesson["fix"])
        self.assertIn("flatten compiled sources", lesson["fix"])
        self.assertIn("ESP32 build failures", lesson["problem"])
        self.assertEqual(mc.critic_fix_lessons(self.base / "missing.sqlite", 30), [])

    def test_critic_lessons_insert_as_pending_through_curate_and_roll_back(self):
        path = self._critic_db([("s1", "Diagnose", [("stop", "DECISION=REVISE\nCRITICAL_FINDING=real bug found")])])
        db = self.db()
        r = mc.curate(db, self.store.parent, None, None, (OWNER,), (AGENT,), 30, True, str(path))
        self.assertEqual(r["inserted"], 1)
        self.assertEqual(mc.summary(db)["by_status"].get("pending"), 1)
        again = mc.curate(db, self.store.parent, None, None, (OWNER,), (AGENT,), 30, True, str(path))
        self.assertEqual((again["inserted"], again["already_present"]), (0, 1))
        self.assertEqual(mc.rollback(db, r["txn"])["status"], "ROLLED_BACK")
        self.assertEqual(mc.summary(db)["total"], 0)

    def test_engine_api_errors_become_versioned_facts_and_project_bugs_do_not(self):
        import os, time as _t
        rc = self.base / "receipts"; rc.mkdir()
        tc = self.base / "godot" / "4.7.2"; tc.mkdir(parents=True)
        (self.base / "godot" / "latest").mkdir()  # non-numeric directory is not a version
        def receipt(name, errors, age=0):
            f = rc / (name + ".operator.log")
            f.write_text(json.dumps({"status": "FAIL", "errors": errors}) + "\n")
            os.utime(f, (_t.time() - age, _t.time() - age))
        receipt("a", ["SCRIPT ERROR: Invalid assignment of property or key 'sun_elevation' with value of type 'float' on a base object of type 'ProceduralSkyMaterial'. [at: x.gd:22]",
                      "SCRIPT ERROR: Invalid call. Nonexistent function 'store_text' in base 'FileAccess'.",
                      "SCRIPT ERROR: Invalid access to property or key 'amp' on a base object of type 'Dictionary'.",
                      "SCRIPT ERROR: Invalid call. Nonexistent function 'make_current' in base 'Nil'.",
                      "SCRIPT ERROR: Invalid access to property or key 'hp' on a base object of type 'Node3D (player.gd)'.",
                      "SCRIPT ERROR: Trying to assign invalid previously freed instance."])
        receipt("b", ["SCRIPT ERROR: Invalid assignment of property or key 'sun_elevation' with value of type 'float' on a base object of type 'ProceduralSkyMaterial'."])
        self.assertEqual(mc.toolchain_version(self.base / "godot"), "4.7.2")
        lessons = mc.engine_error_lessons(rc, "godot", "4.7.2", 30)
        self.assertEqual(sorted(l["meta"]["member"] for l in lessons), ["store_text", "sun_elevation"])
        sky = [l for l in lessons if l["meta"]["member"] == "sun_elevation"][0]
        self.assertEqual((sky["kind"], sky["status"], sky["meta"]["class"], sky["meta"]["version"]), ("semantic", "active", "ProceduralSkyMaterial", "4.7.2"))
        self.assertIn("4.7.2", sky["problem"])
        # receipts older than the installed engine are not attributed to it
        self.assertEqual(mc.engine_error_lessons(rc, "godot", "4.7.2", 30, not_before=_t.time() + 60), [])
        self.assertEqual(mc.engine_error_lessons(rc, "godot", None, 30), [])
        db = self.db()
        out = self.base / "out" / "recall.json"
        r = mc.curate(db, self.store.parent, None, None, (OWNER,), (AGENT,), 30, True, None, "+", str(rc), "4.7.2", str(out))
        self.assertEqual((r["inserted"], r["exported"]), (2, {"engine": 2, "owner": 0}))
        data = json.loads(out.read_text())
        self.assertEqual({e["member"] for e in data["engine"]}, {"sun_elevation", "store_text"})
        self.assertEqual(oct(out.stat().st_mode & 0o777), "0o644")
        self.assertEqual(mc.rollback(db, r["txn"])["status"], "ROLLED_BACK")
        self.assertEqual(mc.summary(db)["total"], 0)

    def _fail(self, evidence_root, run, file, grader, detail="boom"):
        ev = evidence_root / run
        ev.mkdir(parents=True, exist_ok=True)
        (ev / "verification.json").write_text(json.dumps({
            "status": "FAIL",
            "files": [{"file": file, "status": "FAIL", "graders": [{"grader": grader, "status": "FAIL", "detail": detail}]}],
        }))

    def test_a_grader_recurring_across_distinct_files_becomes_one_auto_applied_pattern_lesson(self):
        # pattern_lessons() reads already-COMMITTED episodic incidents, so it sees this run's 3 new incidents only
        # on the NEXT curate() call (the same one-cycle lag the real 15-minute timer has) — not within the run
        # that is still inserting them.
        evidence_root = self.base / "evidence"
        for i, f in enumerate(["a.gd", "b.gd", "c.gd"]):
            self._fail(evidence_root, "run%d" % i, f, "null-safety", detail="boom %d" % i)
        db = self.db()
        r1 = mc.curate(db, self.store.parent, None, str(evidence_root), (OWNER,), (AGENT,), 30, apply=True)
        self.assertEqual(r1["inserted"], 3)
        self.assertEqual(r1["pattern_candidates"], 0)  # not yet visible to this same run
        r2 = mc.curate(db, self.store.parent, None, str(evidence_root), (OWNER,), (AGENT,), 30, apply=True)
        self.assertEqual(r2["inserted"], 1)  # the pattern lesson, now that the 3 incidents are committed
        self.assertEqual(r2["pattern_candidates"], 1)
        pattern = [l for l in db.execute("SELECT kind,problem,fix,status,source,meta FROM lessons WHERE source LIKE 'pattern:%'").fetchall()]
        self.assertEqual(len(pattern), 1)
        kind, problem, fix, status, source, meta = pattern[0]
        self.assertEqual((kind, status), ("procedural", "active"))  # auto-applied immediately, no extra gate
        self.assertIn("null-safety", problem)
        self.assertIn("3", problem)
        self.assertEqual(json.loads(meta)["occurrences"], 3)
        self.assertEqual(sorted(json.loads(meta)["files"]), ["a.gd", "b.gd", "c.gd"])
        # it is findable through the normal recall path like any other active lesson
        found = mc.recall(db, "null-safety", 10)
        self.assertTrue(any(l["source"] == source for l in found))
        # a third curate() run with no new incidents makes no new pattern lesson (same key, already present)
        r3 = mc.curate(db, self.store.parent, None, str(evidence_root), (OWNER,), (AGENT,), 30, apply=True)
        self.assertEqual(r3["inserted"], 0)
        self.assertEqual(mc.summary(db)["by_kind"]["procedural"], 1)
        db.close()

    def test_below_the_occurrence_threshold_no_pattern_lesson_is_ever_written(self):
        evidence_root = self.base / "evidence"
        self._fail(evidence_root, "run0", "a.gd", "rare-check")
        self._fail(evidence_root, "run1", "b.gd", "rare-check")
        db = self.db()
        mc.curate(db, self.store.parent, None, str(evidence_root), (OWNER,), (AGENT,), 30, apply=True)
        r = mc.curate(db, self.store.parent, None, str(evidence_root), (OWNER,), (AGENT,), 30, apply=True)
        self.assertEqual(r["pattern_candidates"], 0)
        self.assertEqual(mc.summary(db)["by_kind"].get("procedural", 0), 0)
        db.close()

    def test_higher_occurrence_threshold_is_respected_even_once_incidents_are_committed(self):
        evidence_root = self.base / "evidence"
        for i, f in enumerate(["a.gd", "b.gd", "c.gd"]):
            self._fail(evidence_root, "run%d" % i, f, "null-safety")
        db = self.db()
        mc.curate(db, self.store.parent, None, str(evidence_root), (OWNER,), (AGENT,), 30, apply=True)
        r = mc.curate(db, self.store.parent, None, str(evidence_root), (OWNER,), (AGENT,), 30, apply=True,
                      pattern_min_occurrences=4)
        self.assertEqual(r["pattern_candidates"], 0)  # 3 committed incidents, threshold raised to 4
        db.close()

    def test_repeated_failures_on_the_same_file_still_count_toward_the_threshold(self):
        # pattern_lessons groups by grader name and reports distinct FILES in its meta; three incidents on the
        # same grader but spread across only two distinct files still recur (occurrence count is per-incident,
        # not per-file), but the files list in meta must reflect the true distinct count.
        evidence_root = self.base / "evidence"
        self._fail(evidence_root, "run0", "a.gd", "null-safety", detail="first")
        self._fail(evidence_root, "run1", "a.gd", "null-safety", detail="second")
        self._fail(evidence_root, "run2", "b.gd", "null-safety", detail="third")
        db = self.db()
        mc.curate(db, self.store.parent, None, str(evidence_root), (OWNER,), (AGENT,), 30, apply=True)
        r = mc.curate(db, self.store.parent, None, str(evidence_root), (OWNER,), (AGENT,), 30, apply=True)
        self.assertEqual(r["pattern_candidates"], 1)
        meta = json.loads(db.execute("SELECT meta FROM lessons WHERE source LIKE 'pattern:%'").fetchone()[0])
        self.assertEqual(meta["occurrences"], 3)
        self.assertEqual(sorted(meta["files"]), ["a.gd", "b.gd"])
        db.close()

    def test_two_curate_calls_in_the_same_second_get_different_rollback_transactions(self):
        # Regression: txn ids used to be a hash of whole-second time, so two calls within the same second
        # collided and rolling back one silently undid the other too.
        evidence_root = self.base / "evidence"
        self._fail(evidence_root, "run0", "a.gd", "x")
        db = self.db()
        r1 = mc.curate(db, self.store.parent, None, str(evidence_root), (OWNER,), (AGENT,), 30, apply=True)
        r2 = mc.curate(db, self.store.parent, None, str(evidence_root), (OWNER,), (AGENT,), 30, apply=True)
        self.assertNotEqual(r1["txn"], r2["txn"])
        db.close()

    def test_rolling_back_a_pattern_lesson_leaves_the_underlying_episodic_incidents_alone(self):
        evidence_root = self.base / "evidence"
        for i, f in enumerate(["a.gd", "b.gd", "c.gd"]):
            self._fail(evidence_root, "run%d" % i, f, "null-safety")
        db = self.db()
        mc.curate(db, self.store.parent, None, str(evidence_root), (OWNER,), (AGENT,), 30, apply=True)
        r = mc.curate(db, self.store.parent, None, str(evidence_root), (OWNER,), (AGENT,), 30, apply=True)
        self.assertEqual(mc.summary(db)["by_kind"]["episodic"], 3)
        self.assertEqual(mc.summary(db)["by_kind"]["procedural"], 1)
        mc.rollback(db, r["txn"])  # rolls back only the 2nd transaction (the pattern lesson)
        self.assertEqual(mc.summary(db)["by_kind"]["episodic"], 3)  # untouched
        self.assertEqual(mc.summary(db)["by_kind"].get("procedural", 0), 0)
        db.close()


if __name__ == "__main__":
    unittest.main()
