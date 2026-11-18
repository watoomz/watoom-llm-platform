#!/usr/bin/env python3
"""Call the rig's Unreal editor through the restricted ue-mcp SSH route, and start the editor first when it is not running (stdlib only).

  ue_route.py ensure [--max-wait 1200]            start the editor if needed and wait until the bridge answers (a cold start takes up to ~12 min)
  ue_route.py call 'project.get_status {}' ...    run one or more category.method {json} calls in one session

Why `ensure` polls instead of trusting editor.start_editor: start_editor launches the editor through the WatooM-UeEditorStart task (that is the
whole point of the rig's UeEditorTaskShim), but it stops waiting after about 150 s and then reports "the editor process is gone - it exited
during startup" even though the editor is still booting (seen 2026-11-14: a cold start took 12 minutes, the process was alive and responding the
whole time, the bridge on 127.0.0.1:63053 only appeared at the end). So: ask project.get_status; if editorConnected is not true, call
editor.start_editor once (ignore its failure text), then poll project.get_status until editorConnected is true or --max-wait expires.
The credentials are the ones playbooks/ue-mcp-ssh.yml stages (default /data/ai/ue-mcp-ssh); the route itself is restricted to the ue-mcp policy
wrapper, so nothing here can run anything but ue-mcp actions.
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import time

DEFAULT_KEY_DIR = "/data/ai/ue-mcp-ssh"


def ssh_command(host, port, user, key_dir):
    return ["ssh", "-i", os.path.join(key_dir, "key"), "-o", "UserKnownHostsFile=" + os.path.join(key_dir, "known_hosts"),
            "-o", "StrictHostKeyChecking=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-p", str(port), "%s@%s" % (user, host)]


def reply_failed(text, is_error=False):
    """True when a tool reply reports failure: the MCP isError flag, text starting with "Error", or JSON with success false / a non-empty error."""
    if is_error:
        return True
    s = (text or "").lstrip()
    if s.startswith("Error"):
        return True
    if "{" in s:
        try:
            d, _ = json.JSONDecoder().raw_decode(s, s.index("{"))   # the first JSON object; text after it is ignored
            if isinstance(d, dict):
                return d.get("success") is False or bool(d.get("error"))
        except ValueError:
            pass
    return '"success": false' in s or '"success":false' in s


def reply_ok(text, is_error=False):
    """True only for an explicit success: no failure signal and "success": true in the reply."""
    return not reply_failed(text, is_error) and ('"success": true' in (text or "") or '"success":true' in (text or ""))


class SshTransport:
    """One MCP stdio session over ssh. call(category, method, args, timeout) -> the text of the first content block (or raises)."""

    def __init__(self, cmd):
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        self.out = {}
        self.n = 10
        self.is_error = False
        threading.Thread(target=self._read, daemon=True).start()
        self._send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "ue_route", "version": "1"}}})
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self._wait(1, 30)

    def _read(self):
        for line in self.p.stdout:
            try:
                d = json.loads(line)
                self.out[d.get("id")] = d
            except ValueError:
                pass

    def _send(self, o):
        self.p.stdin.write(json.dumps(o) + "\n")
        self.p.stdin.flush()

    def _wait(self, i, timeout):
        t0 = time.time()
        while i not in self.out and time.time() - t0 < timeout:
            time.sleep(0.2)
        return self.out.get(i)

    def call(self, category, method, args=None, timeout=60, action="call"):
        """action "call" runs category.method(args); action "describe" returns that method's full parameter schema (the
        gateway always answers describe; the policy only filters calls). Nested params such as the Niagara toolset's
        stackInputRef are only documented there, not in the one-line tool reference."""
        self.n += 1
        arguments = {"action": action, "category": category, "method": method}
        if action == "call":
            arguments["args"] = args or {}
        self._send({"jsonrpc": "2.0", "id": self.n, "method": "tools/call", "params": {"name": "tools", "arguments": arguments}})
        d = self._wait(self.n, timeout)
        if d is None:
            raise TimeoutError("%s.%s: no reply in %ss" % (category, method, timeout))
        if "error" in d:
            raise RuntimeError("%s.%s: %s" % (category, method, json.dumps(d["error"])[:300]))
        self.is_error = bool(d["result"].get("isError"))   # the MCP error flag of the latest reply; reply_failed(text, t.is_error)
        blocks = [b["text"] for b in d["result"].get("content", []) if b.get("type") == "text"]
        # the bridge can prepend a UE_MCP_UPGRADE_AVAILABLE (or similar UE_MCP_*) notice as its own leading block,
        # pushing the real reply to content[1] -- skip any such banner block instead of always reading content[0].
        # execute_python replies lead with an "[AGENT DIRECTIVE - MANDATORY]" block (a usage banner) and carry the result
        # after it; reading the banner as the reply lost every Python result (T-0061, 2026-11-19).
        payload = next((b for b in blocks if not is_banner(b)), blocks[-1] if blocks else "")
        return payload

    def close(self):
        try:
            self.p.stdin.close()
            time.sleep(0.5)
            self.p.terminate()
        except OSError:
            pass


DAEMON_RESTART = "daemon stopped while this call was in flight"


def call_read(t, category, method, args, timeout=60, tries=3, sleep=time.sleep):
    """t.call for a READ that is safe to repeat: retried when the ue-mcp daemon restarted mid-call (JSON-RPC -32001 "The ue-mcp
    daemon stopped while this call was in flight"). Seen twice on 2026-11-19, once 15 minutes into a full foliage scan, which then
    died with nothing done (T-0052). Never use it for a write: a write's outcome is unknown after that error."""
    for i in range(tries):
        try:
            return t.call(category, method, args, timeout)
        except RuntimeError as e:
            if DAEMON_RESTART not in str(e) or i == tries - 1:
                raise
            sleep(15)


def is_banner(text):
    """A notice block the bridge puts before the real reply (upgrade notices, the execute_python directive)."""
    t = text.lstrip()
    return t.startswith(("UE_MCP_", "[AGENT DIRECTIVE", "MACHINE_DIRECTIVE="))


def editor_connected(transport_factory):
    """True when project.get_status says the editor bridge is connected. Any transport failure counts as not connected."""
    t = None
    try:
        t = transport_factory()
        text = t.call("project", "get_status", {}, 40)
        return bool(json.loads(text).get("editorConnected"))
    except Exception:
        return False
    finally:
        if t:
            t.close()


def ensure_editor(transport_factory, max_wait=1200, poll=15, sleep=time.sleep, clock=time.monotonic, log=lambda m: None):
    """Start the editor when needed and wait for the bridge. Returns {state: already-running|started|timeout, waited_s}."""
    t0 = clock()
    if editor_connected(transport_factory):
        return {"state": "already-running", "waited_s": 0}
    log("editor bridge not answering: requesting start through editor.start_editor")
    t = None
    try:
        t = transport_factory()
        text = t.call("editor", "start_editor", {}, 240)  # returns after ~150 s, often with a false 'exited during startup'
        log("start_editor said: " + text[:160].replace("\n", " "))
    except Exception as e:  # the launch itself may still have worked; the polling below decides
        log("start_editor raised: %s" % e)
    finally:
        if t:
            t.close()
    while clock() - t0 < max_wait:
        if editor_connected(transport_factory):
            return {"state": "started", "waited_s": int(clock() - t0)}
        sleep(poll)
    return {"state": "timeout", "waited_s": int(clock() - t0)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="10.99.1.44")
    ap.add_argument("--port", type=int, default=2224)
    ap.add_argument("--user", default="uemcp")
    ap.add_argument("--key-dir", default=DEFAULT_KEY_DIR)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("ensure")
    e.add_argument("--max-wait", type=int, default=1200)
    c = sub.add_parser("call")
    c.add_argument("calls", nargs="+", help="category.method {json args}")
    dsc = sub.add_parser("describe", help="print the parameter schema of category.method")
    dsc.add_argument("methods", nargs="+", help="category.method")
    a = ap.parse_args(argv)
    factory = lambda: SshTransport(ssh_command(a.host, a.port, a.user, a.key_dir))  # noqa: E731
    if a.cmd == "ensure":
        r = ensure_editor(factory, a.max_wait, log=lambda m: print(time.strftime("%H:%M:%S"), m, flush=True))
        print(json.dumps(r))
        return 0 if r["state"] != "timeout" else 2
    t = factory()
    failed = 0
    if a.cmd == "describe":
        try:
            for head in a.methods:
                cat, meth = head.split(".", 1)
                print("[%s] %s" % (head, t.call(cat, meth, None, 120, action="describe")))
        finally:
            t.close()
        return 0
    try:
        for spec in a.calls:
            head, _, js = spec.partition(" ")
            cat, meth = head.split(".", 1)
            text = t.call(cat, meth, json.loads(js or "{}"), 300)
            print("[%s] %s" % (head, text))
            if reply_failed(text, getattr(t, "is_error", False)):
                failed += 1
    finally:
        t.close()
    return 1 if failed else 0   # a failed call is a non-zero exit so a calling script or model cannot miss it


if __name__ == "__main__":
    sys.exit(main())
