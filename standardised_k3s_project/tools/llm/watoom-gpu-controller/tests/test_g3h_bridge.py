import importlib.util
import json
import hashlib
import sqlite3
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

FILES=Path(__file__).resolve().parents[4]/'ansible/roles/llm-model-lab/files'
JOB='20261012T120000Z-12345678'


class BridgeTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('g3h_bridge',FILES/'opencode_mesh_bridge.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name)
        self.bridge=module.Bridge.__new__(module.Bridge)
        self.bridge.state=root/'state';self.bridge.state.mkdir()
        self.spool=root/'jobs';self.spool.mkdir()
        for state in ('pending','running','complete','failed'):(self.spool/state).mkdir()
        assets=root/'assets';assets.mkdir()
        self.bridge.c={'job_root':str(self.spool),'asset_root':str(assets)}
        self.submissions=0
        self.lose_reply=False
        def write(path,value):Path(path).write_text(json.dumps(value))
        def find(c,jid):
            for state in ('pending','running','complete','failed'):
                path=self.spool/state/jid
                if path.exists():return path
            raise ValueError('unknown job')
        def submit(c,args):
            self.submissions+=1
            path=self.spool/'pending'/JOB;path.mkdir()
            write(path/'request.json',{'output_dir':args.output_dir,'created_at':'now'})
            write(path/'status.json',{'job_id':JOB,'state':'pending'})
            if self.lose_reply:raise OSError('lost submission acknowledgement')
            print('JOB_ID='+JOB)
        self.bridge.pipeline=SimpleNamespace(write=write,now=lambda:'now',submit=submit,find_job=find)
        self.request={'operation':'submit','prompt':'A cube','name':'test','request_id':'one-proof'}

    def tearDown(self):self.tmp.cleanup()

    def test_reconnect_same_request_submits_exactly_once(self):
        first=self.bridge.execute(self.request)
        second=self.bridge.execute(self.request)
        self.assertEqual(first['job_id'],second['job_id'])
        self.assertTrue(second['idempotent'])
        self.assertEqual(self.submissions,1)

    def test_lost_reply_after_durable_submit_reconciles(self):
        self.lose_reply=True
        with self.assertRaises(OSError):self.bridge.execute(self.request)
        result=self.bridge.execute(self.request)
        self.assertEqual(result['job_id'],JOB)
        self.assertEqual(self.submissions,1)

    def test_different_arguments_same_key_rejected(self):
        self.bridge.execute(self.request)
        with self.assertRaisesRegex(RuntimeError,'different arguments'):
            self.bridge.execute({**self.request,'prompt':'A sphere'})
        self.assertEqual(self.submissions,1)

    def test_unknown_receipt_never_submits_second_job(self):
        def fail(*args):raise OSError('interrupted before commit')
        self.bridge.pipeline.submit=fail
        with self.assertRaises(OSError):self.bridge.execute(self.request)
        with self.assertRaisesRegex(RuntimeError,'unknown outcome'):self.bridge.execute(self.request)
        self.assertEqual(self.submissions,0)

    def test_existing_async_schema_remains_supported(self):
        self.bridge.execute({k:v for k,v in self.request.items() if k!='request_id'})
        self.assertEqual(self.submissions,1)



    def checkpoint_fixture(self, request=None):
        request = request or self.request
        database = Path(self.tmp.name) / 'native.sqlite'
        with sqlite3.connect(database) as db:
            db.execute('CREATE TABLE IF NOT EXISTS _watoom_outbox(body TEXT, state TEXT)')
            arguments = {k:v for k,v in request.items() if k != 'operation'}
            digest = hashlib.sha256(json.dumps(arguments,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
            body = {'version':2,'seq':1,'kind':'checkpoint','job':'gpu:session:'+request['request_id'],
                    'id':'a'*64,'scope':{'project':'p','repository':'r','agent':'a'},
                    'content':json.dumps({'phase':'GPU_HANDOVER_PENDING','requestID':request['request_id'],'inputDigest':digest})}
            db.execute('INSERT INTO _watoom_outbox VALUES (?,?)',(json.dumps(body),'pending'))
        self.bridge.config = {'checkpoint_databases':{'1001':str(database)}}
        return database

    def test_native_peer_requires_committed_checkpoint_before_submit(self):
        database=self.checkpoint_fixture()
        with sqlite3.connect(database) as db:db.execute('DELETE FROM _watoom_outbox')
        with self.assertRaisesRegex(PermissionError,'checkpoint not found'):
            self.bridge.execute(self.request,peer_uid=1001)
        self.assertEqual(self.submissions,0)

    def test_native_checkpoint_allows_exactly_once_and_records_scope(self):
        self.checkpoint_fixture()
        self.bridge.execute(self.request,peer_uid=1001)
        self.bridge.execute(self.request,peer_uid=1001)
        allocations=[p for p in self.bridge.state.glob('test-*.json')]
        self.assertEqual(json.loads(allocations[0].read_text())['native_checkpoint']['scope']['project'],'p')
        self.assertEqual(self.submissions,1)

    def test_native_checkpoint_cannot_authorize_changed_arguments(self):
        self.checkpoint_fixture()
        with self.assertRaises(PermissionError):
            self.bridge.execute({**self.request,'prompt':'different'},peer_uid=1001)
        self.assertEqual(self.submissions,0)


if __name__=='__main__':unittest.main()
