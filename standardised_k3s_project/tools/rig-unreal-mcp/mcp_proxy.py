#!/usr/bin/env python3
"""Authenticated, tool-filtering proxy in front of an Unreal MCP endpoint reached through a reverse SSH tunnel.

  watoom-code pod --(Bearer token)--> this proxy (10.242.0.1:15354) --> 127.0.0.1:15353 (tunnel end) --> rig 127.0.0.1:5353 (Nwiro MCP)

The editor-side MCP server documents no authentication, so this proxy is the gate: it checks a bearer token, forwards only POST /mcp
(and DELETE for session end), and applies a tool policy. The policy file is re-read on every request, so changing it needs no restart.
Standard library only. Tool arguments are never logged, only method and tool names.
"""
import argparse
import hmac
import http.server
import json
import pathlib
import socketserver
import sys
import urllib.error
import urllib.request

MAX_BODY = 1 << 20
DEFAULT_POLICY = {'allow_prefixes': ['list_', 'read_', 'find_', 'get_'], 'allow_names': [], 'deny_names': []}
BLOCKED_CODE = -32001


def load_policy(path):
    policy = dict(DEFAULT_POLICY)
    try:
        data = json.loads(pathlib.Path(path).read_text())
        for key in policy:
            if isinstance(data.get(key), list):
                policy[key] = [str(x) for x in data[key]]
    except (OSError, ValueError):
        pass  # missing or invalid policy file => the read-only default
    return policy


def tool_allowed(policy, name):
    name = str(name or '')
    if name in policy['deny_names']:
        return False
    return name in policy['allow_names'] or name.startswith(tuple(policy['allow_prefixes']))


def check_request(raw, policy):
    """Return (blocked_responses, tool_names). blocked_responses is a list of JSON-RPC errors for disallowed tools/call messages."""
    msgs = json.loads(raw)
    batch = msgs if isinstance(msgs, list) else [msgs]
    blocked, names = [], []
    for m in batch:
        if not isinstance(m, dict):
            raise ValueError('invalid JSON-RPC message')
        if m.get('method') == 'tools/call':
            name = (m.get('params') or {}).get('name')
            names.append(str(name))
            if not tool_allowed(policy, name):
                blocked.append({'jsonrpc': '2.0', 'id': m.get('id'),
                                'error': {'code': BLOCKED_CODE, 'message': 'tool "%s" is not allowed by the proxy policy' % name}})
    return blocked, names, (len(batch) == len(blocked) and bool(blocked))


def filter_list_payload(obj, policy):
    if isinstance(obj, dict) and isinstance(obj.get('result'), dict) and isinstance(obj['result'].get('tools'), list):
        obj['result']['tools'] = [t for t in obj['result']['tools'] if isinstance(t, dict) and tool_allowed(policy, t.get('name'))]
    return obj


def filter_response(body, content_type, policy):
    """Hide disallowed tools from tools/list results; works for plain JSON and single-event SSE bodies."""
    try:
        if 'text/event-stream' in (content_type or ''):
            out = []
            for line in body.decode().splitlines():
                if line.startswith('data:'):
                    obj = json.loads(line[5:].strip() or 'null')
                    obj = [filter_list_payload(o, policy) for o in obj] if isinstance(obj, list) else filter_list_payload(obj, policy)
                    line = 'data: ' + json.dumps(obj)
                out.append(line)
            return ('\n'.join(out) + '\n\n').encode() if out else body
        obj = json.loads(body)
        obj = [filter_list_payload(o, policy) for o in obj] if isinstance(obj, list) else filter_list_payload(obj, policy)
        return json.dumps(obj).encode()
    except (ValueError, UnicodeDecodeError):
        return body


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = 'unreal-mcp-proxy'
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        sys.stderr.write('%s %s\n' % (self.address_string(), fmt % args))

    def _send(self, status, body=b'', content_type='application/json', extra=None):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _authorised(self):
        sent = self.headers.get('Authorization', '')
        return sent.startswith('Bearer ') and hmac.compare_digest(sent[7:].strip(), self.server.token)

    def _forward(self, method, body):
        up = urllib.request.Request(self.server.upstream, data=body, method=method)
        for h in ('Content-Type', 'Accept', 'Mcp-Session-Id', 'MCP-Protocol-Version'):
            if self.headers.get(h):
                up.add_header(h, self.headers[h])
        try:
            with urllib.request.urlopen(up, timeout=self.server.timeout) as r:
                return r.status, r.read(), r.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers
        except (urllib.error.URLError, OSError) as e:
            return 502, json.dumps({'error': 'upstream unreachable (is the rig tunnel up and the editor open?)'}).encode(), None

    def do_POST(self):
        if self.path.rstrip('/') != '/mcp':
            return self._send(404, b'{"error":"not found"}')
        if not self._authorised():
            return self._send(401, b'{"error":"unauthorised"}')
        length = int(self.headers.get('Content-Length') or 0)
        if length <= 0 or length > MAX_BODY:
            return self._send(413, b'{"error":"bad body size"}')
        raw = self.rfile.read(length)
        policy = load_policy(self.server.policy_file)
        try:
            blocked, names, all_blocked = check_request(raw, policy)
        except ValueError:
            return self._send(400, b'{"error":"invalid JSON-RPC"}')
        if blocked:
            self.log_message('blocked tools=%s', [b['error']['message'].split('"')[1] for b in blocked])
        if all_blocked:
            payload = blocked[0] if len(blocked) == 1 else blocked
            return self._send(200, json.dumps(payload).encode())
        if blocked:  # mixed batch: refuse as a whole rather than guess
            return self._send(200, json.dumps(blocked).encode())
        self.log_message('forward tools=%s', names or '-')
        status, body, headers = self._forward('POST', raw)
        ctype = headers.get('Content-Type', 'application/json') if headers else 'application/json'
        extra = {'Mcp-Session-Id': headers['Mcp-Session-Id']} if headers and headers.get('Mcp-Session-Id') else None
        self._send(status, filter_response(body, ctype, policy) if status == 200 else body, ctype, extra)

    def do_DELETE(self):
        if self.path.rstrip('/') != '/mcp' or not self._authorised():
            return self._send(401 if self.path.rstrip('/') == '/mcp' else 404, b'{"error":"denied"}')
        status, body, _ = self._forward('DELETE', None)
        self._send(status, body)

    def do_GET(self):
        self._send(405, b'{"error":"use POST"}', extra={'Allow': 'POST, DELETE'})


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def make_server(listen, port, upstream, token, policy_file, timeout=120):
    srv = Server((listen, port), Handler)
    srv.upstream, srv.token, srv.policy_file, srv.timeout = upstream, token, policy_file, timeout
    return srv


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--listen', default='10.242.0.1')
    ap.add_argument('--port', type=int, default=15354)
    ap.add_argument('--upstream', default='http://127.0.0.1:15353/mcp')
    ap.add_argument('--token-file', required=True, type=pathlib.Path)
    ap.add_argument('--policy-file', required=True, type=pathlib.Path)
    a = ap.parse_args()
    token = a.token_file.read_text().strip()
    if len(token) < 32:
        sys.exit('token must be at least 32 characters')
    make_server(a.listen, a.port, a.upstream, token, a.policy_file).serve_forever()


if __name__ == '__main__':
    main()
