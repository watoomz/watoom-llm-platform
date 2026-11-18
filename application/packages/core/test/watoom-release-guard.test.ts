import { test, expect } from "bun:test"
import fs from "node:fs"
import os from "node:os"
import path from "node:path"
import { Gate } from "../src/watoom/release-guard"
test("atomic admission race, owner fencing and persistence across replacement", () => {
  const root=fs.mkdtempSync(path.join(os.tmpdir(),"release-guard-"))
  const file=path.join(root,"guard.json"), owner="a".repeat(64), other="b".repeat(64)
  const old=new Gate(file), release=old.enter()
  expect(()=>old.acquire(owner)).toThrow("Active")
  expect(fs.existsSync(file)).toBe(false)
  release(); release()
  expect(old.status().leases).toBe(0)
  expect(old.acquire(owner).held).toBe(true)
  expect(()=>old.enter()).toThrow("held")
  const candidate=new Gate(file)
  expect(()=>candidate.enter()).toThrow("held")
  expect(()=>candidate.release(other)).toThrow("ownership")
  // Failed candidate rollback retains the same persistent fence.
  const rollback=new Gate(file)
  expect(()=>rollback.enter()).toThrow("held")
  expect(rollback.release(owner).held).toBe(false)
  const restored=rollback.enter()
  expect(()=>rollback.acquire(owner)).toThrow("Active")
  restored()
})
test("no persistent configuration cannot claim safe release", () => {
  expect(()=>new Gate().acquire("a".repeat(64))).toThrow("unavailable")
})
