import unittest,urllib.error
from unittest.mock import patch
from native_readiness import wait
class ReadinessTests(unittest.TestCase):
 def test_async_registry_must_settle(self):
  class Fake:
   calls=0
   def request(self,path):
    if path=='/api/info':return {'version':'fixture'}
    self.calls+=1;return {'data':[] if self.calls==1 else [{'id':'original'}]}
  with patch('native_readiness.time.sleep'):self.assertEqual(wait(Fake(),['original'])[2],2)
 def test_missing_skill_is_not_ignored(self):
  class Fake:
   def request(self,path):return {'version':'fixture'} if path=='/api/info' else {'data':[]}
  with self.assertRaisesRegex(RuntimeError,'missing: original'):wait(Fake(),['original'],seconds=0)
 def test_authentication_error_is_not_retried(self):
  class Fake:
   def request(self,path):raise urllib.error.HTTPError(path,401,'unauthorised',{},None)
  with self.assertRaises(urllib.error.HTTPError):wait(Fake(),[])
