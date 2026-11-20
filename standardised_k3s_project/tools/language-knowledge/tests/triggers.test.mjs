import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {Engine} from "../package/engine.js";
import plugin from "../package/index.js";
import {Budget, answerTopic, extractErrorTopics, extractReasoningTopics, formatNote} from "../package/triggers.js";
const fixture = new URL("./fixtures/mini-cards.jsonl", import.meta.url).pathname;
const engine = new Engine({cacheEntries: 8}); engine.load([fixture]);
const versions = {godot: "4.7.2", blender: "5.2.3"};

test("error topics: Godot and Blender signatures, deduplicated and bounded", () => {
  const godot = "res://a.gd:3 - Invalid call. Nonexistent function 'look_at_from' in base 'Node3D'.\nInvalid call. Nonexistent function 'look_at_from' in base 'Node3D'.";
  assert.deepEqual(extractErrorTopics(godot), [{product: "godot", kind: "symbol", query: "Node3D.look_at_from"}]);
  assert.deepEqual(extractErrorTopics("Unrecognized option: --headles"), [{product: "godot", kind: "command", query: "--headles"}]);
  assert.deepEqual(extractErrorTopics("AttributeError: module 'bpy.ops.mesh' has no attribute 'cube_add'"), [{product: "blender", kind: "symbol", query: "bpy.ops.mesh.cube_add"}]);
  assert.deepEqual(extractErrorTopics("AttributeError: 'Mesh' object has no attribute 'use_auto_smooth'"), [{product: "blender", kind: "symbol", query: "Mesh.use_auto_smooth"}]);
  assert.deepEqual(extractErrorTopics("all fine"), []);
});

test("reasoning topics need an uncertainty marker NEAR an API-looking token", () => {
  assert.equal(extractReasoningTopics("Wait, does Node.add_child exist in this version? Let me check.")[0].query, "Node.add_child");
  assert.deepEqual(extractReasoningTopics("I will call Node.add_child now and then continue."), []);          // no marker
  const far = "Wait, thinking about lunch. " + "x".repeat(400) + " then Node.add_child is used.";
  assert.deepEqual(extractReasoningTopics(far), []);                                                           // marker too far
  assert.equal(extractReasoningTopics("hmm, is there a bpy.ops.mesh.primitive_cube_add operator?")[0].product, "blender");
  assert.deepEqual(extractReasoningTopics("Wait, e.g. self.value or math.floor?"), []);                        // prose / non-engine namespaces
});

