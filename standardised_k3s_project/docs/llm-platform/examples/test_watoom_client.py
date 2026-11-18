import io,json,pathlib,sys,unittest,urllib.error
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).parent))
from watoom_client import NativeClient,APIError
class ClientTests(unittest.TestCase):
    def test_info_and_native_prompt_are_distinct_contracts(self):
        seen=[]
        def open_(request,timeout):
            seen.append(request);return io.BytesIO(b'{"data":{"id":"fixture"}}')
        client=NativeClient("https://example.invalid","fixture-only")
        with patch('urllib.request.urlopen',side_effect=open_):
            client.info();client.prompt('ses_fixture','fixture input','msg_fixture')
        self.assertTrue(seen[0].full_url.endswith('/api/info'))
        self.assertTrue(seen[1].full_url.endswith('/api/session/ses_fixture/prompt'))
        self.assertEqual(json.loads(seen[1].data),{'text':'fixture input','resume':True,'id':'msg_fixture'})
        self.assertTrue(seen[0].get_header('Authorization').startswith('Basic '))
    def test_create_schema_and_error_without_retry(self):
        client=NativeClient("http://localhost:4096","fixture-only")
        with patch('urllib.request.urlopen',return_value=io.BytesIO(b'{"data":{}}')) as opened:
            client.create_session('/example/project','fixture')
            body=json.loads(opened.call_args.args[0].data)
            self.assertEqual(body['location'],{'directory':'/example/project'})
            self.assertEqual(body['model'],{'providerID':'watoom','id':'swift-qwen38-coder'})
        with patch('urllib.request.urlopen',side_effect=urllib.error.HTTPError('x',503,'busy',{},None)) as opened:
            with self.assertRaises(APIError):client.prompt('ses_fixture','x')
            opened.assert_called_once()
    def test_url_credentials_and_non_native_paths_rejected(self):
        with self.assertRaises(ValueError):NativeClient('https://user:pass@example.invalid','fixture')
        with self.assertRaises(ValueError):NativeClient('https://example.invalid','fixture').request('GET','/v1/models')
if __name__=='__main__':unittest.main()
