import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import gpu_recover as gr  # noqa: E402


class Client:
    def __init__(self, owner, fail=None):
        self.owner, self.fail, self.calls = owner, fail, []

    def call(self, action, **kw):
        self.calls.append((action, kw))
        if self.fail == action:
            raise RuntimeError("refused")
        return {"owner": self.owner, "generation": 7}


class RecoverTests(unittest.TestCase):
    def test_recovers_when_moss_owns_the_gpu(self):
        c = Client("moss-image")
        self.assertEqual("recovered", gr.recover(c, log=lambda m: None))
        self.assertEqual(("recover", {"job": "moss-image", "generation": 7}), c.calls[-1])

    def test_never_touches_another_owner_or_idle(self):
        for owner in (None, "game-worker", "20261012T120000Z-12345678"):
            c = Client(owner)
            self.assertEqual("none", gr.recover(c, log=lambda m: None))
            self.assertEqual(["status"], [a for a, _ in c.calls])

    def test_controller_refusal_is_reported_not_raised(self):
        self.assertEqual("rejected", gr.recover(Client("moss-image", fail="recover"), log=lambda m: None))
        self.assertEqual("rejected", gr.recover(Client("moss-image", fail="status"), log=lambda m: None))


if __name__ == "__main__":
    unittest.main()
