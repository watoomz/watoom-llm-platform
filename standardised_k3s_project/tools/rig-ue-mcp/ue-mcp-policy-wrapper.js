#!/usr/bin/env node
// Policy wrapper in front of the stdio ue-mcp server (db-lyon/ue-mcp). This is what the rig's restricted SSH
// account's authorized_keys ForceCommand runs (never ue-mcp directly), so every connection goes through one gate:
// a denied tools/call is answered locally with a policy error and never reaches ue-mcp or the editor. Runs ON THE RIG.
//
// ue-mcp reaches its actions through three call shapes, and this reads all of them:
//   micro (default)  tools/call name="tools"   arguments {action:"call", category, method, args}
//   lean / full      tools/call name=<category> arguments {action:<method>, args}   (parameters may also sit flat)
//   discovery        tools {action: guide|search|list_categories|describe}, catalog {...}, <category> {action:"describe"}
// Every call becomes an id "category.method"; the policy lists ids (or "category.*", or "*") under allow and deny, and
// deny always wins. The `flow` category runs arbitrary multi-step workflows through the bridge, which would step around a
// per-action policy, so it must be denied unless the owner decides otherwise.
//
// Usage (this is what the launcher runs, see README.md):
//   node ue-mcp-policy-wrapper.js [--policy <path>] [-- <server command> <args...>]
// Default policy file: %ProgramData%\watoom\ue-mcp-policy.json. A missing or invalid file falls back to a
// discovery-only baseline (the five read calls below), never to "allow everything".
//
// Tested only against a stand-in child process (test-ue-mcp-policy-wrapper.js), not the real server or editor.
'use strict';
const fs = require('fs');
const path = require('path');
const readline = require('readline');
const { spawn } = require('child_process');

const DEFAULT_POLICY = {
  allow: ['project.get_status', 'project.get_info', 'project.describe_action', 'project.search_tools', 'project.list_content_assets'],
  deny: [],
};
const BLOCKED_CODE = -32001;
const IDENT = /^[A-Za-z0-9_]{1,80}$/;
const GATEWAY_DISCOVERY = new Set(['guide', 'search', 'list_categories', 'describe']);

function parseArgs(argv) {
  let policyPath = process.env.ProgramData
    ? path.join(process.env.ProgramData, 'watoom', 'ue-mcp-policy.json')
    : path.join(__dirname, 'ue-mcp-policy.json');
  let serverCommand = 'npx';
  let serverArgs = ['-y', 'ue-mcp'];
  const rest = argv.slice(2);
  const sep = rest.indexOf('--');
  const flags = sep === -1 ? rest : rest.slice(0, sep);
  for (let i = 0; i < flags.length; i++) if (flags[i] === '--policy') policyPath = flags[++i];
  if (sep !== -1 && rest.length > sep + 1) {
    serverCommand = rest[sep + 1];
    serverArgs = rest.slice(sep + 2);
  }
  return { policyPath, serverCommand, serverArgs };
}

function loadPolicy(policyPath) {
  try {
    const data = JSON.parse(fs.readFileSync(policyPath, 'utf8'));
    if (!Array.isArray(data.allow)) return { ...DEFAULT_POLICY };
    return { allow: data.allow.map(String), deny: Array.isArray(data.deny) ? data.deny.map(String) : [] };
  } catch {
    return { ...DEFAULT_POLICY };
  }
}

function matches(list, id) {
  return list.some((e) => e === '*' || e === id || (e.endsWith('.*') && id.startsWith(e.slice(0, -1))));
}

