import ast
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[4]
FILES=ROOT/'ansible/roles/llm-model-lab/files'


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('g3h_pipeline',FILES/'llama_mesh_pipeline.py')
        self.pipeline=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.pipeline)
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.job=self.root/'20261012T120000Z-12345678';self.job.mkdir();(self.job/'result').mkdir()
        (self.job/'prompt.txt').write_text('A cube')
        self.c={'model_alias':'mesh','model_path':'mock.gguf','model_sha256':'mock', 'runtime':'mock',
                'primary':'qwen','mesh':'mesh','namespace':'llama-cpp','generation_timeout':1}
        self.request={'job_id':self.job.name,'name':'cube','created_at':'now','sampling':{},'output_dir':str(self.root/'asset')}

    def tearDown(self):self.tmp.cleanup()

    def test_router_and_pipeline_have_no_reachable_scale_calls(self):
        for name in ('llama_mesh_pipeline.py','gpu-controller-router.py'):
            tree=ast.parse((FILES/name).read_text())
            calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='scale']
            self.assertEqual(calls,[],name)

    def test_guard_literal_preserved_and_inference_cannot_bypass_controller(self):
        text=(FILES/'gpu-controller-router.py').read_text()
        self.assertIn('# WATOOM_MESH_EXTERNAL_GUARD_V1:',text)
        self.assertIn('gpu_controller_check(model_id,allow_request_switch)\n            target = active_only_target or ensure_model(',text)

    def test_generation_failure_restores_via_controller_once(self):
        calls=[]
        def gpu(action,**kw):
            calls.append(action)
            if action=='begin':return {'generation':1}
            if action=='status':return {'phase':'mesh-active','owner':self.job.name,'generation':1,'uncertain':False}
            return {'ok':True}
        def http(url,*args,**kw):
            if url.endswith('/v1/models'):return {'data':[{'id':'mesh'}]}
            raise TimeoutError('Mesh generation timeout')
        p=self.pipeline
        with patch.object(p,'gpu',side_effect=gpu),patch.object(p,'safe_when_idle'),patch.object(p,'obj',return_value={}),\
             patch.object(p,'url',return_value='http://mock'),patch.object(p,'http',side_effect=http),\
             patch.object(p,'health',return_value={'inference':'PASS'}),patch.object(p.signal,'signal'):
            with self.assertRaisesRegex(RuntimeError,'Mesh generation timeout'):
                p.generate(self.c,self.request,self.job)
        self.assertEqual(calls,['begin','activate','status','restore'])
        state=json.loads((self.job/'swap-state.json').read_text())
        self.assertFalse(state['restore_required'])

    def test_failed_restoration_keeps_durable_intent_no_second_attempt(self):
        calls=[]
        def gpu(action,**kw):
            calls.append(action)
            if action=='begin':return {'generation':1}
            if action=='activate':raise TimeoutError('unknown API outcome')
            if action=='status':return {'phase':'recovery-required','owner':self.job.name,'generation':1,'uncertain':True}
            if action=='restore':raise RuntimeError('barrier failed; ownership retained')
            return {'ok':True}
        p=self.pipeline
        with patch.object(p,'gpu',side_effect=gpu),patch.object(p,'safe_when_idle'),patch.object(p,'obj',return_value={}),patch.object(p.signal,'signal'):
            with self.assertRaisesRegex(RuntimeError,'ownership retained'):
                p.generate(self.c,self.request,self.job)
        self.assertEqual(calls,['begin','activate','status','restore'])
        self.assertTrue(json.loads((self.job/'swap-state.json').read_text())['restore_required'])


if __name__=='__main__':unittest.main()
