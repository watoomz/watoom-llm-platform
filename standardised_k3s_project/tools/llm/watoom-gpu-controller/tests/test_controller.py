import unittest
from controller import Controller, State, Conflict, Unsafe


class Store:
    def __init__(self):
        self.value = State()
        self.history = []

    def load(self):
        return self.value

    def save(self, value):
        self.value = value
        self.history.append(value)


class Actuator:
    def __init__(self):
        self.replicas = {"qwen": 1, "mesh": 0}
        self.fail = None
        self.fence = True
        self.calls = []

    def scale(self, name, replicas, generation):
        self.calls.append((name, replicas, generation))
        if self.fail == f"{name}-{replicas}":
            raise TimeoutError("simulated unknown outcome")
        self.replicas[name] = replicas

    def stopped(self, name):
        return self.replicas[name] == 0

    def healthy(self, name):
        return self.replicas[name] == 1

    def fence_and_reconcile(self, generation):
        return self.fence


class Tests(unittest.TestCase):
    def setUp(self):
        self.s = Store()
        self.a = Actuator()
        self.c = Controller(self.s, self.a, "qwen", "mesh")

    def test_cycle(self):
        g = self.c.begin_specialist("job1")
        self.c.switch_to_mesh("job1", g)
        with self.assertRaises(Conflict):
            self.c.request_qwen()
        self.c.begin_restore("job1", g)
        self.assertEqual(self.s.load(), State("qwen-ready", None, g))
        self.assertTrue(self.c.request_qwen())

    def test_double_acquire(self):
        self.c.begin_specialist("first")
        with self.assertRaises(Conflict):
            self.c.begin_specialist("second")

    def test_stale_generation(self):
        self.c.begin_specialist("first")
        with self.assertRaises(Conflict):
            self.c.switch_to_mesh("first", 0)

    def test_timeout_retains_ownership(self):
        g = self.c.begin_specialist("first")
        self.a.fail = "qwen-0"
        with self.assertRaises(TimeoutError):
            self.c.switch_to_mesh("first", g)
        self.assertEqual(self.s.load().phase, "recovery-required")
        with self.assertRaises(Conflict):
            self.c.request_qwen()

    def test_recovery_requires_ended_owner(self):
        g = self.c.begin_specialist("first")
        self.a.fail = "qwen-0"
        with self.assertRaises(TimeoutError):
            self.c.switch_to_mesh("first", g)
        with self.assertRaises(Unsafe):
            self.c.recover("first", g, False)

    def test_unknown_write_blocks_restoration(self):
        g = self.c.begin_specialist("first")
        self.c.switch_to_mesh("first", g)
        self.a.fence = False
        with self.assertRaises(Unsafe):
            self.c.begin_restore("first", g)
        self.assertEqual(self.s.load().phase, "recovery-required")

    def test_ended_owner_recovery(self):
        g = self.c.begin_specialist("first")
        self.a.fail = "mesh-1"
        with self.assertRaises(TimeoutError):
            self.c.switch_to_mesh("first", g)
        self.a.fail = None
        self.c.recover("first", g, True)
        self.assertTrue(self.c.request_qwen())

    def test_old_owner_cannot_recover(self):
        g = self.c.begin_specialist("first")
        self.a.fail = "mesh-1"
        with self.assertRaises(TimeoutError):
            self.c.switch_to_mesh("first", g)
        with self.assertRaises(Conflict):
            self.c.recover("other", g, True)

    def test_failed_qwen_health_keeps_lock(self):
        g = self.c.begin_specialist("first")
        self.c.switch_to_mesh("first", g)
        self.a.fail = "qwen-1"
        with self.assertRaises(TimeoutError):
            self.c.begin_restore("first", g)
        self.assertTrue(self.s.load().uncertain)


if __name__ == "__main__":
    unittest.main()
