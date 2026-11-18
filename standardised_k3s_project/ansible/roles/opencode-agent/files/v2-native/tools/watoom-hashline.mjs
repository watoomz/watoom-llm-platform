#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

const die = (m) => { console.error(`ERROR: ${m}`); process.exit(2); };
const h = (s) => crypto.createHash("sha256").update(s).digest("hex").slice(0, 8);

function projectPath(input) {
  const root = fs.realpathSync(process.cwd());
  const candidate = path.resolve(process.cwd(), input);
  const base = fs.existsSync(candidate) ? candidate : path.dirname(candidate);
  const realBase = fs.realpathSync(base);
  if (realBase !== root && !realBase.startsWith(root + path.sep)) {
    die(`path escapes current project: ${input}`);
  }
  return candidate;
}

function readFileLines(file) {
  if (!fs.existsSync(file)) die(`file not found: ${file}`);
  return fs.readFileSync(file, "utf8").split("\n");
}

function verify(lines, n, expected, label) {
  if (!Number.isInteger(n) || n < 1 || n > lines.length) die(`${label} line out of range`);
  const actual = h(lines[n - 1]);
  if (actual !== expected) die(`${label} anchor mismatch at ${n}: expected=${expected} actual=${actual}`);
}

function atomicWrite(file, text) {
  const st = fs.statSync(file);
  const tmp = path.join(path.dirname(file), `.${path.basename(file)}.watoom-${process.pid}-${Date.now()}`);
  fs.writeFileSync(tmp, text, { mode: st.mode });
  fs.renameSync(tmp, file);
}

const [cmd, ...a] = process.argv.slice(2);

if (cmd === "read") {
  const [arg, s = "1", e] = a;
  if (!arg) die("usage: read FILE [START] [END]");
  const lines = readFileLines(projectPath(arg));
  const start = Math.max(1, Number(s));
  const end = Math.min(lines.length, e ? Number(e) : lines.length);
  if (!Number.isInteger(start) || !Number.isInteger(end) || end < start) die("invalid range");
  for (let n = start; n <= end; n++) console.log(`${n}#${h(lines[n - 1])}| ${lines[n - 1]}`);
  process.exit(0);
}

if (cmd === "replace") {
  const [arg, s, sh, e, eh, replArg] = a;
  if (!replArg) die("usage: replace FILE START START_HASH END END_HASH REPLACEMENT_FILE");
  const file = projectPath(arg);
  const lines = readFileLines(file);
  const start = Number(s), end = Number(e);
  if (!Number.isInteger(start) || !Number.isInteger(end) || end < start) die("invalid range");
  verify(lines, start, sh, "start");
  verify(lines, end, eh, "end");
  const replFile = projectPath(replArg);
  if (!fs.existsSync(replFile)) die(`replacement file not found: ${replArg}`);
  let repl = fs.readFileSync(replFile, "utf8");
  if (repl.endsWith("\n")) repl = repl.slice(0, -1);
  const replLines = repl === "" ? [] : repl.split("\n");
  const out = [...lines.slice(0, start - 1), ...replLines, ...lines.slice(end)];
  atomicWrite(file, out.join("\n"));
  console.log(`REPLACE_OK file=${arg} lines=${start}-${end}`);
  process.exit(0);
}

die("usage: watoom-hashline.mjs {read|replace} ...");
