import copy, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from store import Store
from broker import Broker, identity
from workload import LLAMA_IMAGE

ID = "a" * 64


class FakeBroker(Broker):
    def admission(self, evidence):
        return __import__("contextlib").nullcontext()

    def __init__(self, config, store):
        super().__init__(config, store)
        self.objects = {}
        self.names = []
        self.deleted = []
        self.failing = False

    def artifacts(self, record):
        return [{"path": "/data/ai/models/gguf/model-manager/" + ID + "/m.gguf", "bytes": 7, "digest": "a" * 64}]

    def role(self, name, add):
        if add:
            self.names.append(name)
        elif name in self.names:
            self.names.remove(name)
        return {"rules": []}

    def kube(self, args, obj=None, missing=False):
        if args[0] == "get":
            return copy.deepcopy(self.objects.get((args[1], args[2])))
        if args[0] == "create":
            value = copy.deepcopy(obj)
            kind = value["kind"].lower()
            value["metadata"].update(uid=kind + "-uid", resourceVersion="1")
            if kind == "service":
                value["spec"]["clusterIP"] = "10.243.1.2"
            self.objects[(kind, value["metadata"]["name"])] = value
            return copy.deepcopy(value)
        raise AssertionError(args)

    def delete_owned(self, kind, name, uid):
        actual = self.objects[(kind, name)]
        if actual["metadata"]["uid"] != uid:
            raise ValueError("Replacement protected")
        self.deleted.append(kind)
        del self.objects[(kind, name)]


class Transaction(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = Store(self.root / "catalog.sqlite")
        self.record = {
            "id": ID,
            "revision": "b" * 40,
            "kind": "gguf",
            "settings": {"context": 100000},
            "artifacts": [],
            "registered": False,
        }
        self.store.db.execute("INSERT INTO models VALUES(?,?,?)", (ID, "b" * 40, json.dumps(self.record)))
        self.store.db.commit()
        self.config = {
            "state": str(self.root / "broker"),
            "controller_state": str(self.root / "controller"),
            "router_view": str(self.root / "router/catalog.json"),
            "controller_socket": "fixture",
            "images": {"gguf": LLAMA_IMAGE, "backend_auth_file": "/data/ai/private/model-manager/backend-key"},
        }
        Path(self.config["controller_state"]).mkdir()
        self.broker = FakeBroker(self.config, self.store)
        self.owner = None

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def rpc(self, path, request):
        action = request["action"]
        if action == "status":
            return {"owner": self.owner, "uncertain": False}
        ledger = Path(self.config["controller_state"]) / "managed-models.json"
        if action == "enroll-model":
            if self.broker.failing:
                raise ValueError("Enrollment refused")
            ledger.write_text(json.dumps({"version": 1, "models": {request["deployment"]: request["record"]}}))
            return {"status": "enrolled"}
        if action == "retire-model":
            ledger.write_text(json.dumps({"version": 1, "models": {}}))
            return {"status": "retired"}
        raise AssertionError(request)

    def test_register_then_reconcile_after_missing_ui_commit(self):
        with patch("broker.rpc", self.rpc), patch("broker.os.geteuid", return_value=0):
            first = self.broker("register", self.record)
            second = self.broker("register", self.record)
        self.assertTrue(first["registered"])
        self.assertTrue(second["registered"])
        self.assertEqual(len(self.broker.objects), 2)
        self.assertTrue(all(x["spec"].get("replicas", 0) == 0 for x in self.broker.objects.values()))

    def test_failed_enrollment_rolls_back_only_owned_resources(self):
        self.broker.failing = True
        with patch("broker.rpc", self.rpc), patch("broker.os.geteuid", return_value=0):
            with self.assertRaises(ValueError):
                self.broker("register", self.record)
        self.assertEqual(self.broker.objects, {})
        self.assertEqual(self.broker.names, [])

    def test_retirement_replay_uses_root_receipt_not_ui_resources(self):
        with patch("broker.rpc", self.rpc), patch("broker.os.geteuid", return_value=0):
            result = self.broker("register", self.record)
            self.record.update(result)
            self.record["resources"] = [{"kind": "role", "name": "unrelated", "uid": "malicious"}]
            with self.store.db:
                self.store.db.execute("UPDATE models SET record=? WHERE id=?", (json.dumps(self.record), ID))
            self.assertTrue(self.broker("retire", self.record)["retired"])
            self.assertTrue(self.broker("retire", self.record)["retired"])
        self.assertEqual(self.broker.objects, {})

    def test_lost_enrollment_reply_reconciles_before_resource_deletion(self):
        def lost_reply(path, request):
            result = self.rpc(path, request)
            if request["action"] == "enroll-model":
                raise ValueError("reply lost after commit")
            return result

        with patch("broker.rpc", lost_reply), patch("broker.os.geteuid", return_value=0):
            with self.assertRaisesRegex(ValueError, "reply lost"):
                self.broker("register", self.record)
        self.assertEqual(self.broker.objects, {})
        ledger = json.loads((Path(self.config["controller_state"]) / "managed-models.json").read_text())
        self.assertEqual(ledger["models"], {})

    def test_generation_settings_reach_worker_and_invalid_runtime_settings_are_rejected(self):
        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "watoom-code"))
        self.record.update(kind="diffusion-pipeline", registered=True)
        with self.store.db:
            self.store.db.execute("UPDATE models SET record=? WHERE id=?", (json.dumps(self.record), ID))
        with patch("broker.rpc", self.rpc), patch("broker.os.geteuid", return_value=0), patch(
            "native_admission.check_native_idle"
        ), patch("maintenance_guard.Maintenance"), patch.object(
            self.broker, "inference", return_value={"fixture": True}
        ) as inference:
            self.broker("generate", self.record, {"prompt": "bench", "settings": {"width": 768, "height": 512}})
            self.assertEqual(inference.call_args.args[1]["settings"]["width"], 768)
            self.assertEqual(inference.call_args.args[1]["settings"]["steps"], 30)
            inference.reset_mock()
            with self.assertRaises(ValueError):
                self.broker("generate", self.record, {"prompt": "bench", "settings": {"precision": "float32"}})
            inference.assert_not_called()

    def test_owner_blocks_before_any_mutation(self):
        self.owner = "live-job"
        with patch("broker.rpc", self.rpc), patch("broker.os.geteuid", return_value=0):
            with self.assertRaises(ValueError):
                self.broker("register", self.record)
        self.assertEqual(self.broker.objects, {})


