import importlib.util,pathlib,sqlite3,tempfile,unittest
spec=importlib.util.spec_from_file_location('skill_import',pathlib.Path(__file__).parents[1]/'import-skill-collection.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class ImportTests(unittest.TestCase):
 def fixture(self):
  temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);root=pathlib.Path(temporary.name)
  for name in ['source','target']:
   db=sqlite3.connect(root/name)
   db.executescript("CREATE TABLE sources(repo TEXT PRIMARY KEY,commit_sha TEXT);CREATE TABLE skills(id TEXT PRIMARY KEY,repo TEXT,path TEXT,name TEXT,description TEXT,sha256 TEXT,license TEXT,risk TEXT,validation TEXT,raw TEXT);CREATE TABLE approvals(skill_id TEXT PRIMARY KEY,approved_sha TEXT,note TEXT,at TEXT);CREATE VIRTUAL TABLE skills_fts USING fts5(id UNINDEXED,name,description);CREATE TABLE skill_attributes(skill_id TEXT PRIMARY KEY,classification TEXT,categories TEXT,frameworks TEXT,dependencies TEXT);CREATE TABLE external_links(url TEXT PRIMARY KEY,discovered_in TEXT,state TEXT);")
   db.close()
  return root
 def test_import_is_additive_idempotent_and_never_approves(self):
  root=self.fixture()
  with sqlite3.connect(root/'source') as db:
   db.execute("INSERT INTO sources VALUES(?,?)",('owner/repo','a'*40))
   db.execute("INSERT INTO skills VALUES(?,?,?,?,?,?,?,?,?,?)",('id','owner/repo','skill','Example','Example','b'*64,'UNKNOWN','[]','valid','inert'))
   db.execute("INSERT INTO external_links VALUES(?,?,?)",('https://example.invalid/tutorial','owner/repo','unsupported'))
  with sqlite3.connect(root/'target') as db:
   db.execute("INSERT INTO approvals VALUES(?,?,?,?)",('existing','c'*64,'existing review','now'))
  result=module.merge(root/'source',root/'target')
  self.assertEqual(result['inserted'],1);self.assertEqual(result['approved'],1);self.assertEqual(result['external_references'],1)
  self.assertEqual(module.merge(root/'source',root/'target')['inserted'],0)
  with sqlite3.connect(root/'target') as db:self.assertEqual(db.execute("SELECT approved_sha FROM approvals WHERE skill_id='existing'").fetchone()[0],'c'*64)
 def test_source_conflict_rolls_back_import(self):
  root=self.fixture()
  for name,revision in [('source','a'*40),('target','b'*40)]:
   with sqlite3.connect(root/name) as db:db.execute('INSERT INTO sources VALUES(?,?)',('owner/repo',revision))
  with sqlite3.connect(root/'source') as db:db.execute("INSERT INTO skills VALUES(?,?,?,?,?,?,?,?,?,?)",('id','owner/repo','skill','Example','Example','c'*64,'UNKNOWN','[]','valid','inert'))
  with self.assertRaisesRegex(ValueError,'Conflicting'):module.merge(root/'source',root/'target')
  with sqlite3.connect(root/'target') as db:self.assertEqual(db.execute('SELECT count(*) FROM skills').fetchone()[0],0)
if __name__=='__main__':unittest.main()
