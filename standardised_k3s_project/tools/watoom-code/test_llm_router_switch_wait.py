"""The router's begin_inference waits out an in-flight model switch instead of answering 503 (no server started)."""
import ast
import pathlib
import threading
import time
import unittest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'manifests/10-infrastructure/llm/llm-router-gpu-controller.yml'


def namespace(wait_seconds):
    docs = yaml.safe_load_all(MANIFEST.read_text())
    config = next(d for d in docs if d and d.get('kind') == 'ConfigMap' and d.get('metadata', {}).get('name') == 'llm-router-app')
    tree = ast.parse(config['data']['router.py'])
    body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('switch_in_progress', 'begin_inference')]
    body += [n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ('SWITCHES_IN_FLIGHT', 'SWITCHES_IN_FLIGHT_LOCK', 'MODEL_SWITCH_LOCK') for t in n.targets)]
    ns = {'threading': threading, 'time': time, 'SWITCH_WAIT_SECONDS': wait_seconds}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(MANIFEST), 'exec'), ns)
    ns['time'] = type('T', (), {'monotonic': staticmethod(time.monotonic), 'sleep': staticmethod(lambda s: time.sleep(0.01))})
    return ns


class Client:
    def __init__(self, fail_times):
        self.fail_times, self.calls = fail_times, 0

    def call(self, action, **kw):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise TimeoutError('controller busy switching')
        return {'lease': 'L%d' % self.calls}


class SwitchWait(unittest.TestCase):
    def test_waits_while_a_switch_is_in_flight_then_gets_the_lease(self):
        ns = namespace(60)
        ns['SWITCHES_IN_FLIGHT'][0] = 1          # another request is switching
        c = Client(fail_times=3)
        self.assertEqual(ns['begin_inference'](c, 'dep', False), 'L4')
        self.assertEqual(c.calls, 4)

    def test_no_switch_in_flight_fails_at_once(self):
        ns = namespace(60)
        c = Client(fail_times=1)
        with self.assertRaises(TimeoutError):
            ns['begin_inference'](c, 'dep', False)
        self.assertEqual(c.calls, 1)

    def test_the_switching_request_itself_never_waits_and_is_counted_only_while_it_runs(self):
        ns = namespace(60)
        seen = []
        class Spy(Client):
            def call(self, action, **kw):
                seen.append(ns['SWITCHES_IN_FLIGHT'][0])
                return super().call(action, **kw)
        c = Spy(fail_times=1)
        with self.assertRaises(TimeoutError):
            ns['begin_inference'](c, 'dep', True)
        self.assertEqual((seen, ns['SWITCHES_IN_FLIGHT'][0]), ([1], 0))

    def test_gives_up_after_the_wait_limit(self):
        ns = namespace(0)
        ns['SWITCHES_IN_FLIGHT'][0] = 1
        c = Client(fail_times=100)
        with self.assertRaises(TimeoutError):
            ns['begin_inference'](c, 'dep', False)


if __name__ == '__main__':
    unittest.main()
