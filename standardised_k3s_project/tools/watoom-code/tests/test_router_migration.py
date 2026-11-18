import importlib.util,json,os,pathlib,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location("router_migration",ROOT/"ansible/roles/watoom-code/files/enable-router-discovery.py")
migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
class RouterMigration(unittest.TestCase):
    def test_preserves_user_settings_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            path=pathlib.Path(directory)/"opencode.json"
            value={"model":"watoom/swift-qwen38-coder","preferences":{"keep":True},"providers":{"watoom":{"models":{"keep":{}},"settings":{"baseURL":"http://router/v1"}}}}
            path.write_text(json.dumps(value));path.chmod(0o600)
            self.assertTrue(migration.migrate(path))
            actual=json.loads(path.read_text())
            self.assertEqual(actual["model"],value["model"])
            self.assertEqual(actual["preferences"],value["preferences"])
            self.assertEqual(actual["providers"]["watoom"]["models"],{"keep":{}})
            self.assertEqual(actual["providers"]["watoom"]["settings"],{"baseURL":"http://router/v1","watoomRouterDiscovery":True})
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            self.assertFalse(migration.migrate(path))
    def test_invalid_json_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            path=pathlib.Path(directory)/"opencode.json";path.write_text("INVALID")
            with self.assertRaises(json.JSONDecodeError):migration.migrate(path)
            self.assertEqual(path.read_text(),"INVALID")
if __name__=="__main__":unittest.main()
