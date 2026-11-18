"""Tests the router's embedded reasoning-level performance aggregation without starting a server."""
import ast
import collections
import json
import pathlib
import threading
import time
import unittest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'manifests/10-infrastructure/llm/llm-router.yml'


def performance_namespace():
    docs = yaml.safe_load_all(MANIFEST.read_text())
    config = next(d for d in docs if d and d.get('kind') == 'ConfigMap' and d.get('metadata', {}).get('name') == 'llm-router-app')
    source = config['data']['router.py']
    tree = ast.parse(source)
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in ('record_perf', 'performance_summary', 'sse_has_generated_output')]
    selected += [node for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ('PERF_WINDOW_SECONDS', 'PERF_EVENTS', 'PERF_LOCK') for t in node.targets)]
    namespace = {'collections': collections, 'deque': collections.deque, 'json': json, 'threading': threading, 'time': time}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(MANIFEST), 'exec'), namespace)
    return namespace


class RouterPerformanceTests(unittest.TestCase):
    def test_ttft_parser_ignores_role_only_chunks_until_generated_output(self):
        ns = performance_namespace()
        has_output = ns['sse_has_generated_output']
        self.assertFalse(has_output(b'data: {"choices":[{"delta":{"role":"assistant"}}]}'))
        self.assertFalse(has_output(b'data: [DONE]'))
        self.assertTrue(has_output(b'data: {"choices":[{"delta":{"content":"hello"}}]}'))
        self.assertTrue(has_output(b'data: {"choices":[{"delta":{"tool_calls":[{"index":0}]}}]}'))

    def test_reasoning_levels_have_observed_percentiles_and_explicit_missing_token_rates(self):
        ns = performance_namespace()
        ns['record_perf']('low', 200, 100, 25)
        ns['record_perf']('low', 503, 300, None)
        ns['record_perf']('custom-level', 200, 200, 50)
        summary = ns['performance_summary']()
        self.assertEqual(2, summary['levels']['low']['requests'])
        self.assertEqual(100, summary['levels']['low']['latency_p50_ms'])
        self.assertEqual(300, summary['levels']['low']['latency_p95_ms'])
        self.assertEqual(25, summary['levels']['low']['ttft_p50_ms'])
        self.assertEqual(1, summary['levels']['low']['http_503'])
        self.assertIsNone(summary['levels']['low']['generation_tokens_per_second'])
        self.assertEqual(1, summary['levels']['other']['requests'])
        self.assertEqual(0, summary['levels']['medium']['requests'])


if __name__ == '__main__':
    unittest.main()
