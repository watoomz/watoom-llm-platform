import test from "node:test";
import assert from "node:assert/strict";
import {mkdtempSync, readFileSync, rmSync, writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {Engine} from "../package/engine.js";
const fixture = new URL("./fixtures/mini-cards.jsonl", import.meta.url).pathname;
const make = () => { const e = new Engine(); e.load(fixture); return e; };

test("exact symbol outranks keyword and respects product filter", () => {
  const e = make();
  const r = e.search("Node.add_child", {product: "godot", version: "4.7.2"});
  assert.equal(r.results[0].id, "godot.Node.add_child@4.7.2");
  assert.equal(r.results[0].match, "exact-symbol");
  assert.ok(r.results.every((x) => x.id.startsWith("godot.")));
});
test("same member name in two products is separated by product", () => {
  const e = make();
  assert.ok(e.search("add_child", {product: "blender"}).results.every((x) => x.id.startsWith("blender.")));
});
test("version policy: exact first, mismatch demoted and flagged, never substituted silently", () => {
  const e = make();
  const r = e.search("add_child", {product: "godot", version: "4.7.2"});
  assert.equal(r.results[0].version, "4.7.2");
  const old = r.results.find((x) => x.version === "4.1.0");
  assert.equal(old.version_match, "mismatch");
  const none = e.search("add_child", {product: "godot", version: "9.9.9"});
  assert.ok(none.warnings.length);
});
test("signatures are returned byte-exact", () => {
  const e = make();
  assert.equal(e.get("godot.Node.add_child@4.7.2").signature, "Node.add_child(node: Node, force_readable_name: bool = false, internal: InternalMode = 0) -> void");
});
test("hot path does no disk reads and caches repeats", () => {
  const e = make(); const reads = e.counters.diskReads;
  e.search("remove child node"); e.search("remove child node");
  assert.equal(e.counters.diskReads, reads);
  assert.equal(e.counters.cacheHits, 1);
});
test("token budget truncates and reports it", () => {
  const e = make();
  const r = e.search("add_child", {budget: 60, limit: 20});
  assert.equal(r.results.length, 1); assert.equal(r.truncated, true);
});
test("malformed card is rejected and old generation is kept", () => {
  const e = make();
  assert.throws(() => e.loadText('{"id":"x"}'), /missing/);
  assert.equal(e.status().cards, 5);
});
test("file-backed cold reads use exact byte ranges and the parsed LRU", () => {
  const dir = mkdtempSync(join(tmpdir(), "language-knowledge-"));
  try {
    const path = join(dir, "cards-a.jsonl"), path2 = join(dir, "cards-b.jsonl");
    const expected = Array.from({length: 1040}, (_, i) => ({
      id: `synthetic.${i}`, product: "test", language: "test", version: "1.0", kind: "api_method",
      symbol: `Synthetic.card_${i}`, signature: `Synthetic.card_${i}() -> String`, summary: `Card ${i} — café 🧪`,
      source: {uri: `https://example.test/${i}`}, trust_tier: "verified", status: "active", params: [], returns: {type: "String"},
    }));
    writeFileSync(path, expected.slice(0, 520).map((card) => JSON.stringify(card)).join("\n") + "\n");
    writeFileSync(path2, expected.slice(520).map((card) => JSON.stringify(card)).join("\n") + "\n");
    const e = new Engine();
    e.load([path, path2]);
    const initialReads = e.counters.diskReads;
    assert.deepEqual(e.card(519), expected[519]);
    assert.equal(e.counters.diskReads, initialReads + 1);
    assert.deepEqual(e.card(519), expected[519]);
    assert.equal(e.counters.diskReads, initialReads + 1);
    assert.deepEqual(JSON.parse(readFileSync(path, "utf8").split("\n")[0]), expected[0]);
    assert.deepEqual(e.card(0), expected[0]);
    for (let i = 528; i < 1040; i++) e.card(i);
    const beforeReread = e.counters.diskReads;
    assert.deepEqual(e.card(0), expected[0]);
    assert.equal(e.counters.diskReads, beforeReread + 1);
  } finally {
    rmSync(dir, {recursive: true, force: true});
  }
});
test("natural language finds natural matches", () => {
  const e = make();
  assert.equal(e.search("create a cube mesh", {product: "blender"}).results[0].symbol, "bpy.ops.mesh.primitive_cube_add");
});
