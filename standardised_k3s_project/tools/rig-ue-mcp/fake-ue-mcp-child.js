#!/usr/bin/env node
// Stand-in for `npx ue-mcp`: answers a fixed tools/list and echoes every other request. Used only by the wrapper test.
'use strict';
const readline = require('readline');
readline.createInterface({ input: process.stdin }).on('line', (line) => {
  const msg = JSON.parse(line);
  if (msg.method === 'tools/list') {
    const tools = ['tools', 'catalog', 'project', 'level', 'landscape', 'editor', 'flow'].map((n) => ({ name: n }));
    process.stdout.write(JSON.stringify({ jsonrpc: '2.0', id: msg.id, result: { tools } }) + '\n');
  } else {
    process.stdout.write(JSON.stringify({ jsonrpc: '2.0', id: msg.id, result: { echoed: msg.method, params: msg.params } }) + '\n');
  }
});
