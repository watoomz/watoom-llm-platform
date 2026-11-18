#!/usr/bin/env python3
"""Tickets board UI pod (stdlib only). No access to the ticket store or the Discord webhooks: every operation goes to the
root broker over a Unix socket (same split as tools/skill-editor).

Who is who is decided here, never by the client (kanban-design.md 5):
- the owner signs in with the password (file readable only by the UI group) and gets a long-lived (~10y) in-memory
  session cookie, so logging in once keeps the owner signed in indefinitely on that browser; a pod restart still
  clears it (sessions are in-memory, not persisted) since that is a rare event, not a routine one. Every cookie POST
  needs Origin == --origin and the per-session X-CSRF-Token;
- an agent sends "Authorization: Bearer <token>"; the token's sha256 is looked up in the tokens file
  ({"<sha256 hex>": "<agent id>"}, re-read when it changes). A token never yields the owner role, and a bearer request must not
  carry a session cookie. A client-supplied "by" is ignored.
GET /api/summary (counts only) needs no login, for the Glance widget.
"""
import argparse
import hashlib
import hmac
import json
import re
import secrets
import socket
import threading
import time
import urllib.parse
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WEB = Path(__file__).parent / "web"
MAX_BODY = 16 * 1024
SESSION_SECONDS = 10 * 365 * 24 * 3600  # owner asked not to be logged out routinely; a pod restart still clears sessions (in-memory)
COOKIE = "tb_session"
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'self'; "
       "object-src 'none'; base-uri 'none'; form-action 'self'")
TICKET_PATH = re.compile(r"/api/tickets/(T-\d{1,6})(?:/(move|note|edit|change-request)(?:/(\d{1,4}))?)?")
CODES = {"invalid": 400, "forbidden": 403, "notfound": 404, "conflict": 409}


class BrokerError(Exception):
    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


class Broker:
    def __init__(self, path):
        self.path = path

    def __call__(self, request):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(30)
            s.connect(self.path)
            s.sendall(json.dumps(request).encode() + b"\n")
            raw = s.makefile("rb").readline(4 * 1024 * 1024)
        response = json.loads(raw)
        if "error" in response:
            raise BrokerError(response["error"], response.get("code"))
        return response["result"]


class Tokens:
    """sha256(token) -> agent id, re-read when the file changes (a new agent token needs no pod restart)."""

    def __init__(self, path):
        self.path = Path(path) if path else None
        self.stamp = None
        self.map = {}
        self.lock = threading.Lock()

    def lookup(self, token):
        if not self.path or not token:
            return None
        with self.lock:
            try:
                st = self.path.stat()
                if (st.st_mtime_ns, st.st_size) != self.stamp:
                    raw = json.loads(self.path.read_text())
                    self.map = {k: v for k, v in raw.items() if isinstance(k, str) and isinstance(v, str)} if isinstance(raw, dict) else {}
                    self.stamp = (st.st_mtime_ns, st.st_size)
            except (OSError, ValueError):
                self.map, self.stamp = {}, None
            digest = hashlib.sha256(token.encode()).hexdigest()
            for k, v in self.map.items():
                if hmac.compare_digest(k, digest):
                    return v
        return None


