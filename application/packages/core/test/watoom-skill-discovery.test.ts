import { test, expect } from "bun:test"
import { Database } from "bun:sqlite"
import fs from "node:fs/promises"
import path from "node:path"
import { Effect } from "effect"
import { sqliteLayer } from "#sqlite"
import { EffectDrizzleSqlite } from "../src/database/drizzle"
import { SkillCatalog } from "../src/skill/catalog"
import { Catalog } from "../src/watoom/catalog"
import { SkillDiscovery } from "../src/watoom/skill-discovery"
import { SkillRouting } from "@opencode/schema/skill-routing"
import { Agent } from "../src/agent"
import { Session } from "../src/session"
const context = { agent: Agent.ID.make("test"), sessionID: Session.ID.make("ses_test") }
test("native search discovers imported enabled and unreviewed packages without selecting or executing", async () => {
  const root = await fs.mkdtemp(path.join(process.env.TMPDIR ?? "/tmp", "skill-discovery-"))
  const file = path.join(root, "catalog.sqlite")
  const db = new Database(file)
  db.exec(`CREATE TABLE skills(id TEXT,repo TEXT,path TEXT,name TEXT,description TEXT,sha256 TEXT,license TEXT,risk TEXT,validation TEXT);
    CREATE TABLE sources(repo TEXT,commit_sha TEXT);
    CREATE TABLE approvals(skill_id TEXT,approved_sha TEXT,note TEXT,at TEXT);
    CREATE TABLE approval_context(skill_id TEXT,commit_sha TEXT,bundle_sha TEXT);
    CREATE VIRTUAL TABLE skills_fts USING fts5(id UNINDEXED,name,description);`)
  db.run("INSERT INTO sources VALUES(?,?)", ["owned/test", "a".repeat(40)])
  for (const name of ["wizard", "wizard-extra"]) {
    db.run("INSERT INTO skills VALUES(?,?,?,?,?,?,?,?,?)", [
      name,
      "owned/test",
      name,
      name,
      "Interactive setup wizard",
      "b".repeat(64),
      "MIT",
      "[]",
      "valid",
    ])
    db.run("INSERT INTO skills_fts VALUES(?,?,?)", [name, name, "Interactive setup wizard"])
  }
  db.run("INSERT INTO approvals VALUES(?,?,?,?)", ["wizard", "b".repeat(64), "owner", ""])
  db.run("INSERT INTO approval_context VALUES(?,?,?)", ["wizard", "a".repeat(40), "c".repeat(64)])
  const catalog = {
    browse: (input: Catalog.Browse) =>
      Effect.gen(function* () {
        return yield* Catalog.browse(yield* EffectDrizzleSqlite.makeWithDefaults(), input)
      }).pipe(
        Effect.provide(
          sqliteLayer({ filename: file, readonly: true, readwrite: false, create: false, disableWAL: true }),
        ),
        Effect.scoped,
        Effect.mapError(() => new SkillCatalog.Unavailable({ message: "Test catalogue unavailable" })),
      ),
    selections: () => Effect.succeed([]),
  }
  const sources = [{ id: "blender", name: "Blender", description: "Render scenes", content: "" }]
  const current = { sources, entries: SkillRouting.catalogue(sources) }
  const result = await Effect.runPromise(SkillDiscovery.search(catalog, current, { query: "wizard" }, context))
  expect(result.matches).toHaveLength(0)
  expect(result.imported.entries.map((row) => [row.id, row.enabled, row.selected])).toEqual([
    ["wizard", true, false],
    ["wizard-extra", false, false],
  ])
  expect(result.catalogueSize).toBe(3)
  const first = await Effect.runPromise(SkillDiscovery.search(catalog, current, { query: "*", limit: 1 }, context))
  expect(first.matches[0]?.id).toBe("blender")
  expect(first.imported.nextOffset).toBe(1)
  const second = await Effect.runPromise(
    SkillDiscovery.search(catalog, current, { query: "*", limit: 1, offset: 1 }, context),
  )
  expect(second.imported.entries[0]?.id).toBe("wizard-extra")
  expect(second.imported.nextOffset).toBe(null)
  expect(db.query("SELECT count(*) n FROM approvals").get()).toEqual({ n: 1 })
  db.close()
})
