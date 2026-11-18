import { test, expect } from "bun:test"
import fs from "node:fs/promises"
import path from "node:path"
import { createHash } from "node:crypto"
import { Effect } from "effect"
import { SkillArtifact } from "@opencode/core/watoom/skill-artifact"
import { Permission } from "@opencode/core/permission"
import { Skill } from "@opencode/core/skill"
import { FSUtil } from "@opencode/util/fs-util"
import { AppNodeBuilder } from "@opencode/core/effect/app-node-builder"
import { LayerNode } from "@opencode/util/effect/layer-node"
const allow: Permission.Ruleset = [{ action: "skill", resource: "*", effect: "allow" as const }]
const sha = (data: string) => createHash("sha256").update(data).digest("hex")
async function fixture(nativeTools: string[] = []) {
  const root = await fs.mkdtemp(path.join(process.env.TMPDIR!, "skill-artifact-"))
  const base = path.join(root, "github__owned__fixture")
  const folder = path.join(base, "harmless")
  await fs.mkdir(folder, { recursive: true })
  const text = "---\nname: harmless\ndescription: Owned harmless workflow control\n---\nReturn a read-only summary.\n"
  await fs.writeFile(path.join(folder, "SKILL.md"), text)
  await fs.writeFile(path.join(folder, "reference.txt"), "Reviewed inert reference")
  const manifest = JSON.stringify({ version: 1, native_tools: nativeTools })
  await fs.writeFile(path.join(folder, "watoom-skill.json"), manifest)
  const bundle = sha(
    JSON.stringify([
      ["SKILL.md", sha(text)],
      ["reference.txt", sha("Reviewed inert reference")],
      ["watoom-skill.json", sha(manifest)],
    ]),
  )
  return {
    root,
    base,
    folder,
    ref: {
      id: "github:owned/fixture:harmless",
      repo: "owned/fixture",
      path: "harmless",
      sha256: sha(text),
      commit: "a".repeat(40),
      bundleSha256: bundle,
    },
  }
}
const reject = async (f: Awaited<ReturnType<typeof fixture>>, ref = f.ref, permissions = allow) =>
  expect((await Effect.runPromise(SkillArtifact.resolve(f.root, ref, permissions).pipe(Effect.exit)))._tag).toBe(
    "Failure",
  )
test("approved owned artifact uses actual native parser and prepare without global registration", async () => {
  const f = await fixture()
  const output = await Effect.runPromise(
    Effect.gen(function* () {
      const skill = yield* SkillArtifact.resolve(f.root, f.ref, allow)
      expect(String(skill.id)).toBe(f.ref.id)
      expect(skill.autoinvoke).toBe(false)
      const fsUtil = yield* FSUtil.Service
      return yield* Skill.prepare(fsUtil, skill)
    }).pipe(Effect.provide(AppNodeBuilder.build(LayerNode.group([FSUtil.node]))), Effect.scoped),
  )
  expect(output.output).toContain("Return a read-only summary.")
  expect(output.output).toContain("reference.txt")
})
test("unapproved or denied session cannot resolve instructions", async () => {
  const f = await fixture()
  await reject(f, f.ref, [])
  await reject(f, f.ref, [{ action: "skill", resource: "*", effect: "deny" }])
})
test("companion mutation revokes approved content", async () => {
  const f = await fixture()
  await fs.writeFile(path.join(f.folder, "reference.txt"), "Changed")
  await reject(f)
})
test("changed SKILL.md never reaches native parser", async () => {
  const f = await fixture()
  await fs.appendFile(path.join(f.folder, "SKILL.md"), "Changed")
  await reject(f)
})
test("added or removed companion invalidates full bundle", async () => {
  const f = await fixture()
  await fs.writeFile(path.join(f.folder, "added.txt"), "Added")
  await reject(f)
  const g = await fixture()
  await fs.rename(path.join(g.folder, "reference.txt"), path.join(g.base, "retained.txt"))
  await reject(g)
})
test("acquired source cannot bypass review promotion", async () => {
  const f = await fixture()
  await fs.writeFile(path.join(f.base, ".acquisition.json"), "{}")
  await reject(f)
})
test("symlink companion and source roots rejected", async () => {
  const f = await fixture()
  await fs.symlink(path.join(f.folder, "reference.txt"), path.join(f.folder, "linked.txt"))
  await reject(f)
  const g = await fixture()
  await fs.rename(g.base, g.base + "-retained")
  await fs.symlink(g.base + "-retained", g.base)
  await reject(g)
})
test("traversal and invalid source identities rejected", async () => {
  const f = await fixture()
  for (const relative of ["../harmless", "a/../../harmless", "/harmless", "a//b", "a/./b"])
    await reject(f, { ...f.ref, path: relative })
  await reject(f, { ...f.ref, repo: "../fixture" })
})
test("invalid pin and bundle hash rejected", async () => {
  const f = await fixture()
  await reject(f, { ...f.ref, commit: "main" })
  await reject(f, { ...f.ref, bundleSha256: "f".repeat(64) })
  await reject(f, { ...f.ref, sha256: "invalid" })
})
test("oversized companion rejected before content read", async () => {
  const f = await fixture()
  const h = await fs.open(path.join(f.folder, "huge.txt"), "wx")
  await h.truncate(1024 * 1024 + 1)
  await h.close()
  await reject(f)
})
test("directory budget bounds bundle enumeration", async () => {
  const f = await fixture()
  for (let i = 0; i < 129; i++) await fs.writeFile(path.join(f.folder, `file-${i}.txt`), "")
  await reject(f)
})

test("required native capabilities are checked without installing or granting tools", async () => {
  const f = await fixture(["shell"])
  await reject(f)
  const skill = await Effect.runPromise(SkillArtifact.resolve(f.root, f.ref, allow, new Set(["shell"])))
  expect(String(skill.id)).toBe(f.ref.id)
})
test("missing dependency manifest remains blocked even with a matching content bundle", async () => {
  const f = await fixture()
  await fs.unlink(path.join(f.folder, "watoom-skill.json"))
  const entries = [
    ["SKILL.md", sha(await fs.readFile(path.join(f.folder, "SKILL.md"), "utf8"))],
    ["reference.txt", sha("Reviewed inert reference")],
  ]
  await reject(f, { ...f.ref, bundleSha256: sha(JSON.stringify(entries)) })
})
