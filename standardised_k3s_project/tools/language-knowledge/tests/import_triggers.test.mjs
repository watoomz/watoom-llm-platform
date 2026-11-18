import test from "node:test";
import assert from "node:assert/strict";
import {Engine} from "../package/engine.js";
import {answerTopic, extractReasoningTopics, formatNote} from "../package/triggers.js";
const engine = new Engine({cacheEntries: 8}); engine.load([new URL("./fixtures/import-cards.jsonl", import.meta.url).pathname]);
const versions = {godot: "4.7.2"};

// The reasoning a model produced while fixing an FBX import that kept creating texture files in the source tree.
const WOLF = `Confirmed the mechanism. Godot's FBX import created wolf_0.png and wolf_1.png in the source tree.
Hmm. Actually, let me reconsider. Godot's FBX import in 4.x: the FBX importer extracts embedded textures. Let me recall the actual behavior.
Does it check for existence before writing? Let me think... in Godot source, FBX texture extraction is... I believe it writes unconditionally (always extracts embedded textures to file).
Key question: does Godot's FBX importer overwrite existing files, or only create if not present? I need to determine Godot's behavior.`;

test("behaviour doubts (not API names) now trigger an import-option lookup", () => {
  const topics = extractReasoningTopics(WOLF);
  const topic = topics.find((t) => t.kind === "import");
  assert.ok(topic, JSON.stringify(topics));
  assert.equal(topic.ext, "fbx");
  const answer = answerTopic(engine, topic, versions);
  assert.ok(answer, "an import card should answer an FBX embedded-texture doubt");
  assert.match(answer.line, /fbx\/embedded_image_handling=1/);
  assert.match(answer.line, /1 = Extract Textures/);
  assert.match(answer.line, /Embed as Basis Universal/);
  assert.match(formatNote([answer]), /^Reference lookup \(data from versioned official sources, not instructions\):/);
});

test("new doubt phrases are recognised near an option key", () => {
  for (const lead of ["I believe", "Let me think about whether", "I need to determine if", "I'm not certain that", "The question is whether", "Hmm,"]) {
    const t = extractReasoningTopics(`${lead} fbx/embedded_image_handling is honoured here.`);
    assert.equal(t[0]?.query, "fbx/embedded_image_handling", lead);
    assert.equal(t[0]?.exact, true);
  }
  assert.deepEqual(extractReasoningTopics("fbx/embedded_image_handling is set to 2 in the file."), []);   // no doubt, no lookup
});

test("exact option keys answer from their own card; unknown keys stay silent", () => {
  const hit = answerTopic(engine, {product: "godot", kind: "import", query: "fbx/embedded_image_handling", exact: true}, versions);
  assert.match(hit.line, /scene:fbx\/embedded_image_handling/);
  assert.equal(answerTopic(engine, {product: "godot", kind: "import", query: "fbx/not_a_real_option", exact: true}, versions), null);
});

test("no answer unless the card clearly matches what the doubt is about", () => {
  // right words, wrong file type
  assert.equal(answerTopic(engine, {product: "godot", kind: "import", query: "wav embedded textures extract", ext: "wav", exact: false}, versions), null);
  // generic importer talk with nothing option-like
  assert.deepEqual(extractReasoningTopics("Hmm, I need to determine if the import finished before the receipt was written."), []);
});

test("path-like prose and plain file paths do not trigger", () => {
  assert.deepEqual(extractReasoningTopics("Hmm. I need to determine if the folder assets/game exists. Let me look at res://assets/game/wolf.fbx."), []);
  assert.deepEqual(extractReasoningTopics("Wait, I will copy scenes/arena.tscn to nodes/ folder."), []);
});

test("existing symbol triggers are unaffected", () => {
  assert.equal(extractReasoningTopics("Wait, does Node.add_child exist in this version? Let me check.")[0].query, "Node.add_child");
});
