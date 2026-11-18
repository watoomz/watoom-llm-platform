import http.server
import json
import pathlib
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

import mcp_proxy as p

TOKEN = 'x' * 40


class Upstream(http.server.BaseHTTPRequestHandler):
    seen = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        Upstream.seen.append(body)
        if body.get('method') == 'tools/list':
            res = {'jsonrpc': '2.0', 'id': body['id'], 'result': {'tools': [{'name': n} for n in ('list_assets', 'read_blueprint', 'delete_asset', 'edit_material', 'spawn_actor')]}}
            data = ('event: message\ndata: ' + json.dumps(res) + '\n\n').encode()
            ctype = 'text/event-stream'
        else:
            data = json.dumps({'jsonrpc': '2.0', 'id': body.get('id'), 'result': {'ok': True}}).encode()
            ctype = 'application/json'
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Mcp-Session-Id', 'sess-1')
        self.end_headers()
        self.wfile.write(data)


class ProxyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.up = http.server.HTTPServer(('127.0.0.1', 0), Upstream)
        threading.Thread(target=cls.up.serve_forever, daemon=True).start()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.policy = pathlib.Path(cls.tmp.name) / 'policy.json'
        cls.proxy = p.make_server('127.0.0.1', 0, 'http://127.0.0.1:%d/mcp' % cls.up.server_port, TOKEN, cls.policy, timeout=5)
        threading.Thread(target=cls.proxy.serve_forever, daemon=True).start()
        cls.url = 'http://127.0.0.1:%d/mcp' % cls.proxy.server_port

    @classmethod
    def tearDownClass(cls):
        cls.proxy.shutdown()
        cls.up.shutdown()
        cls.tmp.cleanup()

    def post(self, payload, token=TOKEN):
        req = urllib.request.Request(self.url, data=json.dumps(payload).encode(), method='POST', headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token} if token else {'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, r.read().decode(), r.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode(), e.headers

    def setUp(self):
        Upstream.seen.clear()
        if self.policy.exists():
            self.policy.unlink()

    def test_requires_token(self):
        self.assertEqual(401, self.post({'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}, token='')[0])
        self.assertEqual(401, self.post({'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}, token='y' * 40)[0])
        self.assertEqual([], Upstream.seen)

    def test_read_only_default_blocks_edits_and_hides_them(self):
        status, body, _ = self.post({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': 'delete_asset', 'arguments': {'path': '/Game/X'}}})
        self.assertEqual(200, status)
        self.assertEqual(p.BLOCKED_CODE, json.loads(body)['error']['code'])
        self.assertEqual([], Upstream.seen)
        status, body, headers = self.post({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/list'})
        names = [t['name'] for t in json.loads(body.split('data:', 1)[1])['result']['tools']]
        self.assertEqual(['list_assets', 'read_blueprint'], names)
        self.assertEqual('sess-1', headers['Mcp-Session-Id'])

    def test_allowlist_and_denylist_are_live(self):
        self.policy.write_text(json.dumps({'allow_names': ['edit_material', 'delete_asset'], 'deny_names': ['delete_asset']}))
        ok = self.post({'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call', 'params': {'name': 'edit_material', 'arguments': {}}})
        self.assertIn('"ok": true', ok[1])
        denied = self.post({'jsonrpc': '2.0', 'id': 5, 'method': 'tools/call', 'params': {'name': 'delete_asset', 'arguments': {}}})
        self.assertIn('error', json.loads(denied[1]))

    def test_batch_with_a_blocked_call_is_refused_as_a_whole(self):
        status, body, _ = self.post([{'jsonrpc': '2.0', 'id': 6, 'method': 'tools/call', 'params': {'name': 'read_blueprint'}},
                                    {'jsonrpc': '2.0', 'id': 7, 'method': 'tools/call', 'params': {'name': 'spawn_actor'}}])
        self.assertEqual([], Upstream.seen)
        self.assertEqual(1, len(json.loads(body)))

    def test_unreachable_upstream_and_bad_input(self):
        srv = p.make_server('127.0.0.1', 0, 'http://127.0.0.1:1/mcp', TOKEN, self.policy, timeout=2)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            req = urllib.request.Request('http://127.0.0.1:%d/mcp' % srv.server_port, data=b'{"jsonrpc":"2.0","id":1,"method":"ping"}', method='POST', headers={'Authorization': 'Bearer ' + TOKEN})
            with self.assertRaises(urllib.error.HTTPError) as c:
                urllib.request.urlopen(req, timeout=5)
            self.assertEqual(502, c.exception.code)
        finally:
            srv.shutdown()
        self.assertEqual(400, self.post_raw(b'not json'))

    def post_raw(self, data):
        req = urllib.request.Request(self.url, data=data, method='POST', headers={'Authorization': 'Bearer ' + TOKEN})
        try:
            return urllib.request.urlopen(req, timeout=5).status
        except urllib.error.HTTPError as e:
            return e.code


if __name__ == '__main__':
    unittest.main()
