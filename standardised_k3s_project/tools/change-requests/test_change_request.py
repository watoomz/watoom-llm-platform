import json, os, pathlib, subprocess, tempfile, unittest
import change_request as cr


class T(unittest.TestCase):
    def setUp(self):
        self.t = pathlib.Path(tempfile.mkdtemp())
        self.repo = self.t / "repo"
        self.q = self.t / "q"
        self.q.mkdir()
        self.repo.mkdir()
        g = lambda *a: subprocess.run(
            ["git", "-C", str(self.repo), "-c", "user.name=t", "-c", "user.email=t@t", *a],
            check=True,
            capture_output=True,
        )
        g("init", "-q")
        (self.repo / "a.py").write_text("X=1\nY=2\n")
        (self.repo / "b.py").write_text("Z=3\n")
        g("add", ".")
        g("commit", "-qm", "init")
        self.p = {
            "repo": str(self.repo),
            "audit": str(self.t / "audit.jsonl"),
            "push": False,
            "queue_root": str(self.t),
            "queues": [str(self.q)],
            "limits": {"max_request_bytes": 65536, "max_text_bytes": 1000, "max_changed_lines": 4},
            "targets": {
                "a.py": {"checks": [["python3", "-c", "import ast,sys; ast.parse(open(sys.argv[1]).read())", "{file}"]]}
            },
        }

    def req(self, rid, **kw):
        v = {"schema": 1, "id": rid, "file": "a.py", "old": "X=1", "new": "X=2", "reason": "raise X"}
        v.update(kw)
        (self.q / (rid + ".json")).write_text(json.dumps(v))

    def status(self, rid):
        return json.loads((self.q / (rid + ".status.json")).read_text())

    def test_pending_then_approve_commits_only_target(self):
        (self.repo / "b.py").write_text("Z=99\n")
        self.req("r1")
        cr.scan(self.p)
        self.assertEqual(self.status("r1")["status"], "PENDING_APPROVAL")
        self.assertIn("+X=2", self.status("r1")["diff"])
        cr.approve(self.p, "r1", False)
        self.assertEqual((self.repo / "a.py").read_text(), "X=2\nY=2\n")
        self.assertEqual(self.status("r1")["status"], "APPLIED")
        self.assertEqual(
            subprocess.run(
                ["git", "-C", str(self.repo), "status", "--porcelain"], capture_output=True, text=True
            ).stdout.strip(),
            "M b.py",
        )

    def test_rejections(self):
        self.req("bad1", file="b.py")
        self.req("bad2", old="nope")
        self.req("bad3", extra=1)
        self.req("bad4", old="\n".join("l%d" % i for i in range(3)), new="q")
        cr.scan(self.p)
        for r in ("bad1", "bad2", "bad3", "bad4"):
            self.assertEqual(self.status(r)["status"], "REJECTED", r)
        self.assertIn("allowlist", self.status("bad1")["reason"])

    def test_failed_check_restores_file(self):
        self.req("syn", new="X=(")
        cr.scan(self.p)
        with self.assertRaises(SystemExit):
            cr.approve(self.p, "syn", False)
        self.assertEqual((self.repo / "a.py").read_text(), "X=1\nY=2\n")
        self.assertEqual(self.status("syn")["status"], "CHECK_FAILED")

    def test_stale_and_tamper_and_dirty(self):
        self.req("s1")
        cr.scan(self.p)
        (self.repo / "a.py").write_text("X=1\nY=3\n")
        with self.assertRaises(SystemExit):
            cr.approve(self.p, "s1", False)
        self.req("s2", old="Y=3", new="Y=4")
        subprocess.run(
            ["git", "-C", str(self.repo), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "y"],
            check=True,
            capture_output=True,
        )
        cr.scan(self.p)
        self.req("s2", old="Y=3", new="Y=5")
        with self.assertRaisesRegex(SystemExit, "changed after review"):
            cr.approve(self.p, "s2", False)

    def test_symlink_request_rejected(self):
        (self.q / "ln.json").symlink_to(self.t / "repo" / "a.py")
        cr.scan(self.p)
        self.assertEqual(self.status("ln")["status"], "REJECTED")

    def test_glob_discovery_ambiguity_and_symlinked_queue(self):
        for proj in ("g/one", "g/two"):
            d = self.t / proj / ".opencode" / "change-requests"
            d.mkdir(parents=True)
        (self.t / "g/one/.opencode/change-requests/dup.json").write_text(
            json.dumps({"schema": 1, "id": "dup", "file": "a.py", "old": "X=1", "new": "X=2", "reason": "r"})
        )
        (self.t / "g/two/.opencode/change-requests/dup.json").write_text(
            json.dumps({"schema": 1, "id": "dup", "file": "a.py", "old": "Y=2", "new": "Y=3", "reason": "r"})
        )
        evil = self.t / "g/three"
        (evil / ".opencode").mkdir(parents=True)
        (evil / ".opencode" / "change-requests").symlink_to(self.t / "elsewhere")
        (self.t / "elsewhere").mkdir()
        (self.t / "elsewhere/x.json").write_text("{}")
        self.p.update(queues=[], queue_globs=[str(self.t) + "/*/*/.opencode/change-requests"])
        self.assertEqual(cr.scan(self.p), 2)
        self.assertFalse((self.t / "elsewhere/x.status.json").exists())
        with self.assertRaisesRegex(SystemExit, "Ambiguous"):
            cr.find(self.p, "dup")
        cr.approve(self.p, "dup", False, "one")
        self.assertEqual((self.repo / "a.py").read_text(), "X=2\nY=2\n")

    def test_prefix_optional_and_whitespace_hint(self):
        self.p["targets"] = {"sub/a.py": {"checks": []}}
        (self.repo / "sub").mkdir()
        (self.repo / "sub/a.py").write_text("if x:\n    y=1\n")
        self.p["repo"] = str(self.repo)
        self.p["targets"] = {"standardised_k3s_project/a.py": {"checks": []}}
        (self.repo / "standardised_k3s_project").mkdir()
        (self.repo / "standardised_k3s_project/a.py").write_text("if x:\n    y=1\n")
        self.req("pre", file="a.py", old="    y=1", new="    y=2")
        self.req("ws", file="a.py", old="     y=1", new="     y=2")
        cr.scan(self.p)
        self.assertEqual(self.status("pre")["status"], "PENDING_APPROVAL")
        self.assertEqual(self.status("ws")["status"], "REJECTED")
        self.assertIn("Whitespace differs", self.status("ws")["reason"])

    def test_publish_and_glance_decisions(self):
        self.p["state_dir"] = str(self.t / "state")
        self.req("r1")
        self.req("r2", new="X=3")
        cr.scan(self.p)
        cr.publish(self.p)
        feed = json.loads((self.t / "state/requests.json").read_text())
        self.assertEqual(feed["pending"], 2)
        self.assertEqual(feed["requests"][0]["status"], "PENDING_APPROVAL")
        self.assertIn(
            "+X=2", feed["requests"][0]["diff"] if feed["requests"][0]["id"] == "r1" else feed["requests"][1]["diff"]
        )
        inbox = self.t / "state/decisions"
        inbox.mkdir()
        sha1 = self.status("r1")["request_sha256"]
        proj = self.q.parent.parent.name
        (inbox / "1.json").write_text(
            json.dumps({"action": "approve", "id": "r1", "project": proj, "request_sha256": "0" * 64})
        )  # stale hash
        (inbox / "2.json").write_text(
            json.dumps(
                {
                    "action": "reject",
                    "id": "r2",
                    "project": proj,
                    "request_sha256": self.status("r2")["request_sha256"],
                    "reason": "no",
                }
            )
        )
        (inbox / "3.json").write_text("{not json")
        errs = cr.decisions(self.p)
        self.assertEqual(len(errs), 2)
        self.assertEqual(self.status("r1")["status"], "PENDING_APPROVAL")
        self.assertEqual(self.status("r2")["status"], "REJECTED")
        self.assertEqual(list(inbox.glob("*.json")), [])
        (inbox / "4.json").write_text(
            json.dumps({"action": "approve", "id": "r1", "project": proj, "request_sha256": sha1})
        )
        self.assertEqual(cr.decisions(self.p), [])
        self.assertEqual(self.status("r1")["status"], "APPLIED")
        self.assertEqual((self.repo / "a.py").read_text(), "X=2\nY=2\n")

    def test_unexpected_apply_failure_is_reported_and_kept(self):
        self.p["state_dir"] = str(self.t / "state")
        self.req("r1")
        cr.scan(self.p)
        proj = self.q.parent.parent.name
        inbox = self.t / "state/decisions"
        inbox.mkdir(parents=True)
        (inbox / "1.json").write_text(
            json.dumps(
                {
                    "action": "approve",
                    "id": "r1",
                    "project": proj,
                    "request_sha256": self.status("r1")["request_sha256"],
                }
            )
        )
        self.p["repo"] = str(self.t / "missing-repo")  # git cannot run there
        errs = cr.decisions(self.p)
        self.assertEqual(len(errs), 1)
        self.assertIn("r1", errs[0]["id"])
        cr.publish(self.p, errs)
        self.assertEqual(self.status("r1")["status"], "PENDING_APPROVAL")
        cr.publish(self.p, [])
        feed = json.loads((self.t / "state/requests.json").read_text())
        self.assertEqual(len(feed["errors"]), 1)


if __name__ == "__main__":
    unittest.main()
