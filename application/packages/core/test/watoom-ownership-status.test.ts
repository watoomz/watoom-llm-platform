import { test, expect } from "bun:test"
import fs from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import { OwnershipStatus } from "../src/watoom/ownership-status"
test("ownership observations fail closed for stale, absent, forged and writable snapshots", async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "ownership-status-")),
    file = path.join(root, "status.json")
  expect((await OwnershipStatus.read(file)).available).toBe(false)
  const value = {
    schema: "watoom.gpu-observation.v1",
    sampledAt: Date.now(),
    phase: "qwen-ready",
    owner: null,
    generation: 3,
    uncertain: false,
    activeRequests: 0,
    primary: "primary",
  }
  await fs.writeFile(file, JSON.stringify(value), { mode: 0o644 })
  if (process.getuid?.() === 0) {
    expect((await OwnershipStatus.read(file)).stale).toBe(false)
    await fs.writeFile(file, JSON.stringify({ ...value, sampledAt: Date.now() - 30000 }))
    expect((await OwnershipStatus.read(file)).stale).toBe(true)
  }
  await fs.chmod(file, 0o666)
  expect((await OwnershipStatus.read(file)).available).toBe(false)
  await fs.chmod(file, 0o644)
  await fs.symlink(file, path.join(root, "indirect.json"))
  expect((await OwnershipStatus.read(path.join(root, "indirect.json"))).available).toBe(false)
})
