#!/usr/bin/env node
'use strict';
const path = require('path');
const assert = require('assert');
const fs = require('fs');
const os = require('os');
const { spawn } = require('child_process');
const w = require('./ue-mcp-policy-wrapper.js');

const wrapper = path.join(__dirname, 'ue-mcp-policy-wrapper.js');
const fake = path.join(__dirname, 'fake-ue-mcp-child.js');
const call = (id, name, args) => ({ jsonrpc: '2.0', id, method: 'tools/call', params: { name, arguments: args } });

function run(lines, policy) {
  return new Promise((resolve, reject) => {
    const tmp = path.join(os.tmpdir(), `ue-mcp-policy-${process.pid}-${Math.random().toString(16).slice(2)}.json`);
    if (policy) fs.writeFileSync(tmp, typeof policy === 'string' ? policy : JSON.stringify(policy));
    const proc = spawn('node', [wrapper, '--policy', tmp, '--', 'node', fake]);
    let out = '';
    proc.stdout.on('data', (d) => { out += d; });
    proc.on('error', reject);
    proc.on('exit', () => { try { fs.unlinkSync(tmp); } catch {} resolve(out.trim().split('\n').filter(Boolean).map((l) => JSON.parse(l)).sort((a, b) => (Array.isArray(a) ? a[0].id : a.id) - (Array.isArray(b) ? b[0].id : b.id))); });
    for (const l of lines) proc.stdin.write(JSON.stringify(l) + '\n');
    proc.stdin.end();
  });
}
const POLICY = { allow: ['landscape.*', 'level.*', 'project.*', 'editor.*'], deny: ['editor.execute_python', 'level.delete_actor', 'flow.*'] };
const blocked = (r) => r.error && r.error.code === -32001;
const passed = (r) => r.result && r.result.echoed === 'tools/call';
const T = [];
const t = (name, fn) => T.push([name, fn]);

t('micro gateway: an allowed category.method reaches the server', async () => {
  const [r] = await run([call(1, 'tools', { action: 'call', category: 'landscape', method: 'get_slope_map', args: {} })], POLICY);
  assert(passed(r));
});
t('micro gateway: a denied method is answered locally', async () => {
  const [r] = await run([call(1, 'tools', { action: 'call', category: 'editor', method: 'execute_python', args: { code: 'x' } })], POLICY);
  assert(blocked(r)); assert(/editor\.execute_python/.test(r.error.message));
});
t('micro gateway: a category that is not allowed is refused', async () => {
  const [r] = await run([call(1, 'tools', { action: 'call', category: 'asset', method: 'list' })], POLICY);
  assert(blocked(r));
});
t('micro gateway: the flow category cannot step around the policy', async () => {
  const [r] = await run([call(1, 'tools', { action: 'call', category: 'flow', method: 'run', args: { flowName: 'x' } })], POLICY);
  assert(blocked(r));
});
t('micro gateway: discovery (guide/search/list_categories/describe) always works', async () => {
  const rs = await run(['guide', 'search', 'list_categories', 'describe'].map((a, i) => call(i + 1, 'tools', { action: a, query: 'q', category: 'asset' })), { allow: [] });
  assert(rs.every(passed));
});
t('lean/full: <category> with action is classified the same way', async () => {
  const [a, b] = await run([call(1, 'level', { action: 'place_actor', args: {} }), call(2, 'level', { action: 'delete_actor', args: {} })], POLICY);
  assert(passed(a)); assert(blocked(b));
});
t('lean/full: parameters sent flat beside action are still gated by the action', async () => {
  const [r] = await run([call(1, 'editor', { action: 'execute_python', code: 'print(1)' })], POLICY);
  assert(blocked(r));
});
t('a category tool with action describe is informational', async () => {
  const [r] = await run([call(1, 'asset', { action: 'describe', method: 'import_static_mesh' })], { allow: [] });
  assert(passed(r));
});
t('deny wins over allow, and category wildcards match', async () => {
  assert(w.decide({ allow: ['*'], deny: ['editor.*'] }, 'editor', { action: 'save' }).ok === false);
  assert(w.decide({ allow: ['*'], deny: [] }, 'asset', { action: 'save' }).ok === true);
  assert(w.decide({ allow: ['landscape.*'], deny: [] }, 'landscape2', { action: 'x' }).ok === false);
});
t('unclassifiable calls are refused: no action, bad identifiers, unknown gateway action', async () => {
  const rs = await run([call(1, 'level', {}), call(2, 'tools', { action: 'call', category: 'level;rm', method: 'x' }), call(3, 'tools', { action: 'weird' }), call(4, 'bad name', { action: 'x' })], { allow: ['*'] });
  assert(rs.length === 4 && rs.every(blocked));
});
t('a missing or invalid policy file falls back to the discovery-only baseline', async () => {
  const [ok, no] = await run([call(1, 'tools', { action: 'call', category: 'project', method: 'get_status' }), call(2, 'tools', { action: 'call', category: 'level', method: 'place_actor' })], '{not json');
  assert(passed(ok)); assert(blocked(no));
});
t('a policy without an allow list is not "allow everything"', async () => {
  const [r] = await run([call(1, 'tools', { action: 'call', category: 'level', method: 'place_actor' })], { deny: [] });
  assert(blocked(r));
});
t('a batch with one denied call is refused as a whole', async () => {
  const rs = await run([[call(1, 'level', { action: 'place_actor' }), call(2, 'editor', { action: 'execute_python' })]], POLICY);
  assert(Array.isArray(rs[0]) ? rs[0].every(blocked) : blocked(rs[0]));
});
t('tools/list hides a denied or never-allowed category tool but keeps the gateway', async () => {
  const [r] = await run([{ jsonrpc: '2.0', id: 1, method: 'tools/list' }], POLICY);
  const names = r.result.tools.map((x) => x.name);
  assert.deepStrictEqual(names, ['tools', 'catalog', 'project', 'level', 'landscape', 'editor']);
});
t('invalid JSON is answered with a parse error', async () => {
  const proc = spawn('node', [wrapper, '--', 'node', fake]);
  let out = ''; proc.stdout.on('data', (d) => { out += d; });
  proc.stdin.write('nope\n'); proc.stdin.end();
  await new Promise((r) => proc.on('exit', r));
  assert.strictEqual(JSON.parse(out.trim()).error.code, -32700);
});

(async () => {
  for (const [name, fn] of T) { await fn(); console.log('ok:', name); }
  console.log('all tests passed');
})().catch((e) => { console.error(e); process.exit(1); });
