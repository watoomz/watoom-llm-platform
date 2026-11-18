#!/usr/bin/env node
// Stand-in for `npx @npgamedev/godot-mcp-server`: reads ndjson lines from stdin, answers a
// minimal JSON-RPC result per line (a fixed tool list for tools/list). Used only by
// test-godot-mcp-policy-wrapper.js.
'use strict';
const readline = require('readline');
const rl = readline.createInterface({ input: process.stdin });
rl.on('line', (line) => {
  const msg = JSON.parse(line);
  if (msg.method === 'tools/list') {
    const tools = ['list_nodes', 'read_scene', 'get_screenshot', 'execute_code', 'delete_node'].map((n) => ({ name: n }));
    process.stdout.write(JSON.stringify({ jsonrpc: '2.0', id: msg.id, result: { tools } }) + '\n');
  } else {
    process.stdout.write(JSON.stringify({ jsonrpc: '2.0', id: msg.id, result: { echoed: msg.method } }) + '\n');
  }
});
