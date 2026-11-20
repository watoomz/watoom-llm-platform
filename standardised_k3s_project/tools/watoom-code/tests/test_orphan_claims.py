import sqlite3, sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import orphan_claims


class Tests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute(
            "CREATE TABLE session_v2(id TEXT,parent_id TEXT,time_suspended INTEGER,time_updated INTEGER,time_idle INTEGER,idle_outcome TEXT,resume_attempts INTEGER)"
        )
        self.db.execute("INSERT INTO session_v2 VALUES ('parent',NULL,NULL,100,200,'interrupted',0)")
        self.db.execute("INSERT INTO session_v2 VALUES ('child','parent',10,20,NULL,NULL,2)")
        self.db.commit()
        self.expected = [dict(id="child", parent_id="parent", time_suspended=10, time_updated=20)]

    def test_exact_cancel_preserves_history(self):
        self.assertEqual(orphan_claims.reconcile(self.db, self.expected), 1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM session_v2").fetchone()[0], 2)
        self.assertEqual(
            self.db.execute(
                "SELECT time_suspended,resume_attempts,time_updated FROM session_v2 WHERE id='child'"
            ).fetchone(),
            (None, 0, 20),
        )

    def test_changed_identity_refused(self):
        self.expected[0]["time_updated"] = 21
        with self.assertRaises(ValueError):
            orphan_claims.reconcile(self.db, self.expected)
        self.assertEqual(self.db.execute("SELECT time_suspended FROM session_v2 WHERE id='child'").fetchone()[0], 10)

    def test_other_claim_refused(self):
        self.db.execute("INSERT INTO session_v2 VALUES ('other','parent',10,20,NULL,NULL,0)")
        self.db.commit()
        with self.assertRaises(ValueError):
            orphan_claims.reconcile(self.db, self.expected)

    def test_running_parent_refused(self):
        self.db.execute("UPDATE session_v2 SET time_idle=NULL WHERE id='parent'")
        self.db.commit()
        with self.assertRaises(ValueError):
            orphan_claims.reconcile(self.db, self.expected)


if __name__ == "__main__":
    unittest.main()
