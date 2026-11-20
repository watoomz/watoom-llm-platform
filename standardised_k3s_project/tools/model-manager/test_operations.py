import json, tempfile, unittest, unittest.mock, hashlib
from pathlib import Path
from store import Store
from operations import Operations, Blocked


class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = Store(self.root / "catalog.sqlite")

        def download(root, repo, rev, item, progress, cancel=lambda: False):
            dest = Path(root) / item["path"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"fixture")
            progress(7)
            return {"path": str(dest), "bytes": 7, "sha256": hashlib.sha256(b"fixture").hexdigest()}

        self.calls = []

        def broker(action, record):
            self.calls.append(action)
            return {"registered": True} if action == "register" else {"retired": True}

        self.ops = Operations(self.store, self.root / "models", broker, download, metadata_reader=lambda path: None)
        self.selection = {
            "repository": "fixture/model",
            "revision": "a" * 40,
            "kind": "gguf",
            "settings": {"context": 131072},
            "files": [{"path": "m.gguf", "size": 7}],
            "max_context": 131072,
        }

    def tearDown(self):
        self.tmp.cleanup()

    def install(self):
        return self.ops.install(self.selection)

    def test_keep_default(self):
        record = self.install()
        plan = self.ops.plan_remove(record["id"], record["revision"])
        result = self.ops.remove(record["id"], record["revision"], confirmation=plan["confirmation"])
        self.assertEqual(result["files"], "retained")
        self.assertTrue(Path(plan["paths"][0]).exists())

    def test_exact_delete_quarantines(self):
        r = self.install()
        plan = self.ops.plan_remove(r["id"], r["revision"])
        with self.assertRaises(Blocked):
            self.ops.remove(r["id"], r["revision"], True, "wrong")
        self.assertTrue(Path(plan["paths"][0]).exists())
        result = self.ops.remove(r["id"], r["revision"], True, plan["confirmation"])
        self.assertEqual(result["actual_reclaimed_bytes"], 0)
        self.assertTrue(Path(result["moved"][0]["quarantine"]).exists())

    def test_removal_replay(self):
        r = self.install()
        plan = self.ops.plan_remove(r["id"], r["revision"])
        first = self.ops.remove(r["id"], r["revision"], True, plan["confirmation"], job_id="fixture-job")
        self.assertEqual(
            first, self.ops.remove(r["id"], r["revision"], True, plan["confirmation"], job_id="fixture-job")
        )

    def test_keep_requires_confirmation(self):
        r = self.install()
        with self.assertRaises(Blocked):
            self.ops.remove(r["id"], r["revision"])

    def test_reinstall_after_quarantine(self):
        r = self.install()
        plan = self.ops.plan_remove(r["id"], r["revision"])
        self.ops.remove(r["id"], r["revision"], True, plan["confirmation"])
        self.assertTrue(self.install()["registered"])

    def test_stale_revision(self):
        r = self.install()
        with self.assertRaises(Blocked):
            self.ops.remove(r["id"], "b" * 40)

    def test_disk_check_looks_at_where_files_actually_land_not_at_root(self):
        # self.root can be a small container-local overlay with only the per-category
        # subdirectory bind-mounted onto real storage; disk_usage(self.root) alone would
        # wrongly report the overlay's free space instead of the mount actually used.
        import operations
        from collections import namedtuple

        Usage = namedtuple("Usage", ["total", "used", "free"])

        def fake_disk_usage(path):
            return Usage(0, 0, 0) if Path(path) == self.ops.root else Usage(0, 0, 10**12)

        with unittest.mock.patch.object(operations.shutil, "disk_usage", fake_disk_usage):
            self.assertTrue(self.install()["registered"])

    def test_reregister_retires_then_registers_keeping_files_and_identity(self):
        r = self.install()
        self.store.db.execute("UPDATE models SET record=json_set(record,'$.registered',json('true')) WHERE id=?", (r["id"],))
        self.calls.clear()
        out = self.ops.reregister(r["id"], r["revision"], {"reasoning": "on"})
        self.assertEqual(self.calls, ["retire", "register"])
        self.assertEqual((out["id"], out["artifacts"], out["registered"]), (r["id"], r["artifacts"], True))
        self.assertEqual((out["settings"]["reasoning"], out["reregistered_from"]), ("on", {"reasoning": None}))
        self.assertTrue(all(Path(p).exists() for p in self.ops.plan_remove(r["id"], r["revision"])["paths"]))

    def test_reregister_can_adopt_swift_runtime_settings(self):
        r = self.install()
        out = self.ops.reregister(r["id"], r["revision"], {"cache_k": "turbo5", "cache_v": "turbo4", "batch": 2048, "ubatch": 1024})
        self.assertEqual((out["settings"]["cache_k"], out["settings"]["ubatch"], out["id"]), ("turbo5", 1024, r["id"]))

    def test_reregister_reproves_mtp_from_the_header_and_enables_draft_mtp(self):
        r = self.install()
        self.ops.metadata_reader = lambda path: {"context_length": 131072, "nextn_predict_layers": 1}
        out = self.ops.reregister(r["id"], r["revision"], {"speculation": "draft-mtp", "draft_count": 5})
        self.assertTrue(out["capabilities"]["mtp"])
        self.assertEqual((out["settings"]["speculation"], out["settings"]["draft_count"]), ("draft-mtp", 5))
        self.ops.metadata_reader = lambda path: {"context_length": 131072, "nextn_predict_layers": 0}
        with self.assertRaises(ValueError):
            self.ops.reregister(r["id"], r["revision"], {"speculation": "draft-mtp", "draft_count": 5})

    def test_interrupted_reregister_retires_the_leftover_registration(self):
        r = self.install()
        record = json.loads(self.store.db.execute("SELECT record FROM models WHERE id=?", (r["id"],)).fetchone()[0])
        record.update(registered=False, controller_identity=record.get("controller_identity") or "leftover")
        with self.store.db:
            self.store.db.execute("UPDATE models SET record=? WHERE id=?", (json.dumps(record), r["id"]))
        self.calls.clear()
        out = self.ops.reregister(r["id"], r["revision"], {"reasoning": "on"})
        self.assertEqual(self.calls, ["retire", "register"])
        self.assertTrue(out["registered"])

    def test_reregister_refuses_other_settings_and_stale_revision(self):
        r = self.install()
        with self.assertRaises(Blocked):
            self.ops.reregister(r["id"], r["revision"], {"context": 4096})
        with self.assertRaises(Blocked):
            self.ops.reregister(r["id"], "b" * 40)

    def test_reregister_failed_register_is_recoverable(self):
        r = self.install()
        broker = self.ops.broker
        self.ops.broker = lambda action, record: {"registered": False} if action == "register" else {"retired": True}
        failed = self.ops.reregister(r["id"], r["revision"])
        self.assertFalse(failed["registered"])
        self.assertIn("Registration not verified", failed["registration_error"])
        self.ops.broker = broker
        self.calls.clear()
        self.assertTrue(self.ops.reregister(r["id"], r["revision"])["registered"])
        self.assertEqual(self.calls, ["register"])

    def test_dedup(self):
        r = self.install()
        self.assertEqual(self.install()["id"], r["id"])
        self.assertEqual(self.calls, ["register"])

    def test_settings_create_immutable_replacement_share_artifacts(self):
        original = self.install()
        self.selection["settings"] = {"context": 65536}
        revised = self.install()
        self.assertNotEqual(original["id"], revised["id"])
        self.assertEqual(original["artifacts"], revised["artifacts"])
        self.assertEqual(self.ops.plan_remove(original["id"], original["revision"])["bytes"], 0)

    def test_diffusion_variants_share_configs_and_reinstall(self):
        self.selection.update(
            kind="diffusion-pipeline",
            settings={"width": 1024, "precision": "float32"},
            files=[{"path": "model_index.json", "size": 7}, {"path": "unet/m.safetensors", "size": 7}],
        )
        a = self.install()
        self.selection["settings"] = {"width": 1024, "precision": "float16"}
        self.selection["files"][1]["path"] = "unet/m.fp16.safetensors"
        b = self.install()
        self.assertTrue((Path(b["base_path"]) / "model_index.json").exists())
        self.assertEqual(
            (Path(a["base_path"]) / "model_index.json").stat().st_ino,
            (Path(b["base_path"]) / "model_index.json").stat().st_ino,
        )
        plan = self.ops.plan_remove(b["id"], b["revision"])
        self.ops.remove(b["id"], b["revision"], confirmation=plan["confirmation"])
        self.assertTrue(self.install()["registered"])

    def test_shared_file_survives(self):
        r = self.install()
        aid = r["artifacts"][0]
        with self.store.db:
            self.store.db.execute("INSERT INTO refs VALUES(?,?)", ("other", aid))
        self.assertEqual(self.ops.plan_remove(r["id"], r["revision"])["bytes"], 0)

    def test_protected(self):
        import json

        r = self.install()
        r["protected"] = True
        with self.store.db:
            self.store.db.execute("UPDATE models SET record=? WHERE id=?", (json.dumps(r), r["id"]))
        with self.assertRaises(Blocked):
            self.ops.remove(r["id"], r["revision"])


if __name__ == "__main__":
    unittest.main()
