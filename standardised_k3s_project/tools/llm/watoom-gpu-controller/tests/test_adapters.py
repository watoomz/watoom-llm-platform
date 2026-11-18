import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from client import GPUClient, MeshWorkerAdapter, RouterAdapter, ControllerRejected, ControllerUnavailable
from gateway import Gateway, Server

class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/'rpc.sock'
        self.server=Server(self.path,Gateway(Path(self.tmp.name)/'state'),{os.getuid()})
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.client=GPUClient(self.path)
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)
        self.tmp.cleanup()
    def test_router_disallowed_during_mesh(self):
        router=RouterAdapter(self.client);worker=MeshWorkerAdapter(self.client)
        self.assertTrue(router.ensure_primary_available())
        generation=worker.begin('job-1')
        with self.assertRaises(ControllerRejected):router.ensure_primary_available()
        worker.activate('job-1',generation)
        with self.assertRaises(ControllerRejected):router.ensure_primary_available()
        worker.restore('job-1',generation)
        self.assertTrue(router.ensure_primary_available())
    def test_router_cannot_activate_mesh(self):
        with self.assertRaises(ControllerRejected):RouterAdapter(self.client).ensure_specialist()
    def test_stale_worker_cannot_restore(self):
        worker=MeshWorkerAdapter(self.client)
        generation=worker.begin('a');worker.activate('a',generation)
        with self.assertRaises(ControllerRejected):worker.restore('wrong',generation)
        worker.restore('a',generation)
    def test_rpc_unknown_state_fail_closed(self):
        worker=MeshWorkerAdapter(self.client)
        generation=worker.begin('a')
        with self.assertRaises(ControllerRejected):RouterAdapter(self.client).ensure_primary_available()
        self.assertEqual(worker.status()['phase'],'acquiring')
        self.assertEqual(generation,1)
    def test_no_unsafe_fallback_on_missing_socket(self):
        with self.assertRaises(ControllerUnavailable): RouterAdapter(GPUClient('/definitely/not/a/socket')).ensure_primary_available()
    def test_credential_bound_process_uid(self):
        self.assertEqual(self.path.stat().st_mode & 0o777,0o600)
    def test_input_size_checked(self):
        with self.assertRaises(ValueError):self.client.call('status',pad='x'*70000)

if __name__=='__main__':unittest.main()
