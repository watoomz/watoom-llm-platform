import unittest
from idle_streams import classify,key,notification,NonIdleStreams,closed_unqualified
class StreamTests(unittest.TestCase):
 def test_only_native_heartbeat_frames_qualify(self):
  self.assertTrue(classify(b'd\r\n: heartbeat\n\n\r\n'));self.assertTrue(classify(b': heartbeat\n\n'))
  for value in [b'data: work\n\n',b'GET /api/session',b': heartbeat\n\nrequest',b'',b'0\r\n\r\n']:self.assertFalse(classify(value))
 def test_only_exact_established_ipv4_app_tuple(self):
  self.assertEqual(key({'local':'49002A0A:1000','remote':'01002A0A:AC5E','state':'01'}),('10.242.0.73',4096,'10.242.0.1',44126))
  with self.assertRaises(RuntimeError):key({'local':'49002A0A:1000','remote':'01002A0A:AC5E','state':'08'})

 def test_only_inspected_empty_skill_notification(self):
  self.assertTrue(notification(b'data: {"id":"evt_fixture","type":"skill.updated","data":{}}\n\n'))
  self.assertFalse(notification(b'data: {"type":"session.updated","data":{}}\n\n'))
  self.assertFalse(notification(b'data: {"type":"skill.updated","data":{"command":"do work"}}\n\n'))

 def test_only_naturally_closed_unqualified_connections_allow_retry(self):
  c=dict(local='49002A0A:1000',remote='01002A0A:AC5E',state='01')
  e=NonIdleStreams({key(c):dict(heartbeats=0,other_server_payloads=1,client_payloads=1)})
  self.assertFalse(closed_unqualified(e,dict(connections=[c],processes=[])))
  self.assertFalse(closed_unqualified(e,dict(connections=[],processes=[dict(pid=2)])))
  self.assertTrue(closed_unqualified(e,dict(connections=[],processes=[])))

 def test_only_inspected_empty_provider_notification(self):
  self.assertTrue(notification(b'data: {"type":"provider.updated","data":{}}\n\n'))
  self.assertFalse(notification(b'data: {"type":"provider.updated","data":{"command":"run"}}\n\n'))
