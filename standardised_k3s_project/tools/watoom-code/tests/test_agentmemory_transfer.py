import json, pathlib, sys, tempfile, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import agentmemory_transfer as t


def store(root, memories):
    root.mkdir()
    body = json.dumps({m["id"]: m for m in memories}).encode() + bytes.fromhex("00009653c10928ab8ffd")
    (root / "mem%3Amemories.bin").write_bytes(body)


class Transfer(unittest.TestCase):
    def test_export_pages_verify_and_resumable_skip_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            memories = [{"id": "m%03d" % i, "content": "x" * 200, "createdAt": "2026-10-%02dT00:00:00Z" % (1 + i % 28)} for i in range(60)]
            store(tmp / "store", memories)
            manifest = t.export(tmp / "store", tmp / "out", page_bytes=2048)
            pages = manifest["collections"]["memories"]["pages"]
            self.assertEqual(manifest["collections"]["memories"]["records"], 60)
            self.assertGreater(len(pages), 3)
            self.assertEqual(t.verify(tmp / "out", tmp / "store")["status"], "PASS")
            received, calls = {}, [0]
            def sender(url, secret, body):
                self.assertEqual(body["strategy"], "skip")
                calls[0] += 1
                if calls[0] == 3:
                    raise KeyboardInterrupt
                new = [m for m in body["exportData"]["memories"] if m["id"] not in received]
                received.update({m["id"]: m for m in new})
                return {"success": True, "stats": {"memories": len(new), "skipped": len(body["exportData"]["memories"]) - len(new)}}
            with self.assertRaises(KeyboardInterrupt):
                t.import_pages(tmp / "out", "http://x", "s", sender)
            self.assertEqual(len(json.loads((tmp / "out/import-checkpoint.json").read_text())["done"]), 2)
            totals = t.import_pages(tmp / "out", "http://x", "s", sender)
            self.assertEqual(totals["pages"], len(pages) - 2)
            self.assertEqual(len(received), 60)
            self.assertEqual(t.import_pages(tmp / "out", "http://x", "s", sender)["pages"], 0)

    def test_tampered_page_and_existing_output_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            store(tmp / "store", [{"id": "a", "createdAt": "1"}])
            t.export(tmp / "store", tmp / "out", page_bytes=4096)
            with self.assertRaises(FileExistsError):
                t.export(tmp / "store", tmp / "out", page_bytes=4096)
            page = tmp / "out" / "memories-00000.jsonl"
            page.write_text(page.read_text().replace('"a"', '"b"'))
            with self.assertRaises(ValueError):
                t.import_pages(tmp / "out", "http://x", "s", lambda *a: {"success": True})

    def test_missing_records_fail_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            store(tmp / "store", [{"id": "a"}, {"id": "b"}])
            t.export(tmp / "store", tmp / "out", page_bytes=4096)
            (tmp / "store/mem%3Amemories.bin").write_bytes(json.dumps({"a": {"id": "a"}}).encode())
            report = t.verify(tmp / "out", tmp / "store")
            self.assertEqual((report["status"], report["memories"]["missing"]), ("FAIL", 1))


if __name__ == "__main__":
    unittest.main()
