import importlib.util
import json
import pathlib
import unittest

spec = importlib.util.spec_from_file_location("ur", pathlib.Path(__file__).with_name("ue_route.py"))
ur = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ur)


class Fake:
    """A transport whose project.get_status flips to connected after `up_after` status polls; records every call."""
    def __init__(self, log, state):
        self.log, self.state = log, state

    def call(self, category, method, args=None, timeout=60):
        self.log.append((category, method))
        if (category, method) == ("project", "get_status"):
            self.state["polls"] += 1
            if self.state["fail_status"] and self.state["polls"] <= self.state["fail_status"]:
                raise RuntimeError("route down")
            return json.dumps({"editorConnected": self.state["polls"] > self.state["up_after"]})
        if (category, method) == ("editor", "start_editor"):
            return json.dumps({"success": False, "message": "Editor launched but did not become ready: the editor process is gone"})
        raise AssertionError((category, method))

    def close(self):
        pass


class Ensure(unittest.TestCase):
    def run_ensure(self, up_after, fail_status=0, max_wait=100):
        log, state, now = [], {"polls": 0, "up_after": up_after, "fail_status": fail_status}, [0.0]
        def sleep(s): now[0] += s
        r = ur.ensure_editor(lambda: Fake(log, state), max_wait, 15, sleep=sleep, clock=lambda: now[0])
        return r, log

    def test_running_editor_is_left_alone(self):
        r, log = self.run_ensure(up_after=0)
        self.assertEqual(r["state"], "already-running")
        self.assertNotIn(("editor", "start_editor"), log)

    def test_closed_editor_is_started_once_and_polled_until_the_bridge_answers(self):
        r, log = self.run_ensure(up_after=5)
        self.assertEqual(r["state"], "started")
        self.assertEqual(log.count(("editor", "start_editor")), 1)
        self.assertGreater(r["waited_s"], 0)

    def test_false_start_failure_text_does_not_stop_the_wait(self):
        r, _ = self.run_ensure(up_after=3)
        self.assertEqual(r["state"], "started")

    def test_route_errors_count_as_not_connected_and_it_gives_up_at_max_wait(self):
        r, log = self.run_ensure(up_after=10 ** 6, max_wait=60)
        self.assertEqual(r["state"], "timeout")
        self.assertEqual(log.count(("editor", "start_editor")), 1)
        r2, _ = self.run_ensure(up_after=0, fail_status=2)
        self.assertEqual(r2["state"], "started")

    def test_ssh_command_is_pinned_and_non_interactive(self):
        c = ur.ssh_command("10.99.1.44", 2224, "uemcp", "/k")
        self.assertIn("StrictHostKeyChecking=yes", c)
        self.assertIn("BatchMode=yes", c)
        self.assertEqual(c[-1], "uemcp@10.99.1.44")


class Describe(unittest.TestCase):
    def test_describe_sends_the_gateway_describe_action_without_args(self):
        sent = []
        tr = ur.SshTransport.__new__(ur.SshTransport)
        tr.n = 0
        tr._send = sent.append
        tr._wait = lambda n, timeout: {"result": {"content": [{"type": "text", "text": "{}"}]}}
        tr.call("niagara", "epic_set_stack_input_data", None, 5, action="describe")
        args = sent[0]["params"]["arguments"]
        self.assertEqual((args["action"], args["method"], "args" in args), ("describe", "epic_set_stack_input_data", False))


class ReadRetry(unittest.TestCase):
    def test_a_daemon_restart_is_retried_and_other_errors_are_not(self):
        calls = []

        class T:
            def call(self, *a):
                calls.append(a)
                if len(calls) == 1:
                    raise RuntimeError("foliage.get_instances: The ue-mcp daemon stopped while this call was in flight.")
                return '{"ok": 1}'
        self.assertEqual(ur.call_read(T(), "foliage", "get_instances", {}, sleep=lambda s: None), '{"ok": 1}')
        self.assertEqual(len(calls), 2)

        class Bad:
            def call(self, *a):
                raise RuntimeError("level.x: permission denied")
        with self.assertRaises(RuntimeError):
            ur.call_read(Bad(), "level", "x", {}, sleep=lambda s: None)


class Banners(unittest.TestCase):
    def test_notice_blocks_are_not_the_reply(self):
        self.assertTrue(ur.is_banner("UE_MCP_UPGRADE_AVAILABLE 1.5"))
        self.assertTrue(ur.is_banner("  [AGENT DIRECTIVE - MANDATORY]\nexecute_python was used"))
        self.assertTrue(ur.is_banner('MACHINE_DIRECTIVE={"kind":"workaround.feedback"}'))
        self.assertFalse(ur.is_banner('{"success": true}'))


if __name__ == "__main__":
    unittest.main()
