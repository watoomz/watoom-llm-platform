import multiprocessing as mp
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from gateway import ExclusiveStore, Gateway, Server, request
from controller import Conflict, Unsafe

def hold_lock(root, ready, release):
    store=ExclusiveStore(root)
    with store.exclusive():
        ready.set()
        release.wait(5)

def measure_lock(root, q, attempting):
    s=ExclusiveStore(root)
    start=time.monotonic()
    attempting.set()
    with s.exclusive():
        q.put(time.monotonic()-start)

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
    def tearDown(self):
        self.tmp.cleanup()
    def test_persisted_state_multiple_gateway_instances(self):
        a=Gateway(self.root); g=a.handle({'action':'begin','job':'j'})['generation']
        b=Gateway(self.root)
        self.assertEqual(b.handle({'action':'status'})['phase'],'acquiring')
        with self.assertRaises(Conflict): b.handle({'action':'begin','job':'j2'})
        b.handle({'action':'activate','job':'j','generation':g})
        a.handle({'action':'restore','job':'j','generation':g})
        self.assertEqual(Gateway(self.root).handle({'action':'status'})['phase'],'qwen-ready')
    def test_requires_exclusive_lock(self):
        s=ExclusiveStore(self.root)
        with self.assertRaises(Unsafe):s.load()
    def test_cross_process_mutex(self):
        ready=mp.Event(); release=mp.Event(); q=mp.Queue()
        a=mp.Process(target=hold_lock,args=(self.root,ready,release))
        a.start()
        self.assertTrue(ready.wait(3))
        attempting=mp.Event()
        b=mp.Process(target=measure_lock,args=(self.root,q,attempting)); b.start()
        try:
            self.assertTrue(attempting.wait(3))
            time.sleep(.15); self.assertTrue(q.empty())
        finally:
            release.set(); a.join(3); b.join(3)
        self.assertEqual(a.exitcode,0);self.assertEqual(b.exitcode,0)
        self.assertGreater(q.get(timeout=2),.1)
    def test_socket_auth_rejects_other_uid(self):
        path=self.root/'gateway.sock';srv=Server(path,Gateway(self.root),[os.getuid()+123456])
        t=threading.Thread(target=srv.serve_forever,daemon=True);t.start()
        try:self.assertEqual(request(path,{'action':'status'}).get('error'),'permission denied')
        finally:srv.shutdown();srv.server_close()
    def test_socket_lifecycle_and_no_remote_recovery(self):
        path=self.root/'gateway.sock';srv=Server(path,Gateway(self.root),[os.getuid()])
        t=threading.Thread(target=srv.serve_forever,daemon=True);t.start()
        try:
            self.assertEqual(request(path,{'action':'status'})['result']['phase'],'qwen-ready')
            self.assertEqual(request(path,{'action':'recover','owner_confirmed_ended':True})['error'],'ValueError')
            self.assertEqual(request(path,{'action':'begin','job':'job'})['result']['generation'],1)
            self.assertEqual(request(path,{'action':'can-use-qwen'})['error'],'Conflict')
        finally:srv.shutdown();srv.server_close()
    def test_unknown_actuator_blocks_restore(self):
        g=Gateway(self.root); gen=g.handle({'action':'begin','job':'a'})['generation']
        g.handle({'action':'activate','job':'a','generation':gen})
        g.actuator.pending=True
        with self.assertRaises(Unsafe):g.handle({'action':'restore','job':'a','generation':gen})
        self.assertEqual(g.handle({'action':'status'})['phase'],'recovery-required')
if __name__=='__main__':unittest.main()
