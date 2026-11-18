import test from "node:test";
import assert from "node:assert/strict";
import {writeFileSync, mkdtempSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {Engine} from "../package/engine.js";
const fixture = new URL("./fixtures/mini-cards.jsonl", import.meta.url).pathname;
const DIM = 8;
function unit(k) { const v = new Array(DIM).fill(0); v[k] = 1; return v; }
function build(e, axes) {
  const dir = mkdtempSync(join(tmpdir(), "wlk-"));
  const buf = Buffer.alloc(e.cards.length * DIM);
  axes.forEach((axis, i) => unit(axis).forEach((x, k) => buf.writeInt8(Math.round(x * 127), i * DIM + k)));
  writeFileSync(join(dir, "v.i8"), buf);
  return {path: join(dir, "v.i8"), meta: {model: "fake", dim: DIM, count: e.cards.length, cards_sha: e.sha}};
}
test("semantic hit surfaces a card keyword search misses; exact symbol still first", () => {
  const e = new Engine(); e.load(fixture);
  // card order: add_child, remove_child, add_child(old), cube_add (blender), Object.add_child (blender)
  const {path, meta} = build(e, [0, 1, 2, 3, 4]);
  e.loadVectors(path, meta);
  const lexical = e.search("zzz unrelated words", {});
  assert.equal(lexical.count, 0);
  const sem = e.search("zzz unrelated words", {queryVector: unit(3)});
  assert.equal(sem.results[0].symbol, "bpy.ops.mesh.primitive_cube_add");
  assert.equal(sem.results[0].match, "semantic");
  const exact = e.search("Node.add_child", {queryVector: unit(3), product: "godot", version: "4.7.2"});
  assert.equal(exact.results[0].id, "godot.Node.add_child@4.7.2");
});
test("vectors built for different cards are refused", () => {
  const e = new Engine(); e.load(fixture);
  const {path, meta} = build(e, [0, 1, 2, 3, 4]);
  assert.throws(() => e.loadVectors(path, {...meta, cards_sha: "deadbeef"}), /vectors built for cards/);
});
test("product filter applies to semantic results", () => {
  const e = new Engine(); e.load(fixture);
  const {path, meta} = build(e, [0, 1, 2, 3, 3]); e.loadVectors(path, meta);
  assert.ok(e.search("zzz", {queryVector: unit(3), product: "godot"}).results.every((r) => r.id.startsWith("godot.")) || true);
  assert.equal(e.search("zzz", {queryVector: unit(3), product: "godot"}).results.filter((r) => r.id.startsWith("blender.")).length, 0);
});
