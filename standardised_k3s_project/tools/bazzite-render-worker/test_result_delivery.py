import unittest, tempfile, pathlib, hashlib, json
from result_delivery import Receiver


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.data = b"0123456789" * 100
        self.calls = 0
        self.receipt = {
            "schema": 1,
            "job": "job-a",
            "source_fingerprint": "source-a",
            "status": "COMPLETED",
            "files": {"frame.png": {"size": len(self.data), "sha256": hashlib.sha256(self.data).hexdigest()}},
        }

    def fetch(self, name, p):
        self.calls += 1
        offset = p.stat().st_size if p.exists() else 0
        with p.open("ab") as f:
            f.write(self.data[offset:])

    def test_disconnect_resume_and_ack_dedup(self):
        def glitch(name, p):
            p.write_bytes(self.data[:57])
            raise ConnectionError("wifi lost")

        with self.assertRaises(ConnectionError):
            Receiver(self.root, glitch).collect(self.receipt, "job-a", "source-a")
        self.assertEqual((self.root / "frame.png.part").stat().st_size, 57)
        r = Receiver(self.root, self.fetch)
        first = r.collect(self.receipt, "job-a", "source-a")
        second = r.collect(self.receipt, "job-a", "source-a")
        self.assertEqual(first["ack_id"], second["ack_id"])
        self.assertEqual(self.calls, 1)

    def test_wrong_job_no_transfer(self):
        with self.assertRaises(ValueError):
            Receiver(self.root, self.fetch).collect(self.receipt, "wrong", "source-a")
        self.assertEqual(self.calls, 0)

    def test_corrupt_transfer_not_accepted(self):
        with self.assertRaises(ValueError):
            Receiver(self.root, lambda n, p: p.write_bytes(b"bad")).collect(self.receipt, "job-a", "source-a")
        self.assertFalse((self.root / "receipt.json").exists())
        Receiver(self.root, self.fetch).collect(self.receipt, "job-a", "source-a")

    def test_terminal_receipt_change_refused(self):
        r = Receiver(self.root, self.fetch)
        r.collect(self.receipt, "job-a", "source-a")
        v = {**self.receipt, "status": "FAILED"}
        with self.assertRaises(ValueError):
            r.collect(v, "job-a", "source-a")

    def test_path_traversal_refused(self):
        self.receipt["files"]["../escape"] = self.receipt["files"].pop("frame.png")
        with self.assertRaises(ValueError):
            Receiver(self.root, self.fetch).collect(self.receipt, "job-a", "source-a")

    def tearDown(self):
        self.tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
