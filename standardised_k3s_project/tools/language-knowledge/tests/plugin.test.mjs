import test from "node:test";
import assert from "node:assert/strict";
import plugin from "../package/index.js";
const fixture = new URL("./fixtures/mini-cards.jsonl", import.meta.url).pathname;
async function register(options, storage) {
  const tools = {};
  await plugin.setup({options, storage, tool: {transform: async (fn) => fn({add: (t) => { tools[t.name] = t; }})}});
  return tools;
}
test("registers six read-only tools with {content, metadata} results", async () => {
  const tools = await register({cards: [fixture]});
  assert.deepEqual(Object.keys(tools).sort(), ["wlk_command", "wlk_feedback", "wlk_get", "wlk_search", "wlk_status", "wlk_symbol"]);
  const r = await tools.wlk_search.execute({query: "Node.add_child", product: "godot", version: "4.7.2"});
  assert.deepEqual(Object.keys(r).sort(), ["content", "metadata"]);
  assert.equal(JSON.parse(r.content).results[0].id, "godot.Node.add_child@4.7.2");
});
test("symbol tool drops keyword-only hits", async () => {
  const tools = await register({cards: [fixture]});
  const r = JSON.parse((await tools.wlk_symbol.execute({symbol: "create cube"})).content);
  assert.equal(r.count, 0);
});
test("missing snapshot reports not-ready instead of throwing", async () => {
  const tools = await register({cards: ["/nonexistent/cards.jsonl"]});
  const r = JSON.parse((await tools.wlk_search.execute({query: "x"})).content);
  assert.equal(r.ready, false);
  assert.match(JSON.parse((await tools.wlk_status.execute({})).content).load_error, /ENOENT/);
});

test("feedback is queued to plugin storage, validated and redacted, never promoted", async () => {
  const saved = {};
  const tools = await register({cards: [fixture]}, {set: async (k, v) => { saved[k] = v; }});
  const good = JSON.parse((await tools.wlk_feedback.execute({card_id: "godot.Node.add_child@4.7.2", outcome: "worked", note: "ok token=abc123"})).content);
  assert.equal(good.queued, true);
  assert.match(Object.values(saved)[0].note, /\[redacted\]/);
  const bad = JSON.parse((await tools.wlk_feedback.execute({card_id: "nope", outcome: "worked"})).content);
  assert.equal(bad.queued, false);
});
test("embedding service failure degrades to lexical search", async () => {
  const tools = await register({cards: [fixture], embeddingUrl: "http://127.0.0.1:9", embeddingTimeoutMs: 200});
  const r = JSON.parse((await tools.wlk_search.execute({query: "Node.add_child"})).content);
  assert.equal(r.results[0].match, "exact-symbol");
});
