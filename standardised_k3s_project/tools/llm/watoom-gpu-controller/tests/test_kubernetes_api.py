import io, json, unittest
from kubernetes_api import DeploymentAPI, APIError

class Response:
    def __init__(self, body): self.body=body
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,n):return json.dumps(self.body).encode()

class Tests(unittest.TestCase):
    def setUp(self):
        self.sent=[]
        def record(req,timeout):
            self.sent.append((req.full_url,req.get_method(),req.data,req.get_header('Content-type')))
            return Response({'metadata':{'uid':'abc','resourceVersion':'2'},'spec':{'replicas':0}})
        self.api=DeploymentAPI(base_url='https://kubernetes.default.svc',namespace='llama-cpp',token='test',ca_file='/unused',allowed=['llama-cpp-llama-mesh'],opener=record)
    def test_get(self):
        self.api.get('llama-cpp-llama-mesh');self.assertEqual(self.sent[0][1],'GET')
    def test_disallowed(self):
        with self.assertRaises(APIError):self.api.get('llama-cpp-swift-qwen38-coder')
        self.assertEqual(self.sent,[])
    def test_patch_conditions(self):
        p=[{'op':'test','path':'/metadata/uid','value':'abc'},{'op':'test','path':'/metadata/resourceVersion','value':'1'},{'op':'replace','path':'/spec/replicas','value':0}]
        self.api.patch('llama-cpp-llama-mesh',p);self.assertEqual(self.sent[0][1],'PATCH')
        self.assertEqual(self.sent[0][3],'application/json-patch+json')
    def test_unconditional_rejected(self):
        with self.assertRaises(ValueError):self.api.patch('llama-cpp-llama-mesh',[{'op':'replace','path':'/spec/replicas','value':0}])
        self.assertEqual(self.sent,[])
    def test_outside_paths_rejected(self):
        p=[{'op':'test','path':'/metadata/uid','value':'abc'},{'op':'test','path':'/metadata/resourceVersion','value':'1'},{'op':'replace','path':'/spec/template','value':{}}]
        with self.assertRaises(ValueError):self.api.patch('llama-cpp-llama-mesh',p)
    def test_bad_namespace(self):
        with self.assertRaises(ValueError):DeploymentAPI(base_url='https://k8s',namespace='../x',token='t',ca_file='ca',allowed=['x'])
if __name__=='__main__':unittest.main()