// -> {id} for a classifiable action call, {discovery:true} for an informational call, or {error} when it cannot be classified
function classify(name, args) {
  name = String(name || '');
  args = args && typeof args === 'object' ? args : {};
  const action = args.action;
  if (name === 'tools') {
    if (typeof action === 'string' && GATEWAY_DISCOVERY.has(action)) return { discovery: true };
    if (action !== 'call') return { error: 'tools gateway: unknown action' };
    if (!IDENT.test(String(args.category || '')) || !IDENT.test(String(args.method || ''))) return { error: 'tools gateway: category and method are required' };
    return { id: `${args.category}.${args.method}` };
  }
  if (name === 'catalog') return { discovery: true };
  if (!IDENT.test(name)) return { error: 'invalid tool name' };
  if (typeof action !== 'string' || !IDENT.test(action)) return { error: `${name}: an action is required` };
  if (action === 'describe') return { discovery: true };
  return { id: `${name}.${action}` };
}

function decide(policy, name, args) {
  const c = classify(name, args);
  if (c.discovery) return { ok: true };
  if (c.error) return { ok: false, label: c.error };
  if (matches(policy.deny, c.id) || !matches(policy.allow, c.id)) return { ok: false, label: c.id };
  return { ok: true };
}

function checkRequest(msg, policy) {
  const batch = Array.isArray(msg) ? msg : [msg];
  const blocked = [];
  for (const m of batch) {
    if (m && typeof m === 'object' && m.method === 'tools/call') {
      const p = m.params || {};
      const d = decide(policy, p.name, p.arguments);
      if (!d.ok) blocked.push({ jsonrpc: '2.0', id: m.id, error: { code: BLOCKED_CODE, message: `call "${d.label}" is not allowed by the proxy policy` } });
    }
  }
  return { blocked, allBlocked: batch.length === blocked.length && blocked.length > 0 };
}

// A category tool whose whole category is denied or never allowed is hidden from tools/list; individual actions cannot be hidden.
function filterListPayload(obj, policy) {
  if (obj && typeof obj === 'object' && obj.result && Array.isArray(obj.result.tools)) {
    obj.result.tools = obj.result.tools.filter((t) => {
      if (!t || typeof t.name !== 'string' || t.name === 'tools' || t.name === 'catalog') return true;
      if (matches(policy.deny, `${t.name}.*`)) return false;
      return policy.allow.some((e) => e === '*' || e.startsWith(`${t.name}.`));
    });
  }
  return obj;
}

function run({ policyPath, serverCommand, serverArgs }) {
  const child = spawn(serverCommand, serverArgs, { stdio: ['pipe', 'pipe', 'inherit'], windowsHide: true });
  const toChild = readline.createInterface({ input: process.stdin });
  toChild.on('line', (line) => {
    let msg;
    try {
      msg = JSON.parse(line);
    } catch {
      process.stdout.write(JSON.stringify({ jsonrpc: '2.0', id: null, error: { code: -32700, message: 'invalid JSON-RPC' } }) + '\n');
      return;
    }
    const { blocked } = checkRequest(msg, loadPolicy(policyPath));
    if (blocked.length) {
      process.stderr.write(`[policy] blocked ${blocked.map((b) => b.error.message.match(/"([^"]*)"/)[1])}\n`);
      process.stdout.write(JSON.stringify(blocked.length === 1 ? blocked[0] : blocked) + '\n'); // a mixed batch is refused as a whole
      return;
    }
    child.stdin.write(line + '\n');
  });
  toChild.on('close', () => child.stdin.end());
  const fromChild = readline.createInterface({ input: child.stdout });
  fromChild.on('line', (line) => {
    let obj;
    try {
      obj = JSON.parse(line);
    } catch {
      process.stdout.write(line + '\n');
      return;
    }
    const policy = loadPolicy(policyPath);
    obj = Array.isArray(obj) ? obj.map((o) => filterListPayload(o, policy)) : filterListPayload(obj, policy);
    process.stdout.write(JSON.stringify(obj) + '\n');
  });
  child.on('exit', (code) => process.exit(code === null ? 1 : code));
  child.on('error', (e) => {
    process.stderr.write(`[policy] failed to spawn the server: ${e.message}\n`);
    process.exit(1);
  });
}

if (require.main === module) run(parseArgs(process.argv));
module.exports = { classify, decide, matches, loadPolicy, DEFAULT_POLICY };
