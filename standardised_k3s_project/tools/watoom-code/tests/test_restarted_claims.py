import sqlite3,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import restarted_claims
class Tests(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(':memory:');self.db.execute('CREATE TABLE session_v2(id TEXT,parent_id TEXT,time_suspended INTEGER,time_updated INTEGER,time_idle INTEGER,idle_outcome TEXT,resume_attempts INTEGER)')
  self.db.executemany('INSERT INTO session_v2 VALUES (?,?,?,?,NULL,NULL,1)',[('root',None,10,11),('child','root',12,13)]);self.db.commit();self.expected=[dict(id='root',parent_id=None,time_suspended=10,time_updated=11),dict(id='child',parent_id='root',time_suspended=12,time_updated=13)]
 def test_stop_preserves_rows_and_timestamps(self):
  self.assertEqual(restarted_claims.reconcile(self.db,self.expected,'root',20,30),2);self.assertEqual(self.db.execute('SELECT time_updated,time_suspended,time_idle,idle_outcome FROM session_v2 ORDER BY id').fetchall(),[(13,None,30,'interrupted'),(11,None,30,'interrupted')])
 def test_newer_claim_refused(self):
  with self.assertRaises(ValueError):restarted_claims.reconcile(self.db,self.expected,'root',12,30)
 def test_other_root_refused(self):
  with self.assertRaises(ValueError):restarted_claims.reconcile(self.db,self.expected,'wrong',20,30)
 def test_unexpected_claim_refused(self):
  self.db.execute("INSERT INTO session_v2 VALUES ('other',NULL,1,1,NULL,NULL,0)");self.db.commit()
  with self.assertRaises(ValueError):restarted_claims.reconcile(self.db,self.expected,'root',20,30)
 def test_changed_identity_refused(self):
  self.expected[0]['time_updated']=0
  with self.assertRaises(ValueError):restarted_claims.reconcile(self.db,self.expected,'root',20,30)
if __name__=='__main__':unittest.main()