class Application:
    def __init__(self, password, origin, broker, prefix="/tickets", tokens=None, owner_id="owner"):
        self.password = password
        self.origin = origin
        self.broker = broker
        self.prefix = prefix.rstrip("/")
        self.tokens = tokens or Tokens(None)
        self.owner_id = owner_id
        self.sessions = {}  # token -> (expiry, csrf)
        self.lock = threading.Lock()

    def new_session(self):
        token, csrf, now = secrets.token_urlsafe(32), secrets.token_urlsafe(32), time.time()
        with self.lock:
            for k in [k for k, v in self.sessions.items() if v[0] < now]:
                self.sessions.pop(k, None)
            self.sessions[token] = (now + SESSION_SECONDS, csrf)
        return token

    def session(self, token):
        with self.lock:
            s = self.sessions.get(token or "")
        return s if s and s[0] > time.time() else None

    def page(self, name):
        raw = (WEB / name).read_bytes()
        for attr in (b'href="/', b'src="/', b'action="/'):
            raw = raw.replace(attr, attr[:-1] + (self.prefix + "/").encode())
        return raw

    def handler(self):
        app = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "tickets-board"
            sys_version = ""

            def log_message(self, *args):
                pass

            def send(self, code, value, kind="application/json", headers=None):
                raw = json.dumps(value).encode() if kind == "application/json" else value
                self.send_response(code)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(raw)))
                for k, v in {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "same-origin",
                             "Content-Security-Policy": CSP, **(headers or {})}.items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(raw)

            def route(self):
                path = urllib.parse.urlsplit(self.path).path
                return path[len(app.prefix):] if path.startswith(app.prefix + "/") else None

            def cookie(self):
                c = SimpleCookie()
                try:
                    c.load(self.headers.get("Cookie", ""))
                except Exception:
                    pass
                return c[COOKIE].value if COOKIE in c else None

            def identify(self):
                """(actor, role, kind, csrf) or an error tuple (code, message)."""
                auth = self.headers.get("Authorization", "")
                if auth.startswith("Bearer "):
                    if self.cookie():
                        return None, (400, "a bearer request must not carry a session cookie")
                    agent = app.tokens.lookup(auth[7:].strip())
                    if not agent or agent == app.owner_id:  # a token never yields the owner role
                        return None, (401, "unknown token")
                    return (agent, "agent", "bearer", None), None
                s = app.session(self.cookie())
                if s:
                    return (app.owner_id, "owner", "cookie", s[1]), None
                return None, (401, "not signed in")

            def call(self, request, ok=200):
                try:
                    return self.send(ok, app.broker(request))
                except BrokerError as e:
                    return self.send(CODES.get(e.code, 503), {"error": str(e)[:400]})
                except Exception:
                    return self.send(503, {"error": "ticket service unavailable"})

            def do_GET(self):
                path = self.route()
                if path is None:
                    return self.send(404, {"error": "not found"})
                if path == "/login":
                    return self.send(200, app.page("login.html"), "text/html; charset=utf-8")
                if path == "/style.css":
                    return self.send(200, (WEB / "style.css").read_bytes(), "text/css")
                if path == "/api/summary":
                    return self.call({"op": "summary"})
                who, err = self.identify()
                if not who:
                    if path == "/" and err[0] == 401:
                        self.send_response(303)
                        self.send_header("Location", app.prefix + "/login")
                        self.end_headers()
                        return
                    return self.send(err[0], {"error": err[1]})
                actor, role, kind, csrf = who
                if path == "/":
                    return self.send(200, app.page("index.html"), "text/html; charset=utf-8")
                if path == "/app.js":
                    return self.send(200, (WEB / "app.js").read_bytes(), "text/javascript")
                if path == "/api/session":
                    return self.send(200, {"actor": actor, "role": role, "auth": kind, "csrf": csrf or ""})
                if path == "/api/board":
                    etag = self.headers.get("If-None-Match", "").strip('"') or None
                    try:
                        result = app.broker({"op": "board", "actor": actor, "role": role, "etag": etag})
                    except BrokerError as e:
                        return self.send(CODES.get(e.code, 503), {"error": str(e)[:400]})
                    except Exception:
                        return self.send(503, {"error": "ticket service unavailable"})
                    if result.get("not_modified"):
                        self.send_response(304)
                        self.send_header("ETag", '"%s"' % result["etag"])
                        self.send_header("Cache-Control", "no-store")
                        self.end_headers()
                        return
                    return self.send(200, result, headers={"ETag": '"%s"' % result["etag"]})
                m = TICKET_PATH.fullmatch(path)
                if m and not m.group(2):
                    return self.call({"op": "ticket", "actor": actor, "role": role, "ticket": m.group(1)})
                return self.send(404, {"error": "not found"})

            def do_POST(self):
                path = self.route()
                if path is None:
                    return self.send(404, {"error": "not found"})
                try:
                    size = int(self.headers.get("Content-Length", "0") or 0)
                except ValueError:
                    size = -1
                if path == "/login":
                    if self.headers.get("Origin") != app.origin or not 0 < size < 4096:
                        return self.send(403, {"error": "login origin rejected"})
                    value = urllib.parse.parse_qs(self.rfile.read(size).decode(errors="replace"))
                    if not hmac.compare_digest(value.get("password", [""])[0].encode(), app.password.encode()):
                        time.sleep(1)  # slow down guessing
                        return self.send(401, {"error": "invalid credentials"})
                    token = app.new_session()
                    self.send_response(303)
                    self.send_header("Location", app.prefix + "/")
                    self.send_header("Set-Cookie", "%s=%s; HttpOnly; SameSite=Strict; Path=%s/; Max-Age=%d%s" % (
                        COOKIE, token, app.prefix, SESSION_SECONDS, "; Secure" if app.origin.startswith("https:") else ""))
                    self.end_headers()
                    return
                who, err = self.identify()
                if not who:
                    return self.send(err[0], {"error": err[1]})
                actor, role, kind, csrf = who
                if kind == "cookie" and (self.headers.get("Origin") != app.origin or
                                         not hmac.compare_digest(self.headers.get("X-CSRF-Token", ""), csrf)):
                    return self.send(403, {"error": "Origin/CSRF rejected"})
                if path == "/logout":
                    with app.lock:
                        app.sessions.pop(self.cookie() or "", None)
                    self.send_response(303)
                    self.send_header("Location", app.prefix + "/login")
                    self.send_header("Set-Cookie", "%s=; HttpOnly; SameSite=Strict; Path=%s/; Max-Age=0" % (COOKIE, app.prefix))
                    self.end_headers()
                    return
                if not 0 < size <= MAX_BODY:
                    return self.send(400, {"error": "request body must be 1 byte to 16 KB of JSON"})
                try:
                    args = json.loads(self.rfile.read(size))
                    if not isinstance(args, dict):
                        raise ValueError
                except ValueError:
                    return self.send(400, {"error": "request body must be a JSON object"})
                args.pop("by", None)  # identity comes from the credential only
                if path == "/api/tickets":
                    return self.call({"op": "create", "actor": actor, "role": role, "args": args}, 201)
                m = TICKET_PATH.fullmatch(path)
                if not m or not m.group(2):
                    return self.send(404, {"error": "not found"})
                tid, verb, index = m.groups()
                if verb == "change-request" and index is not None:
                    args["index"] = int(index)
                    op = "decide"
                elif index is not None:
                    return self.send(404, {"error": "not found"})
                else:
                    op = {"move": "move", "note": "note", "edit": "edit", "change-request": "change_request"}[verb]
                return self.call({"op": op, "actor": actor, "role": role, "ticket": tid, "args": args})

        return Handler


def main():
    p = argparse.ArgumentParser()
    for flag in ("--password-file", "--origin", "--broker-socket"):
        p.add_argument(flag, required=True)
    p.add_argument("--tokens-file", default="")
    p.add_argument("--owner-id", default="owner")
    p.add_argument("--listen", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8789)
    p.add_argument("--prefix", default="/tickets")
    a = p.parse_args()
    password = Path(a.password_file).read_text().strip()
    if len(password) < 24:
        raise SystemExit("password must have at least 24 characters")
    app = Application(password, a.origin, Broker(a.broker_socket), a.prefix, Tokens(a.tokens_file), a.owner_id)
    ThreadingHTTPServer((a.listen, a.port), app.handler()).serve_forever()


if __name__ == "__main__":
    main()
