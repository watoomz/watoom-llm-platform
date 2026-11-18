import importlib.util, pathlib, sys, tempfile, unittest, sqlite3, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import production_consolidation as subject

class ProductionConsolidationTests(unittest.TestCase):
    def test_model_coordinator_creates_new_durable_private_recovery_files(self):
        script=pathlib.Path(__file__).resolve().parents[3]/"scripts/watoom-qwen-maintenance.py"
        spec=importlib.util.spec_from_file_location("model_maintenance",script);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            path=pathlib.Path(tmp)/"new-checkpoint.json";module.atomic_json(path,{"state":"checkpointed"})
            self.assertEqual(json.loads(path.read_text()),{"state":"checkpointed"});self.assertEqual(path.stat().st_mode & 0o777,0o600)
            module.atomic_json(path,{"state":"ready"});self.assertEqual(json.loads(path.read_text()),{"state":"ready"})

    def test_rig_and_production_are_preserved(self):
        for ns,name in [("watoom-code-rig-jobs","watoom-code"),("watoom-code","watoom-code"),("watoom-code","agentmemory")]:
            self.assertEqual(subject.classify({"metadata":{"namespace":ns,"name":name}}),"KEEP_PRODUCTION")
        self.assertEqual(subject.classify({"metadata":{"namespace":"opencode","name":"opencode-v2-canary"}}),"INVESTIGATE")
    def test_atomic_session_specific_checkpoint_preserves_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);db=root/"source.sqlite"
            with sqlite3.connect(db) as c:
                c.executescript("CREATE TABLE session_v2(id,parent_id,directory,model,time_updated,time_suspended); CREATE TABLE session_message(session_id,id,seq,data,type); CREATE TABLE session_pending(id); CREATE TABLE session_inbox(id); CREATE TABLE _watoom_checkpoint(scope,job,seq,body); CREATE TABLE _watoom_outbox(id); CREATE TABLE project(id,worktree,name);")
                c.execute("insert into session_v2 values ('parent',NULL,'/project','swift',1,NULL)");c.execute("insert into session_v2 values ('child','parent','/project','swift',2,NULL)")
                c.execute("insert into session_message values (?,?,?,?,?)", ("parent","msg",1,json.dumps({"status":"failed"}),"compaction"));c.execute("insert into project values ('p','/project','project')")
            one=subject.checkpoint(db,root/"one");two=subject.checkpoint(db,root/"two")
            self.assertEqual(one,{"sessions":2,"children":1,"projects":1});self.assertEqual(one,two)
            data=json.loads((root/"one/session-checkpoints.private.json").read_text());self.assertEqual(len(data["compactions"]),1)
            with sqlite3.connect(db) as c:self.assertEqual(c.execute("select count(*) from session_v2").fetchone()[0],2)
    def test_checkpoint_reads_v225_schema_without_session_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);db=root/"source.sqlite"
            with sqlite3.connect(db) as c:
                c.executescript("CREATE TABLE session_v2(id,parent_id,directory,model,time_updated,time_suspended); CREATE TABLE session_message(session_id,id,seq,data,type); CREATE TABLE session_inbox(id); CREATE TABLE job(id,status); CREATE TABLE _watoom_checkpoint(scope,job,seq,body); CREATE TABLE _watoom_outbox(id); CREATE TABLE project(id,worktree,name);")
                c.execute("insert into session_v2 values ('parent',NULL,'/project','swift',1,NULL)");c.execute("insert into project values ('p','/project','project')")
            self.assertEqual(subject.checkpoint(db,root/"one"),{"sessions":1,"children":0,"projects":1})
            data=json.loads((root/"one/session-checkpoints.private.json").read_text())
            self.assertNotIn("session_pending",data["pending"]);self.assertIn("job",data["pending"])
    def test_legacy_reconciliation_requires_explicit_restore(self):
        root=pathlib.Path(__file__).resolve().parents[3]
        self.assertIn("opencode_agent_restore_retired | default(false)",(root/"ansible/playbooks/opencode-agent.yml").read_text())
        text=(root/"ansible/playbooks/watoom-code-context.yml").read_text()
        self.assertNotIn("pi-kali",text);self.assertNotIn("PersistentVolumeClaim",text)
    def test_generated_recovery_request_ids_are_native_and_ascending(self):
        first=subject.native_message_id(1793220088103);later=subject.native_message_id(1793220088104)
        self.assertRegex(first,r"^msg_1843f1127001[0-9A-Za-z]{14}$");self.assertLess(first[:16],later[:16])
        self.assertNotEqual(subject.native_message_id(1),subject.native_message_id(1))
    def test_recovery_rejects_non_native_request_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):subject.recover_session(pathlib.Path(tmp),"ses_x","not-a-message-id")
            with self.assertRaises(ValueError):subject.recover_session(pathlib.Path(tmp),"","msg_x")
    def test_application_pins_live_only_in_production_vars(self):
        import yaml
        root=pathlib.Path(__file__).resolve().parents[3]
        defaults=yaml.safe_load((root/"ansible/roles/watoom-code/defaults/main.yml").read_text())
        pins=yaml.safe_load((root/"ansible/vars/watoom-code.yml").read_text())
        for key in ("watoom_code_image","watoom_code_image_source_commit","watoom_code_application_commit",
                    "watoom_code_memory_image","watoom_code_toolkit_image","watoom_code_toolkit_source_commit"):
            self.assertNotIn(key,defaults);self.assertIn(key,pins)
        for key in ("watoom_code_image","watoom_code_memory_image","watoom_code_toolkit_image"):self.assertIn("@sha256:",pins[key])
        self.assertFalse([k for k in defaults if k.endswith("_image") and isinstance(defaults[k],str) and "@sha256:" in defaults[k]])
        self.assertIn("watoom_code_image is defined",(root/"ansible/roles/watoom-code/tasks/main.yml").read_text())
        for playbook in ("watoom-code.yml","watoom-code-memory-catalogue.yml"):
            self.assertIn("../vars/watoom-code.yml",(root/"ansible/playbooks"/playbook).read_text())
if __name__=="__main__":unittest.main()
