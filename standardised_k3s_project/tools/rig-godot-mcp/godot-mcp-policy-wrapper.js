#!/usr/bin/env node
// Tool-filtering wrapper around the stdio-only NPGameDev Godot MCP bridge. This is what the rig's
// restricted SSH account's authorized_keys ForceCommand actually runs (never the bridge directly),
// so every connection -- however it got in -- goes through the same policy gate as rig-unreal-mcp's
// mcp_proxy.py: default read-only (list_/read_/find_/get_ prefixes), policy.json re-read per
// request, denied tools/call requests answered locally without ever reaching the bridge/editor,
// and hidden from tools/list results. Runs ON THE RIG, not the lab -- there is no network hop here
// to gate centrally the way Nwiro's HTTP proxy does, since the bridge itself only ever speaks
// stdio (see tools/rig-godot-mcp/README.md for why).
//
// Usage (this is what goes in authorized_keys' command="...", see README):
//   node godot-mcp-policy-wrapper.js [--policy <path>] [-- <bridge command> <bridge args...>]
// Default bridge command: npx -y @npgamedev/godot-mcp-server
// Default policy file: %ProgramData%\watoom\godot-mcp-policy.json (falls back to the read-only
// default if missing or invalid -- same behaviour as mcp_proxy.py's load_policy).
//
// UNTESTED against the real editor/plugin/bridge -- only against a fake stand-in child process
// (see test-godot-mcp-policy-wrapper.js).
'use strict';
const fs = require('fs');
const path = require('path');
const readline = require('readline');
const { spawn } = require('child_process');

const DEFAULT_POLICY = { allow_prefixes: ['list_', 'read_', 'find_', 'get_'], allow_names: [], deny_names: [] };
const BLOCKED_CODE = -32001;

function parseArgs(argv) {
  let policyPath = process.env.ProgramData
    ? path.join(process.env.ProgramData, 'watoom', 'godot-mcp-policy.json')
    : path.join(__dirname, 'godot-mcp-policy.json');
  let bridgeCommand = 'npx';
  let bridgeArgs = ['-y', '@npgamedev/godot-mcp-server'];
  const rest = argv.slice(2);
  const sepIdx = rest.indexOf('--');
  const flags = sepIdx === -1 ? rest : rest.slice(0, sepIdx);
  for (let i = 0; i < flags.length; i++) {
    if (flags[i] === '--policy') policyPath = flags[++i];
  }
  if (sepIdx !== -1 && rest.length > sepIdx + 1) {
    bridgeCommand = rest[sepIdx + 1];
    bridgeArgs = rest.slice(sepIdx + 2);
  }
  return { policyPath, bridgeCommand, bridgeArgs };
}

function loadPolicy(policyPath) {
  try {
    const data = JSON.parse(fs.readFileSync(policyPath, 'utf8'));
    const policy = { ...DEFAULT_POLICY };
    for (const key of Object.keys(DEFAULT_POLICY)) {
      if (Array.isArray(data[key])) policy[key] = data[key].map(String);
    }
    return policy;
  } catch {
    return { ...DEFAULT_POLICY }; // missing or invalid policy file => the read-only default
  }
}

function toolAllowed(policy, name) {
  name = String(name || '');
  if (policy.deny_names.includes(name)) return false;
  return policy.allow_names.includes(name) || policy.allow_prefixes.some((p) => name.startsWith(p));
}

function checkRequest(msg, policy) {
  const batch = Array.isArray(msg) ? msg : [msg];
  const blocked = [];
  for (const m of batch) {
    if (m && typeof m === 'object' && m.method === 'tools/call') {
      const name = (m.params || {}).name;
      if (!toolAllowed(policy, name)) {
        blocked.push({ jsonrpc: '2.0', id: m.id, error: { code: BLOCKED_CODE, message: `tool "${name}" is not allowed by the proxy policy` } });
      }
    }
  }
  const allBlocked = batch.length === blocked.length && blocked.length > 0;
  return { blocked, allBlocked };
}

function filterListPayload(obj, policy) {
  if (obj && typeof obj === 'object' && obj.result && Array.isArray(obj.result.tools)) {
    obj.result.tools = obj.result.tools.filter((t) => t && toolAllowed(policy, t.name));
  }
  return obj;
}

function run({ policyPath, bridgeCommand, bridgeArgs }) {
  const child = spawn(bridgeCommand, bridgeArgs, { stdio: ['pipe', 'pipe', 'inherit'], windowsHide: true });

  const toChild = readline.createInterface({ input: process.stdin });
  toChild.on('line', (line) => {
    let msg;
    try {
      msg = JSON.parse(line);
    } catch {
      process.stdout.write(JSON.stringify({ jsonrpc: '2.0', id: null, error: { code: -32700, message: 'invalid JSON-RPC' } }) + '\n');
      return;
    }
    const policy = loadPolicy(policyPath);
    const { blocked, allBlocked } = checkRequest(msg, policy);
    if (blocked.length) {
      process.stderr.write(`[policy] blocked tools=${blocked.map((b) => b.error.message.match(/"([^"]*)"/)[1])}\n`);
    }
    if (allBlocked) {
      process.stdout.write(JSON.stringify(blocked.length === 1 ? blocked[0] : blocked) + '\n');
      return;
    }
    if (blocked.length) { // mixed batch: refuse as a whole rather than guess
      process.stdout.write(JSON.stringify(blocked) + '\n');
      return;
    }
    child.stdin.write(line + '\n');
  });
  toChild.on('close', () => child.stdin.end());

  const fromChild = readline.createInterface({ input: child.stdout });
  fromChild.on('line', (line) => {
    const policy = loadPolicy(policyPath);
    let obj;
    try {
      obj = JSON.parse(line);
    } catch {
      process.stdout.write(line + '\n');
      return;
    }
    obj = Array.isArray(obj) ? obj.map((o) => filterListPayload(o, policy)) : filterListPayload(obj, policy);
    process.stdout.write(JSON.stringify(obj) + '\n');
  });

  child.on('exit', (code) => process.exit(code === null ? 1 : code));
  child.on('error', (e) => {
    process.stderr.write(`[policy] failed to spawn bridge: ${e.message}\n`);
    process.exit(1);
  });
}

if (require.main === module) {
  run(parseArgs(process.argv));
}

module.exports = { loadPolicy, toolAllowed, checkRequest, filterListPayload, run, DEFAULT_POLICY, BLOCKED_CODE };
