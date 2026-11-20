"""The router's /v1/models application_context follows each model's real llama-server context (owner 2026-11-19):
--ctx-size or LLAMA_ARG_CTX_SIZE from the Deployment scaled 100K per 128K, looked up through the public alias, 100000 when unknown."""
import ast
import pathlib
import threading
import time
import unittest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'manifests/10-infrastructure/llm/llm-router-gpu-controller.yml'
NAMES = ('server_context', 'server_vision', 'deployment_facts', 'model_list', 'application_budget')
CONSTS = ('DEPLOYMENT_CONTEXT_TTL', 'DEPLOYMENT_CONTEXT', 'DEPLOYMENT_CONTEXT_LOCK', 'APPLICATION_CONTEXT_RATIO')


def namespace(deployments):
    docs = yaml.safe_load_all(MANIFEST.read_text())
    config = next(d for d in docs if d and d.get('kind') == 'ConfigMap' and d.get('metadata', {}).get('name') == 'llm-router-app')
    tree = ast.parse(config['data']['router.py'])
    body = [n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in CONSTS for t in n.targets)]
    body += [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in NAMES]
    calls = []
    def deploy(name):
        calls.append(name)
        if name not in deployments:
            raise RuntimeError('not found')
        return {'spec': {'template': {'spec': {'containers': [deployments[name]]}}}}
    ns = {'threading': threading, 'time': time, 'deploy': deploy, 'DEFAULT_APPLICATION_CONTEXT': 100000,
          'MODELS': {'big-q': {'deployment': 'd-big'}, 'small': {'deployment': 'd-small'}, 'mm-x': {'deployment': 'd-mm', 'application_context': 65536},
                     'gone': {'deployment': 'd-gone'}},
          'MODEL_ALIASES': {'big': 'big-q'},
          'VISIBLE_MODELS': {'active-model': 'Active', 'big': 'Big', 'small': 'Small', 'mm-x': 'Managed', 'gone': 'Gone'}}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(MANIFEST), 'exec'), ns)
    return ns, calls


class Context(unittest.TestCase):
    def test_application_context_is_the_served_context(self):
        ns, calls = namespace({'d-big': {'args': ['--ctx-size', '131072']},
                               'd-small': {'env': [{'name': 'LLAMA_ARG_CTX_SIZE', 'value': '262144'}], 'args': ['--mmproj', '/models/p.gguf']},
                               'd-mm': {'args': ['--alias', 'mm-x']}, 'd-gone': {'args': ['--ctx-size', '100000']}})
        rows = {r['id']: r['application_context'] for r in ns['model_list']()['data']}
        self.assertEqual(rows, {'active-model': 100000, 'big': 100000, 'small': 200000, 'mm-x': 65536, 'gone': 100000})
        vision = {r['id']: r['vision'] for r in ns['model_list']()['data']}
        self.assertEqual(vision, {'active-model': None, 'big': False, 'small': True, 'mm-x': False, 'gone': False})
        self.assertEqual(ns['application_budget'](65536), 65536)
        self.assertEqual(ns['application_budget'](163840), 125000)
        before = len(calls)
        ns['model_list']()
        self.assertEqual(len(calls), before)  # cached


if __name__ == '__main__':
    unittest.main()
