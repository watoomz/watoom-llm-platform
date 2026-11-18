import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

FILES=Path(__file__).resolve().parents[4]/'ansible/roles/llm-model-lab/files'


class MCPTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('g3h_mcp',FILES/'watoom-llama-mesh.py')
        self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)

    def test_generate_keeps_llm_idle_until_completed_and_submits_once(self):
        calls=[];statuses=iter(['running','complete'])
        class Socket:
            def __init__(self,*args):pass
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def settimeout(self,*args):pass
            def connect(self,*args):pass
            def sendall(self,payload):self.request=json.loads(payload)
            def makefile(self,*args):
                operation=self.request['operation'];calls.append(self.request)
                if operation=='submit':result={'job_id':'proof-job'}
                elif operation=='status':result={'state':next(statuses)}
                elif operation=='retrieve':result={'artifacts':{},'manifest':{}}
                else:raise AssertionError(operation)
                return io.BytesIO(json.dumps({'ok':True,'result':result}).encode()+b'\n')
        with tempfile.TemporaryDirectory() as directory:
            real_path=Path
            def mapped(value):
                return real_path(directory) if value=='/workspace/.watoom/llama-mesh' else real_path(value)
            with patch.object(self.module.socket,'socket',Socket),patch.object(self.module.time,'sleep'),patch.object(self.module,'Path',side_effect=mapped):
                result=self.module.call('generate',{'prompt':'A cube','request_id':'one-proof'})
        self.assertEqual([call['operation'] for call in calls],['submit','status','status','retrieve'])
        self.assertEqual(calls[0]['request_id'],'one-proof')
        self.assertEqual(result['workspace_paths'],{})

    def test_generate_requires_idempotency_key_existing_submit_remains(self):
        tools={tool['name']:tool for tool in self.module.TOOLS}
        self.assertIn('request_id',tools['generate']['inputSchema']['required'])
        self.assertEqual(tools['submit']['inputSchema']['required'],['prompt'])
        self.assertIn('status',tools)


if __name__=='__main__':unittest.main()
