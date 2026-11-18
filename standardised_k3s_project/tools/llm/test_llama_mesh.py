import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import llama_mesh as m

TRIANGLE='v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n'

class MeshTests(unittest.TestCase):
    def test_complete_json_and_markdown(self):
        raw=json.dumps({'model':'llama-mesh-q8','choices':[{'finish_reason':'stop','message':{'content':'Here is a mesh:\n```obj\n'+TRIANGLE+'```'}}]})
        text,model=m.extract_response(raw);self.assertEqual(model,'llama-mesh-q8');self.assertEqual(len(m.parse_obj(text)['faces']),1)
    def test_truncated_response_rejected(self):
        for reason in ['length',None,'tool_calls']:
            with self.assertRaises(m.MeshError):m.extract_response(json.dumps({'choices':[{'finish_reason':reason,'message':{'content':TRIANGLE}}]}))
    def test_negative_indices(self):
        self.assertEqual(m.parse_obj(TRIANGLE.replace('f 1 2 3','f -3 -2 -1'))['faces'],[[0,1,2]])
    def test_invalid_geometry(self):
        for text in [TRIANGLE.replace('f 1 2 3','f 1 2 4'),TRIANGLE.replace('f 1 2 3','f 0 2 3'),TRIANGLE.replace('v 1 0 0','v nan 0 0'),TRIANGLE.replace('f 1 2 3','f 1 2 2'),TRIANGLE.replace('v 0 1 0','v 2 0 0'),TRIANGLE+'f 3 2 1\n','No mesh.']:
            with self.subTest(text=text),self.assertRaises(m.MeshError):m.parse_obj(text)
    def test_multiple_mesh_blocks_rejected(self):
        with self.assertRaises(m.MeshError):m.parse_obj('```obj\n'+TRIANGLE+'```\n```obj\n'+TRIANGLE+'```')
    def test_invalid_input_creates_no_asset(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg={'output_root':tmp,'model':'llama-mesh-q8','size_cm':100}
            with self.assertRaises(m.MeshError):m.save_run('not geometry',cfg,'bad')
            self.assertEqual(list(Path(tmp).iterdir()),[])
    def test_unique_run_directories_and_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg={'output_root':tmp,'model':'llama-mesh-q8','size_cm':100}
            x=m.save_run(TRIANGLE,cfg,'../../same');y=m.save_run(TRIANGLE,cfg,'../../same');self.assertNotEqual(x,y);self.assertEqual(x.parent,Path(tmp));self.assertEqual(json.loads((x/'manifest.json').read_text())['model'],None)
    @patch.object(m, "CONTROLLER_CONFIG", Path("/nonexistent/offline-test-controller.json"))
    def test_generation_requires_explicit_idle_confirmation(self):
        class Args:confirm_idle=False
        with patch('llama_mesh.subprocess.run') as run,patch('llama_mesh.request_json') as request:
            with self.assertRaises(m.MeshError):m.generate(Args(),{})
            run.assert_not_called();request.assert_not_called()
    @patch.object(m, "CONTROLLER_CONFIG", Path("/nonexistent/offline-test-controller.json"))
    def test_generation_rejects_busy_backend_before_post(self):
        class Args:confirm_idle=True
        cfg={'namespace':'llama-cpp','backend_service':'llama-cpp-llama-mesh'}
        service=type('Result',(),{'stdout':json.dumps({'spec':{'clusterIP':'10.0.0.1'}})})()
        with patch('llama_mesh.subprocess.run',return_value=service),patch('llama_mesh.request_json',return_value={'status':'ok','slots_processing':1}) as request:
            with self.assertRaises(m.MeshError):m.generate(Args(),cfg)
            request.assert_called_once_with('http://10.0.0.1:8000/health')
    @patch.object(m, "CONTROLLER_CONFIG", Path("/nonexistent/offline-test-controller.json"))
    def test_generation_rejects_wrong_loaded_model_before_post(self):
        class Args:confirm_idle=True
        cfg={'namespace':'llama-cpp','backend_service':'llama-cpp-llama-mesh','model':'llama-mesh-q8'}
        service=type('Result',(),{'stdout':json.dumps({'spec':{'clusterIP':'10.0.0.1'}})})()
        with patch('llama_mesh.subprocess.run',return_value=service),patch('llama_mesh.request_json',side_effect=[{'status':'ok'},{'data':[{'id':'wrong-model'}]}]) as request:
            with self.assertRaises(m.MeshError):m.generate(Args(),cfg)
            self.assertEqual(request.call_count,2)
    def test_controller_managed_generation_cannot_contact_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker=Path(tmp)/"controller.json";marker.write_text("{}")
            with patch.object(m, "CONTROLLER_CONFIG", marker), patch("llama_mesh.subprocess.run") as run, patch("llama_mesh.request_json") as request:
                with self.assertRaisesRegex(m.MeshError, "authorized OpenCode"):
                    m.generate(None,{})
                run.assert_not_called();request.assert_not_called()

    def test_prepare_cannot_escape_output_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(m.MeshError):m.prepare(Path(tmp),{'output_root':tmp})

if __name__=='__main__':unittest.main()
