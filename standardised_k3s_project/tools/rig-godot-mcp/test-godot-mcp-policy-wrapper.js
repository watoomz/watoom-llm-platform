#!/usr/bin/env node
'use strict';
const path = require('path');
const assert = require('assert');
const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');

const wrapper = path.join(__dirname, 'godot-mcp-policy-wrapper.js');
const fakeChild = path.join(__dirname, 'fake-bridge-child.js');

function runWrapper(lines, policyPath) {
  return new Promise((resolve, reject) => {
    const args = policyPath ? ['--policy', policyPath] : [];
    args.push('--', 'node', fakeChild);
    const proc = spawn('node', [wrapper, ...args]);
    let out = '';
    proc.stdout.on('data', (d) => { out += d.toString(); });
    proc.on('error', reject);
    proc.on('exit', () => resolve(out.trim().split('\n').filter(Boolean).map((l) => JSON.parse(l))));
    for (const line of lines) proc.stdin.write(JSON.stringify(line) + '\n');
    proc.stdin.end();
  });
}

async function testReadOnlyDefaultBlocksEditsAndHidesThem() {
  const [blocked, list] = await runWrapper([
    { jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name: 'delete_node', arguments: {} } },
    { jsonrpc: '2.0', id: 2, method: 'tools/list' },
  ]);
  assert.strictEqual(blocked.error.code, -32001);
  const names = list.result.tools.map((t) => t.name);
  assert.deepStrictEqual(names, ['list_nodes', 'read_scene', 'get_screenshot']);
  console.log('ok: testReadOnlyDefaultBlocksEditsAndHidesThem');
}

async function testAllowedCallReachesTheBridge() {
  const [reply] = await runWrapper([{ jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name: 'read_scene', arguments: {} } }]);
  assert.deepStrictEqual(reply.result, { echoed: 'tools/call' });
  console.log('ok: testAllowedCallReachesTheBridge');
}

async function testPolicyFileOpensASpecificTool() {
  const tmp = path.join(os.tmpdir(), `godot-mcp-policy-${process.pid}.json`);
  fs.writeFileSync(tmp, JSON.stringify({ allow_names: ['execute_code'], deny_names: [] }));
  try {
    const [reply] = await runWrapper([{ jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name: 'execute_code', arguments: {} } }], tmp);
    assert.deepStrictEqual(reply.result, { echoed: 'tools/call' });
  } finally {
    fs.unlinkSync(tmp);
  }
  console.log('ok: testPolicyFileOpensASpecificTool');
}

async function testBatchWithABlockedCallIsRefusedAsAWhole() {
  const [reply] = await runWrapper([[
    { jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name: 'read_scene' } },
    { jsonrpc: '2.0', id: 2, method: 'tools/call', params: { name: 'delete_node' } },
  ]]);
  assert.strictEqual(reply.length, 1); // only the blocked entries are returned, mirroring rig-unreal-mcp/mcp_proxy.py
  console.log('ok: testBatchWithABlockedCallIsRefusedAsAWhole');
}

async function testBadJsonGetsAParseError() {
  const proc = spawn('node', [wrapper, '--', 'node', fakeChild]);
  let out = '';
  proc.stdout.on('data', (d) => { out += d.toString(); });
  proc.stdin.write('not json\n');
  proc.stdin.end();
  await new Promise((resolve) => proc.on('exit', resolve));
  assert.strictEqual(JSON.parse(out.trim()).error.code, -32700);
  console.log('ok: testBadJsonGetsAParseError');
}

(async () => {
  await testReadOnlyDefaultBlocksEditsAndHidesThem();
  await testAllowedCallReachesTheBridge();
  await testPolicyFileOpensASpecificTool();
  await testBatchWithABlockedCallIsRefusedAsAWhole();
  await testBadJsonGetsAParseError();
  console.log('all tests passed');
})().catch((e) => { console.error(e); process.exit(1); });
