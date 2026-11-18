import assert from "node:assert/strict";
import {test} from "node:test";
import {searchPresets, summariseStatus, runGenerate, createClient} from "../plugin/index.js";

const data = {presets: [
  {id: "kodak-portra-400", name: "Kodak Portra 400", category: "Film stocks", prompt_look: "warm skin tones"},
  {id: "kodak-tri-x", name: "Kodak Tri-X", category: "Film stocks", prompt_look: "black and white grain"},
  {id: "polaroid", name: "Polaroid", category: "Instant", prompt_look: "faded instant"}]};
const active = {session: {state: "active", idle_seconds_left: 500}, running_job: null, queued: 0};
const idle = {session: {state: "idle", quiet_seconds: 10, quiet_required: 1800}};

test("search by text and category", () => {
  assert.equal(searchPresets(data, {query: "tri-x"}).total, 1);
  assert.equal(searchPresets(data, {category: "instant"}).presets[0].id, "polaroid");
  assert.equal(searchPresets(data, {limit: 1}).presets.length, 1);
});
test("status tells the agent how to start a session only when idle", () => {
  assert.equal(summariseStatus(active).ready_to_generate, true);
  assert.equal(summariseStatus(active).how_to_start, null);
  assert.match(summariseStatus(idle).how_to_start, /operator/);
});
test("generate without a session submits nothing", async () => {
  let submitted = false;
  const client = {status: async () => idle, submit: async () => { submitted = true; }};
  const r = await runGenerate(client, {scene: "a teapot"});
  assert.equal(r.generated, false); assert.equal(r.reason, "no_gpu_session"); assert.equal(submitted, false);
});
test("generate polls to completion and returns the file", async () => {
  const seen = [];
  const jobs = [{status: "running"}, {status: "done", id: "a".repeat(32), image: "a".repeat(32) + ".png"}];
  const client = {status: async () => active, submit: async (b) => { seen.push(b); return {id: "a".repeat(32)}; }, job: async () => jobs.shift()};
  const r = await runGenerate(client, {scene: "a teapot", preset_id: "polaroid", steps: 20}, {sleep: async () => {}});
  assert.equal(r.generated, true); assert.match(r.file, /output\/a+\.png$/);
  assert.deepEqual(seen[0], {scene: "a teapot", preset_id: "polaroid", steps: 20});
});
test("failed and timed-out jobs report instead of throwing; timeout cancels", async () => {
  const client = {status: async () => active, submit: async () => ({id: "b".repeat(32)}), job: async () => ({status: "failed", error: "engine died"})};
  assert.equal((await runGenerate(client, {scene: "x"}, {sleep: async () => {}})).error, "engine died");
  let cancelled = false;
  const slow = {status: async () => active, submit: async () => ({id: "c".repeat(32)}), job: async () => ({status: "running"}), cancel: async () => { cancelled = true; }};
  const r = await runGenerate(slow, {scene: "x"}, {maxMs: 5, pollMs: 1, sleep: () => new Promise((x) => setTimeout(x, 3))});
  assert.equal(r.reason, "timeout"); assert.equal(cancelled, true);
});
test("client turns Studio errors into messages", async () => {
  const c = createClient("http://x", async () => ({ok: false, status: 409, json: async () => ({error: {message: "gpu_session_required"}})}));
  await assert.rejects(c.submit({scene: "x"}), /gpu_session_required/);
});