class SocketPermissions(unittest.TestCase):
    @unittest.skipUnless(
        __import__("os").geteuid() == 0 and __import__("shutil").which("setfacl"), "Linux root ACL regression"
    )
    def test_inherited_group_read_acl_does_not_block_owned_socket(self):
        import socket, subprocess, os, tempfile, stat
        from pathlib import Path
        from broker_service import secure_socket

        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(["setfacl", "-m", "d:u::rwx,d:g::r-x,d:o::---,d:m::rwx", directory], check=True)
            path = Path(directory) / "broker.sock"
            with socket.socket(socket.AF_UNIX) as server:
                server.bind(str(path))
                os.chmod(path, 0o660)
                self.assertTrue(os.getxattr(path, "system.posix_acl_access"))
                secure_socket(path, 1009)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o660)
                self.assertEqual(path.stat().st_gid, 1009)
                with self.assertRaises(OSError):
                    os.getxattr(path, "system.posix_acl_access")


class NativeAdmission(unittest.TestCase):
    def test_registration_and_retirement_guard_before_mutation(self):
        from contextlib import contextmanager

        @contextmanager
        def blocked(_):
            raise ValueError("Active native work")
            yield

        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "catalog.sqlite")
            broker = Broker({"state": str(Path(directory) / "broker")}, store)
            for action in ("register", "retire"):
                with patch.object(broker, "admission", side_effect=blocked), patch.object(
                    broker, "_dispatch"
                ) as dispatch:
                    with self.assertRaisesRegex(ValueError, "Active native work"):
                        broker(action, {"id": ID})
                    dispatch.assert_not_called()
            store.close()


class NativeProfileRemoval(unittest.TestCase):
    def test_prunes_the_live_providers_layout(self):
        from broker import prune_native_profiles

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = root / "config.json"
            alias = "mm-" + "c" * 16
            config = {
                "providers": {
                    "watoom": {
                        "models": {alias: {"modelID": alias}, "swift-qwen38-coder": {"modelID": "swift-qwen38-coder"}}
                    }
                }
            }
            path.write_text(json.dumps(config))
            self.assertTrue(prune_native_profiles(path, {alias}, root / "private" / "before.json"))
            after = json.loads(path.read_text())["providers"]["watoom"]["models"]
            self.assertNotIn(alias, after)
            self.assertIn("swift-qwen38-coder", after)

    def test_only_previous_owned_alias_is_pruned(self):
        from broker import prune_native_profiles

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = root / "config.json"
            alias = "mm-" + "a" * 16
            config = {
                "provider": {
                    "watoom": {
                        "models": {
                            alias: {"limit": {"context": 8192}},
                            "swift-qwen38-coder": {"limit": {"context": 100000}},
                            "mm-" + "b" * 16: {"custom": True},
                        }
                    }
                }
            }
            path.write_text(json.dumps(config))
            self.assertTrue(prune_native_profiles(path, {alias}, root / "private" / "before.json"))
            after = json.loads(path.read_text())["provider"]["watoom"]["models"]
            self.assertNotIn(alias, after)
            self.assertIn("mm-" + "b" * 16, after)
            self.assertEqual(after["swift-qwen38-coder"]["limit"]["context"], 100000)
            self.assertEqual(json.loads((root / "private" / "before.json").read_text()), config)
            with self.assertRaises(ValueError):
                prune_native_profiles(path, {"swift-qwen38-coder"}, root / "bad.json")
