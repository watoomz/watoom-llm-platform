import json, pathlib, sqlite3, sys, tempfile, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import memory_outbox

SCOPE = {"project": "p" * 40, "repository": "/workspace", "agent": "watoom-builder"}
SCHEMA = """CREATE TABLE _watoom_outbox(id text PRIMARY KEY, scope text NOT NULL, job text NOT NULL, seq integer NOT NULL,
  digest text NOT NULL, body text NOT NULL, checkpoint_body text NOT NULL, state text NOT NULL, attempts integer DEFAULT 0 NOT NULL,
  last_error text, receipt text, time_created integer, time_attempted integer, time_observed integer,
  CHECK(state IN ('pending','sending','uncertain','observed')))"""

def body(n):
    return {"scope": SCOPE, "job": "ses_x:evt_y", "seq": n, "kind": "event", "content": {"n": n}, "version": 2,
            "id": "%064x" % n, "digest": "%064x" % (n + 1000)}

def hit(b, memory_id="mem_1"):
    return {"observation": {"id": memory_id, "narrative": json.dumps(b)}}

class MemoryOutboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.path = pathlib.Path(self.tmp.name) / "app.sqlite"
        self.db = sqlite3.connect(self.path, isolation_level=None); self.db.execute(SCHEMA); self.db.row_factory = sqlite3.Row
    def tearDown(self):
        self.db.close(); self.tmp.cleanup()
    def add(self, n, state="uncertain", attempted=0):
        b = body(n)
        self.db.execute("INSERT INTO _watoom_outbox(id,scope,job,seq,digest,body,checkpoint_body,state,attempts,last_error,time_attempted) VALUES(?,?,?,?,?,?,?,?,1,'ambiguous acknowledgment',?)",
                        (b["id"], memory_outbox.canonical_scope(SCOPE), b["job"], n, b["digest"], json.dumps(b), "{}", state, attempted))
        return b
    def row(self, b):
        return self.db.execute("SELECT * FROM _watoom_outbox WHERE id=?", (b["id"],)).fetchone()

    def test_exact_envelope_is_found_and_receipt_matches_client_format(self):
        b = self.add(1)
        outcome, receipt = memory_outbox.classify(b, lambda q: {"results": [hit(b)]})
        self.assertEqual(outcome, "found")
        self.assertEqual(list(receipt), ["id", "digest", "scope", "memoryId", "durability"])
        self.assertTrue(memory_outbox.apply(self.db, self.row(b), outcome, receipt, 5))
        r = self.row(b)
        self.assertEqual((r["state"], r["last_error"], r["time_observed"]), ("observed", None, 5))
        self.assertEqual(json.loads(r["receipt"])["memoryId"], "mem_1")

    def test_lookalikes_are_not_accepted(self):
        b = self.add(1)
        other = dict(b, content={"n": 2})
        bad = [hit(other), {"observation": {"id": "bad id!", "narrative": json.dumps(b)}},
               {"observation": {"id": "m", "narrative": "x" * 13000}}, {"observation": {"id": "m"}}, {}]
        self.assertEqual(memory_outbox.classify(b, lambda q: {"results": bad}), ("absent", None))

    def test_absence_requires_both_id_and_digest_searches(self):
        b = self.add(1); queries = []
        def search(q):
            queries.append(q["query"]); return {"results": [hit(b)] if q["query"] == b["digest"] else []}
        self.assertEqual(memory_outbox.classify(b, search)[0], "found")
        self.assertEqual(queries, [b["id"], b["digest"]])

    def test_absent_item_is_requeued_without_touching_other_fields(self):
        b = self.add(1)
        self.assertTrue(memory_outbox.apply(self.db, self.row(b), "absent", None, 5))
        r = self.row(b)
        self.assertEqual((r["state"], r["last_error"], r["attempts"], r["receipt"]), ("pending", None, 1, None))

    def test_concurrent_client_change_is_left_alone(self):
        b = self.add(1); stale = self.row(b)
        self.db.execute("UPDATE _watoom_outbox SET state='observed' WHERE id=?", (b["id"],))
        self.assertFalse(memory_outbox.apply(self.db, stale, "absent", None, 5))
        self.assertEqual(self.row(b)["state"], "observed")

    def test_candidates_are_uncertain_and_only_stale_sending(self):
        self.add(1); self.add(2, "sending", attempted=100); self.add(3, "sending", attempted=990); self.add(4, "pending"); self.add(5, "observed")
        self.assertEqual([r["seq"] for r in memory_outbox.candidates(self.db, 500, 1000)], [1, 2])

    def test_corrupt_row_fails_integrity(self):
        b = self.add(1)
        self.db.execute("UPDATE _watoom_outbox SET digest='0' WHERE id=?", (b["id"],))
        with self.assertRaises(ValueError):
            memory_outbox.envelope(self.row(b))

    def test_invalid_search_response_is_an_error_not_absence(self):
        b = self.add(1)
        with self.assertRaises(ValueError):
            memory_outbox.classify(b, lambda q: {"error": "x"})

if __name__ == "__main__":
    unittest.main()
