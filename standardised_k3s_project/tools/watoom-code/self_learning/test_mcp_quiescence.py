import unittest,json
from unittest.mock import patch
from mcp_quiescence import quiesce,restore,endpoint,ADAPTER_SHA256
class Fake:
 def __init__(self):self.held=True;self.active={};self.is_connected=True;self.calls=[]
 def request(self,p,b=None):
  self.calls.append(p)
  if p=='/api/session/deployment-guard':return {'data':{'held':self.held}}
  if p=='/api/session/active':return {'data':self.active}
  if '/disconnect?' in p:self.is_connected=False;return
  if '/connect?' in p:self.is_connected=True;return
  return {'data':[{'name':'watoom-llama-mesh','status':{'status':'connected' if self.is_connected else 'disconnected'}}]}
 def exec(self,c,*args):return json.dumps([{'directory':'/workspace','pid':123,'start':'456','server':'watoom-llama-mesh','adapter_sha256':ADAPTER_SHA256}]).encode()
 def transport(self):return {'processes':[]}
class MCPTests(unittest.TestCase):
 def test_disconnect_recorded_before_mutation_and_idempotent_restore(self):
  m=Fake();s={'owner':'a'*64};writes=[]
  def save(v):writes.append(json.loads(json.dumps(v)));self.assertTrue(m.is_connected if len(writes)==1 else True)
  quiesce(m,s,save);self.assertFalse(m.is_connected);self.assertIn('mcp_connections',writes[0]);restore(m,s,save);self.assertTrue(m.is_connected)
  count=len([x for x in m.calls if '/connect?' in x]);restore(m,s,save);self.assertEqual(count,len([x for x in m.calls if '/connect?' in x]))
 def test_gate_required(self):
  m=Fake();m.held=False
  with self.assertRaises(RuntimeError):quiesce(m,{},lambda s:None)
  self.assertTrue(m.is_connected)
 def test_active_rejected(self):
  m=Fake();m.active={'unknown':{}}
  with self.assertRaises(RuntimeError):quiesce(m,{},lambda s:None)
  self.assertTrue(m.is_connected)
 def test_location_encoded(self):self.assertIn('location%5Bdirectory%5D=%2Fa+b',endpoint('/a b'))
