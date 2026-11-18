#!/usr/bin/env node
import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const host = process.env.SMOKE_HOST || "127.0.0.1";
const port = Number(process.env.SMOKE_PORT || "4173");
const timeoutMs = Number(process.env.SMOKE_TIMEOUT_MS || "15000");
const url = `http://${host}:${port}/`;

const vite = path.resolve(
  process.cwd(),
  "node_modules",
  ".bin",
  process.platform === "win32" ? "vite.cmd" : "vite",
);

if (!fs.existsSync(vite)) {
  console.error(`SMOKE_FAIL: project-local Vite not found: ${vite}`);
  process.exit(2);
}

const child = spawn(vite, ["--host", host, "--port", String(port), "--strictPort"], {
  cwd: process.cwd(),
  stdio: ["ignore", "pipe", "pipe"],
  shell: false,
});

let output = "";
for (const stream of [child.stdout, child.stderr]) {
  stream.setEncoding("utf8");
  stream.on("data", (chunk) => {
    output += chunk;
    process.stderr.write(chunk);
  });
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function stopChild() {
  if (child.exitCode !== null) return;
  child.kill("SIGTERM");
  const graceful = Date.now() + 2000;
  while (child.exitCode === null && Date.now() < graceful) {
    await sleep(50);
  }
  if (child.exitCode === null) child.kill("SIGKILL");
}

let ok = false;
try {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(`Vite exited early with code ${child.exitCode}`);
    }
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(1500) });
      const html = await response.text();
      if (response.status === 200 && html.trim().length > 0) {
        console.log(`SMOKE_OK status=200 bytes=${Buffer.byteLength(html)} url=${url}`);
        ok = true;
        break;
      }
    } catch {
      // Retry until bounded deadline.
    }
    await sleep(200);
  }
  if (!ok) throw new Error(`no valid HTTP 200 response within ${timeoutMs}ms`);
} catch (error) {
  console.error(`SMOKE_FAIL: ${error.message}`);
  if (output) console.error(output.slice(-4000));
  process.exitCode = 1;
} finally {
  await stopChild();
}
