// T-0115: agent prompt text that restates guard behaviour must match the guard's constants. This is the drift that
// left the specialist roster unreachable in T-0107 (prompts said "call them", the guard allowlist did not).
import assert from "node:assert/strict";
import {readFileSync, readdirSync} from "node:fs";
import {BUDGET, READ_BUDGET, CRITIC_ESCALATION_CAP, COORDINATOR_CHILDREN} from "../../ansible/roles/watoom-code/files/coordinator-guard/index.js";

const native = new URL("../../ansible/roles/watoom-code/files/native/", import.meta.url);
const words = ["zero","one","two","three","four","five","six","seven","eight","nine","ten","eleven","twelve","thirteen",
  "fourteen","fifteen","sixteen","seventeen","eighteen","nineteen","twenty"];
const shared = name => readFileSync(new URL("_src/shared/" + name, native), "utf8");

const limits = shared("03_agent_selection_and_handoff_boundaries.md");
assert.match(limits, new RegExp(`has ${words[BUDGET]} direct execution calls and ${words[READ_BUDGET]} read-only discovery calls`),
  "shared/03 must state the guard's BUDGET/READ_BUDGET");
assert.match(limits, new RegExp(`critic can be consulted at most ${words[CRITIC_ESCALATION_CAP]} times`),
  "shared/03 must state CRITIC_ESCALATION_CAP");

const roster = shared("03_agent_selection_and_handoff_boundaries.md");
const agents = new Set(readdirSync(new URL("agents/", native)).map(f => f.replace(/\.md$/, "")));
for (const child of COORDINATOR_CHILDREN) {
  assert.ok(agents.has(child), `guard allows ${child} but no agents/${child}.md exists`);
  const plain = child.replace(/^watoom-/, "").replace(/-/g, " ");
  assert.ok(new RegExp(plain.replace(/ /g, "[ -]?"), "i").test(roster) || roster.includes(child),
    `shared/03 routing list never mentions ${child}`);
}
const handoff = readFileSync(new URL("_src/roles/watoom-workflow/20_special_routes.md", native), "utf8");
const count = ["zero","one","two","three","four","five","six","seven","eight","nine","ten","eleven","twelve","thirteen","fourteen","fifteen"][COORDINATOR_CHILDREN.length];
assert.ok(handoff.includes(`all ${count} child roles`), `workflow special routes must say "all ${count} child roles"`);
console.log("PASS prompt text matches guard budgets, critic cap and the coordinator child roster");
