import { expect } from "bun:test"
import { Database } from "bun:sqlite"
import { Effect } from "effect"
import { createHash } from "node:crypto"
import fs from "node:fs/promises"
import path from "node:path"
import { tmpdir } from "../../core/test/fixture/tmpdir"
import { it } from "../../core/test/lib/effect"
import { startServer } from "./fixture/server"
import { sqliteLayer } from "@opencode/core/database/sqlite.bun"
import { EffectDrizzleSqlite } from "@opencode/core/database/drizzle"
import { Catalog } from "@opencode/core/watoom/catalog"
import { SkillArtifact } from "@opencode/core/watoom/skill-artifact"
const hash = (text: string) => createHash("sha256").update(text).digest("hex")

it.live("authenticated native review, install preview, pin drift and revocation gate real skill loading", () => Effect.gen(function* () {
  const tmp = yield* Effect.acquireDisposable(Effect.promise(() => tmpdir("watoom-admin-api-")))
  const global = path.join(tmp.path, "config")
  const root = path.join(tmp.path, "artifacts")
  const folder = path.join(root, "github__owned__fixture", "harmless")
  yield* Effect.promise(() => fs.mkdir(folder, { recursive: true }))
  yield* Effect.promise(() => fs.mkdir(global, { recursive: true }))
  const markdown = "---\nname: harmless\ndescription: Owned approval fixture\n---\nReturn an inert summary.\n"
  const dependency = JSON.stringify({ version: 1, native_tools: [] })
  yield* Effect.promise(() => fs.writeFile(path.join(folder, "SKILL.md"), markdown))
  yield* Effect.promise(() => fs.writeFile(path.join(folder, "watoom-skill.json"), dependency))
  const database = path.join(tmp.path, "registry.sqlite3")
  const fixture = new Database(database)
  fixture.run("CREATE TABLE sources(repo TEXT PRIMARY KEY,commit_sha TEXT)")
  fixture.run("CREATE TABLE skills(id TEXT PRIMARY KEY,repo TEXT,path TEXT,name TEXT,description TEXT,sha256 TEXT,license TEXT,risk TEXT,validation TEXT)")
  fixture.run("CREATE TABLE approvals(skill_id TEXT PRIMARY KEY,approved_sha TEXT NOT NULL,note TEXT NOT NULL,at TEXT NOT NULL)")
  fixture.run("CREATE TABLE approval_context(skill_id TEXT PRIMARY KEY,commit_sha TEXT NOT NULL,bundle_sha TEXT NOT NULL)")
  fixture.run("INSERT INTO sources VALUES('owned/fixture',?)", ["a".repeat(40)])
  const id = "github:owned/fixture:harmless"
  fixture.run("INSERT INTO skills VALUES(?,'owned/fixture','harmless','harmless','owned',?,'MIT','[]','valid')", [id, hash(markdown)])
  fixture.close()
  yield* Effect.promise(() => fs.writeFile(path.join(global, "opencode.json"), JSON.stringify({ skill_catalog: { database, artifacts: root, administration: true } })))
  const server = yield* startServer(global)
  const payload = { skillID: id, action: "approve", sha256: hash(markdown), revision: "a".repeat(40), bundleSha256: hash(JSON.stringify([["SKILL.md",hash(markdown)],["watoom-skill.json",hash(dependency)]])), permissions: [{ action: "skill", resource: id, effect: "allow" }], tools: [] }
  const call = (body: object, authenticated = true) => Effect.promise(() => fetch(new URL("/api/skill/catalog/admin", server.base), { method: "POST", headers: { "content-type": "application/json", ...(authenticated ? server.headers : {}) }, body: JSON.stringify(body) }))
  expect((yield* call(payload, false)).status).toBe(401)
  expect((yield* call({ ...payload, revision: "b".repeat(40) })).status).toBe(400)
  const preview = yield* call({ ...payload, dryRun: true })
  expect(preview.status).toBe(200)
  const inspect = new Database(database, { readonly: true })
  expect(inspect.query("SELECT count(*) n FROM approvals").get()).toEqual({ n: 0 })
  inspect.close()
  const approval = yield* call({ ...payload, reviewer: "client-forgery" })
  expect(approval.status).toBe(200)
  const receipt = yield* Effect.promise(() => approval.json())
  expect(receipt.data.reviewer).toBe("server-owner:opencode")
  const load = Effect.gen(function* () {
    const db = yield* EffectDrizzleSqlite.makeWithDefaults()
    const reference = yield* Catalog.approvedReference(db, id)
    return yield* SkillArtifact.resolve(root, { ...reference, commit: reference.commit_sha, bundleSha256: reference.bundle_sha }, [{ action: "skill", resource: id, effect: "allow" }])
  }).pipe(Effect.provide(sqliteLayer({ filename: database, readonly: true, readwrite: false, create: false, disableWAL: true })), Effect.scoped)
  expect(String((yield* load).id)).toBe(id)
  expect((yield* call({ ...payload, action: "install", dryRun: true })).status).toBe(200)
  expect((yield* call({ ...payload, action: "install" })).status).toBe(200)
  expect((yield* call({ ...payload, action: "enable" })).status).toBe(200)
  yield* Effect.promise(() => fs.appendFile(path.join(folder, "SKILL.md"), "changed"))
  expect((yield* load.pipe(Effect.exit))._tag).toBe("Failure")
  yield* Effect.promise(() => fs.writeFile(path.join(folder, "SKILL.md"), markdown))
  expect((yield* call({ ...payload, action: "disable" })).status).toBe(200)
  expect((yield* load.pipe(Effect.exit))._tag).toBe("Failure")
  expect((yield* call({ ...payload, action: "enable" })).status).toBe(200)
  expect((yield* call({ ...payload, action: "revoke" })).status).toBe(200)
  expect((yield* load.pipe(Effect.exit))._tag).toBe("Failure")
  expect((yield* call({ ...payload, action: "enable" })).status).toBe(400)
  const deniedGlobal = path.join(tmp.path, "denied-config")
  yield* Effect.promise(() => fs.mkdir(deniedGlobal))
  yield* Effect.promise(() => fs.writeFile(path.join(deniedGlobal, "opencode.json"), JSON.stringify({ skill_catalog: { database, artifacts: root, administration: false } })))
  const deniedServer = yield* startServer(deniedGlobal)
  const denied = yield* Effect.promise(() => fetch(new URL("/api/skill/catalog/admin", deniedServer.base), { method: "POST", headers: { "content-type": "application/json", ...deniedServer.headers }, body: JSON.stringify(payload) }))
  expect(denied.status).toBe(400)
}), { timeout: 30000 })