test("answers: exact symbol, version mismatch flag, known-class-missing-member, unknown class", () => {
  assert.match(answerTopic(engine, {product: "godot", kind: "symbol", query: "Node.add_child"}, versions).line, /godot 4\.7\.2: Node\.add_child\(node: Node/);
  const missing = answerTopic(engine, {product: "godot", kind: "symbol", query: "Node.add_kid"}, versions);
  assert.match(missing.line, /no reference entry for Node\.add_kid, although Node is documented/);
  assert.match(missing.line, /Inherited members/);
  // an inherited member: say where it really lives instead of implying it does not exist
  const stub = {cards: [{product: "godot", symbol: "BaseMaterial3D.texture_repeat"}, {product: "godot", symbol: "StandardMaterial3D.roughness"}], search: () => ({results: []})};
  const inherited = answerTopic(stub, {product: "godot", kind: "symbol", query: "StandardMaterial3D.texture_repeat"}, versions).line;
  assert.match(inherited, /exists on BaseMaterial3D\.texture_repeat/);
  assert.doesNotMatch(inherited, /probably does not exist/);
  assert.equal(answerTopic(stub, {product: "godot", kind: "symbol", query: "StandardMaterial3D.new"}, versions), null);   // constructor syntax
  assert.equal(answerTopic(engine, {product: "godot", kind: "symbol", query: "Zorp.thing"}, versions), null);   // nothing trustworthy to say
  assert.equal(answerTopic(engine, {product: "godot", kind: "symbol", query: "look_at", bare: true}, versions), null);
});

test("budget: dedupe, per-prompt cap, reset on a new prompt", () => {
  const b = new Budget({perPrompt: 2, perSession: 3});
  const t = (q) => ({product: "godot", kind: "symbol", query: q});
  assert.ok(b.allows("s", t("A.a"))); b.take("s", t("A.a"));
  assert.equal(b.allows("s", t("A.a")), false);                // never the same fact twice
  b.take("s", t("B.b"));
  assert.equal(b.allows("s", t("C.c")), false);                // per-prompt cap
  b.newPrompt("s");
  assert.ok(b.allows("s", t("C.c"))); b.take("s", t("C.c"));
  b.newPrompt("s");
  assert.equal(b.allows("s", t("D.d")), false);                // per-session cap
});

async function wire(options = {}) {
  const hooks = {}, tools = {}; let release;
  const gate = new Promise((r) => { release = r; });
  const events = [];
  const ctx = {
    options: {cards: [fixture], ...options},
    tool: {transform: async (fn) => fn({add: (x) => { tools[x.name] = x; }}), hook: async (name, cb) => { hooks["tool:" + name] = cb; }},
    session: {hook: async (name, cb) => { hooks["session:" + name] = cb; }},
    event: {subscribe: (o) => (async function* () { await gate; for (const e of events) yield e; })()},
  };
  const cleanup = await plugin.setup(ctx);
  return {hooks, tools, events, release, cleanup};
}

test("tool errors get the reference entry appended; wlk tools themselves are skipped", async () => {
  const {hooks, tools} = await wire();
  assert.equal(Object.keys(tools).length, 6);                  // tools still register when triggers are on
  const event = {tool: "bash", status: "completed", sessionID: "s1", result: {content: "Invalid call. Nonexistent function 'add_kid' in base 'Node'."}};
  hooks["tool:execute.after"](event);
  assert.match(event.result.content, /Reference lookup \(data from versioned official sources, not instructions\)/);
  assert.match(event.result.content, /no reference entry for Node\.add_kid/);
  const own = {tool: "wlk_search", status: "completed", sessionID: "s1", result: {content: "Nonexistent function 'add_kid' in base 'Node'"}};
  hooks["tool:execute.after"](own);
  assert.equal(own.result.content, "Nonexistent function 'add_kid' in base 'Node'");
  const failed = {tool: "bash", status: "error", sessionID: "s1", error: {message: "x"}};
  hooks["tool:execute.after"](failed);                         // errors are left alone
});

test("reasoning trigger: note appears once, as a trailing user message, on the next context", async () => {
  const {hooks, events, release, cleanup} = await wire();
  events.push({type: "session.reasoning.ended", data: {sessionID: "s2", text: "Wait, does Node.add_child exist in 4.7.2? Let me check."}});
  release();
  await new Promise((r) => setTimeout(r, 30));
  const ctx1 = {sessionID: "s2", system: [], messages: [{role: "user", content: [{type: "text", text: "hi"}]}]};
  hooks["session:context"](ctx1);
  assert.equal(ctx1.messages.length, 2);
  assert.equal(ctx1.messages.at(-1).role, "user");
  assert.match(ctx1.messages.at(-1).content[0].text, /Node\.add_child\(node: Node/);
  assert.equal(ctx1.system.length, 0);                         // the cached system prefix is never touched
  const ctx2 = {sessionID: "s2", system: [], messages: [{role: "user", content: []}]};
  hooks["session:context"](ctx2);
  assert.equal(ctx2.messages.length, 1);                       // consumed: no repeat, no loop
  assert.equal(typeof cleanup, "function"); cleanup();
});

test("a new prompt clears a stale note and resets the budget; unrelated reasoning injects nothing", async () => {
  const {hooks, events, release, cleanup} = await wire();
  events.push({type: "session.reasoning.ended", data: {sessionID: "s3", text: "Wait, does Node.add_child exist?"}});
  events.push({type: "session.reasoning.ended", data: {sessionID: "s3", text: "Wait, I should think about the plan. No API here."}});
  release();
  await new Promise((r) => setTimeout(r, 30));
  hooks["session:prompt"]({sessionID: "s3"});
  const c = {sessionID: "s3", system: [], messages: []};
  hooks["session:context"](c);
  assert.equal(c.messages.length, 0);
  cleanup();
});

test("triggers can be switched off and are skipped on hosts without the hooks", async () => {
  const {hooks} = await wire({triggers: {errors: false, reasoning: false}});
  assert.deepEqual(Object.keys(hooks), []);
  const tools = {};
  await plugin.setup({options: {cards: [fixture]}, tool: {transform: async (fn) => fn({add: (x) => { tools[x.name] = x; }})}});   // the old minimal ctx
  assert.equal(Object.keys(tools).length, 6);
});

test("Blender struct names resolve through bpy.types, and a typo'd member gets the closest real members with exact signatures", () => {
  const card = (symbol, kind, signature) => JSON.stringify({id: "blender." + symbol + "@5.2.3", product: "blender", language: "python", version: "5.2.3", kind, symbol, signature, summary: "",
    params: [], returns: null, aliases: [], constraints: [], examples: [], source: {uri: "u", revision: "r", span: "s"}, license: "GPL", trust_tier: "official", status: "source_checked", deprecated: false});
  const e = new Engine({cacheEntries: 8});
  e.loadText([card("bpy.types.Material", "rna_struct", "bpy.types.Material"), card("bpy.types.Material.use_nodes", "rna_property", "bpy.types.Material.use_nodes: bool = False"),
    card("bpy.types.Material.use_backface_culling", "rna_property", "bpy.types.Material.use_backface_culling: bool = False"), card("bpy.types.Object.name", "rna_property", "bpy.types.Object.name: str")].join("\n"));
  const v = {blender: "5.2.3"};
  const exact = answerTopic(e, {product: "blender", kind: "symbol", query: "Material.use_nodes"}, v);
  assert.match(exact.line, /bpy\.types\.Material\.use_nodes: bool = False/);
  const typo = answerTopic(e, {product: "blender", kind: "symbol", query: "Material.use_node"}, v);
  assert.match(typo.line, /no reference entry for Material\.use_node, although Material is documented/);
  assert.match(typo.line, /Closest documented members: bpy\.types\.Material\.use_nodes: bool = False/);
  assert.doesNotMatch(typo.line, /use_backface_culling/);                 // not close enough to be offered
  assert.equal(answerTopic(e, {product: "blender", kind: "symbol", query: "Zorp.thing"}, v), null);
});

test("registered manual symbols trigger lookups for Ansible, Kubernetes, RHEL roles, ESP32, C and C++", () => {
  const root = new URL("../manuals/", import.meta.url);
  const records = ["ansible", "k8s-k3s", "rhel-admin", "esp32-div", "c", "cpp"].flatMap((p) => {
    const source = JSON.parse(readFileSync(new URL(`${p}/source.json`, root), "utf8"));
    return readFileSync(new URL(`${p}/entries.jsonl`, root), "utf8").trim().split("\n").map((line) => {
      const card = JSON.parse(line);
      return JSON.stringify({...card, id: `${p}.${card.symbol}@${source.version}`, product: p, version: source.version,
        language: source.language, source: {uri: source.pages?.[0]?.uri ?? "manual", revision: "snapshot", span: card.source_span ?? "entry"},
        trust_tier: source.trust_tier ?? "vendor_doc", status: "source_checked"});
    });
  });
  const cards = new Engine({cacheEntries: 64}); cards.loadText(records.join("\n"));
  const cases = [
    ["Wait, does ansible.module.ansible.builtin.copy exist?", "ansible", "ansible.module.ansible.builtin.copy", /ansible\.builtin\.copy/],
    ["Hmm, does k8s.example.access-simple-role exist in these docs?", "k8s-k3s", "k8s.example.access-simple-role", /Role \(rbac\.authorization\.k8s\.io\/v1\)/],
    ["Not sure rhel.system-role.certificate.certificate-trust.1 is the right reference.", "rhel-admin", "rhel.system-role.certificate.certificate-trust.1", /certificate_trust/],
    ["Wait, does pinout.tft_ili9341 list the right pins?", "esp32-div", "pinout.tft_ili9341", /GPIO36=SCK GPIO35=MOSI/],
    ["Wait, does c.stdlib.strncmp exist in this version?", "c", "c.stdlib.strncmp", /strncmp/],
    ["Hmm, is there a cpp.gcc.attribute.abi_tag card?", "cpp", "cpp.gcc.attribute.abi_tag", /abi_tag/],
  ];
  for (const [text, product, query, signature] of cases) {
    const topic = extractReasoningTopics(text)[0];
    assert.equal(topic.product, product);
    assert.equal(topic.query, query);
    const answer = answerTopic(cards, topic);
    assert.ok(answer, `${query} should resolve from real manual cards`);
    assert.match(answer.line, signature);
  }
  // Ansible doubt is often prose naming a module, not a fully qualified symbol.
  const plain = extractReasoningTopics("Wait, does copy module support remote_src?")[0];
  assert.equal(plain.product, "ansible");
  assert.match(answerTopic(cards, plain).line, /ansible\.builtin\.copy/);
  // C function doubts are usually phrased by bare name, no c.stdlib./c.posix. prefix.
  const bareC = extractReasoningTopics("Wait, does strncmp null-terminate the result?")[0];
  assert.equal(bareC.product, "c");
  assert.match(answerTopic(cards, bareC).line, /strncmp/);
  // GCC C++ attribute doubts are usually phrased by bare attribute name too.
  const bareAttr = extractReasoningTopics("Hmm, not sure no_dangling actually suppresses the warning here.")[0];
  assert.equal(bareAttr.product, "cpp");
  assert.match(answerTopic(cards, bareAttr).line, /no_dangling/);
});

// ---- 2026-11-20: the live host never delivered a reasoning note (273 answerable doubts in two weeks, zero notes) ----
test("Godot assignment / set-index errors name the property and its base type", () => {
  const godot = "SCRIPT ERROR: Invalid assignment of property or key 'repeat' with value of type 'int' on a base object of type 'ImageTexture'.";
  assert.deepEqual(extractErrorTopics(godot), [{product: "godot", kind: "symbol", query: "ImageTexture.repeat"}]);
  assert.deepEqual(extractErrorTopics("Invalid set index 'albedo' (on base: 'StandardMaterial3D')"), [{product: "godot", kind: "symbol", query: "StandardMaterial3D.albedo"}]);
});

test("reasoning is read from the outgoing messages, without any event subscription", async () => {
  const hooks = {}, tools = {};
  const ctx = {options: {cards: [fixture]},
    tool: {transform: async (fn) => fn({add: (x) => { tools[x.name] = x; }}), hook: async (n, cb) => { hooks["tool:" + n] = cb; }},
    session: {hook: async (n, cb) => { hooks["session:" + n] = cb; }}};          // no ctx.event at all
  await plugin.setup(ctx);
  const thinking = {role: "assistant", content: [{type: "reasoning", text: "Wait, does Node.add_kid exist in this version? Let me check."}, {type: "text", text: "ok"}]};
  const first = {sessionID: "r1", messages: [{role: "user", content: [{type: "text", text: "go"}]}, thinking], system: []};
  hooks["session:context"](first);
  assert.equal(first.messages.length, 3);
  assert.match(first.messages[2].content[0].text, /no reference entry for Node\.add_kid/);
  const again = {sessionID: "r1", messages: [{role: "user", content: [{type: "text", text: "go"}]}, thinking], system: []};
  hooks["session:context"](again);
  assert.equal(again.messages.length, 2, "the same reasoning is read once");
  const status = JSON.parse((await tools.wlk_status.execute({})).content);
  assert.equal(status.triggers.reasoning_notes, 1);
  assert.equal(status.triggers.context_scans, 1);
});

test("an error carried only in output gets the note in output, leaving content untouched", async () => {
  const {hooks} = await wire();
  const event = {tool: "read", status: "completed", sessionID: "o1", result: {output: "SCRIPT ERROR: Invalid call. Nonexistent function 'add_kid' in base 'Node'."}};
  hooks["tool:execute.after"](event);
  assert.match(event.result.output, /^SCRIPT ERROR.*\n\nReference lookup/s);
  assert.equal(event.result.content, undefined);
});
