import io,json,socket,threading,tempfile,unittest
from pathlib import Path
from broker_service import Client,GENERATION_BROKER_TIMEOUT
class Deadline(unittest.TestCase):
 def test_outer_deadline_covers_both_controller_switches_and_render(self):
  self.assertGreater(GENERATION_BROKER_TIMEOUT,2*1800+600+30)
 def test_generation_client_uses_budget_and_preserves_wire_contract(self):
  from unittest.mock import patch,MagicMock
  connection=MagicMock()
  connection.__enter__.return_value=connection
  connection.makefile.return_value.readline.return_value=b'{"result":{"verified":true}}'
  with patch("broker_service.socket.socket",return_value=connection):
   self.assertEqual(Client("/fixture")("generate",{"id":"a","revision":"b"},{"prompt":"bench"}),{"verified":True})
  connection.settimeout.assert_called_once_with(GENERATION_BROKER_TIMEOUT)
  payload=json.loads(connection.sendall.call_args.args[0])
  self.assertEqual(payload["request"],{"prompt":"bench"})
 def test_registration_keeps_existing_deadline(self):
  from unittest.mock import patch,MagicMock
  connection=MagicMock();connection.__enter__.return_value=connection
  connection.makefile.return_value.readline.return_value=b'{"result":{}}'
  with patch("broker_service.socket.socket",return_value=connection):
   Client("/fixture")("register",{"id":"a","revision":"b"})
  connection.settimeout.assert_called_once_with(1800)
