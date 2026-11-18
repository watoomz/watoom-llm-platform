#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

const die = (m) => { console.error(`ERROR: ${m}`); process.exit(2); };
const okSlug = (s) => /^[a-z0-9][a-z0-9._-]*$/.test(s || "");
const base = path.resolve(process.cwd(), ".watoom", "tracks");

function dir(slug) {
  if (!okSlug(slug)) die("invalid slug");
  return path.join(base, slug);
}
function stateFile(slug) { return path.join(dir(slug), "status.json"); }
function load(slug) {
  const p = stateFile(slug);
  if (!fs.existsSync(p)) die(`track not found: ${slug}`);
  return JSON.parse(fs.readFileSync(p, "utf8"));
}
function save(slug, s) {
  s.updated_at = new Date().toISOString();
  fs.writeFileSync(stateFile(slug), JSON.stringify(s, null, 2) + "\n");
}
function print(s) { console.log(JSON.stringify(s, null, 2)); }

const [cmd, slug, ...rest] = process.argv.slice(2);

if (cmd === "init") {
  const title = rest.join(" ").trim();
  if (!okSlug(slug) || !title) die('usage: init SLUG "TITLE"');
  const d = dir(slug);
  if (fs.existsSync(d)) die(`track exists: ${slug}`);
  fs.mkdirSync(d, { recursive: true });
  const now = new Date().toISOString();
  fs.writeFileSync(path.join(d, "context.md"), `# Context: ${title}\n\n## Current state\n\n## Constraints\n\n## Authoritative files\n\n`);
  fs.writeFileSync(path.join(d, "spec.md"), `# Specification: ${title}\n\n## Outcome\n\n## Non-goals\n\n## Acceptance criteria\n\n`);
  fs.writeFileSync(path.join(d, "plan.md"), `# Plan: ${title}\n\n`);
  const s = { slug, title, phase: "context", result: "ACTIVE", created_at: now, updated_at: now, tasks: [] };
  save(slug, s); print(s); process.exit(0);
}

if (cmd === "status") { print(load(slug)); process.exit(0); }

if (cmd === "add") {
  const title = rest.join(" ").trim();
  if (!title) die('usage: add SLUG "TASK"');
  const s = load(slug);
  const id = s.tasks.length ? Math.max(...s.tasks.map(x => x.id)) + 1 : 1;
  s.tasks.push({ id, title, status: "pending", reason: null });
  save(slug, s); print(s); process.exit(0);
}

if (cmd === "next") {
  const s = load(slug);
  const t = s.tasks.find(x => x.status === "pending");
  console.log(t ? JSON.stringify(t, null, 2) : "NO_PENDING_TASK");
  process.exit(0);
}

if (cmd === "complete" || cmd === "block") {
  const id = Number(rest[0]);
  if (!Number.isInteger(id)) die(`usage: ${cmd} SLUG TASK_ID [REASON]`);
  const s = load(slug);
  const t = s.tasks.find(x => x.id === id);
  if (!t) die(`task not found: ${id}`);
  if (cmd === "complete") {
    t.status = "complete"; t.reason = null;
  } else {
    const reason = rest.slice(1).join(" ").trim();
    if (!reason) die("block requires reason");
    t.status = "blocked"; t.reason = reason; s.result = "BLOCKED";
  }
  save(slug, s); print(s); process.exit(0);
}

if (cmd === "phase") {
  const phase = rest[0];
  const allowed = new Set(["context","spec","plan","implement","review","finalize","complete"]);
  if (!allowed.has(phase)) die("invalid phase");
  const s = load(slug);
  s.phase = phase;
  if (phase === "complete") s.result = "PASS";
  save(slug, s); print(s); process.exit(0);
}

die("usage: watoom-track.mjs {init|status|add|next|complete|block|phase} ...");
