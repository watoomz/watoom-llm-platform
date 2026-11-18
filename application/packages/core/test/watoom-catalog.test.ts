import fs from "node:fs/promises"
import path from "node:path"
import { randomUUID } from "node:crypto"
import { test, expect } from "bun:test"
import { Effect } from "effect"
import { sql } from "drizzle-orm"
import { SqliteClient } from "@effect/sql-sqlite-bun"
import { EffectDrizzleSqlite } from "@opencode/core/database/drizzle"
import {
  migration,
  agentMigration,
  search,
  browse,
  select,
  selected,
  remove,
  selectForAgent,
  selectedForAgent,
  removeForAgent,
} from "@opencode/core/watoom/catalog"
const scope = { project: "project", repository: "repo", agent: "agent" }
const id = "github:owner/repo:skill"
const run = (
  body: (
    db: Effect.Success<ReturnType<typeof EffectDrizzleSqlite.makeWithDefaults>>,
  ) => Effect.Effect<unknown, unknown>,
  filename = ":memory:",
  initialize = true,
) =>
  Effect.runPromise(
    Effect.gen(function* () {
      const db = yield* EffectDrizzleSqlite.makeWithDefaults()
      if (initialize) {
        yield* db.transaction((tx) => migration.up(tx))
        yield* db.transaction((tx) => agentMigration.up(tx))
        for (const statement of [
          "CREATE TABLE skills(id TEXT PRIMARY KEY,repo TEXT,path TEXT,name TEXT,description TEXT,sha256 TEXT,license TEXT,risk TEXT,validation TEXT)",
          "CREATE TABLE sources(repo TEXT,commit_sha TEXT)",
          "CREATE TABLE approvals(skill_id TEXT,approved_sha TEXT)",
          "CREATE TABLE approval_context(skill_id TEXT,commit_sha TEXT,bundle_sha TEXT)",
          "CREATE VIRTUAL TABLE skills_fts USING fts5(id UNINDEXED,name,description)",
        ])
          yield* db.run(sql.raw(statement))
        yield* db.run(
          sql`INSERT INTO skills VALUES(${id},'owner/repo','skill','fixture','fixture skill',${"a".repeat(64)},'MIT','[]','valid')`,
        )
        yield* db.run(sql`INSERT INTO sources VALUES('owner/repo',${"b".repeat(40)})`)
        yield* db.run(sql`INSERT INTO skills_fts VALUES(${id},'fixture','fixture skill')`)
      }
      return yield* body(db)
    }).pipe(Effect.provide(SqliteClient.layer({ filename, disableWAL: true })), Effect.scoped),
  )
const approve = (db: Effect.Success<ReturnType<typeof EffectDrizzleSqlite.makeWithDefaults>>) =>
  Effect.gen(function* () {
    yield* db.run(sql`INSERT INTO approvals VALUES(${id},${"a".repeat(64)})`)
    yield* db.run(sql`INSERT INTO approval_context VALUES(${id},${"b".repeat(40)},${"c".repeat(64)})`)
  })
test("native catalog defaults approved only and returns bounded metadata", () =>
  run((db) =>
    Effect.gen(function* () {
      expect(yield* search(db, "fixture")).toEqual([])
      expect((yield* search(db, "fixture", 16, false)).length).toBe(1)
      yield* approve(db)
      const rows = yield* search(db, "fixture")
      expect(rows.length).toBe(1)
      expect(rows[0].bundle_sha).toBe("c".repeat(64))
    }),
  ))
test("native selection rejects unapproved and invalid references", () =>
  run((db) =>
    Effect.gen(function* () {
      expect((yield* select(db, db, { sessionID: "s1", scope, skillID: id }).pipe(Effect.exit))._tag).toBe("Failure")
      yield* approve(db)
      expect((yield* select(db, db, { sessionID: "s1", scope, skillID: "invalid" }).pipe(Effect.exit))._tag).toBe(
        "Failure",
      )
    }),
  ))
test("native selection isolates sessions and project scope", () =>
  run((db) =>
    Effect.gen(function* () {
      yield* approve(db)
      yield* select(db, db, { sessionID: "s1", scope, skillID: id })
      expect((yield* selected(db, db, { sessionID: "s2", scope, skillID: id }).pipe(Effect.exit))._tag).toBe("Failure")
      expect(
        (yield* selected(db, db, { sessionID: "s1", scope: { ...scope, project: "other" }, skillID: id }).pipe(
          Effect.exit,
        ))._tag,
      ).toBe("Failure")
      expect((yield* selected(db, db, { sessionID: "s1", scope, skillID: id })).sha256).toBe("a".repeat(64))
    }),
  ))
test("native selection invalidates on source revision update", () =>
  run((db) =>
    Effect.gen(function* () {
      yield* approve(db)
      yield* select(db, db, { sessionID: "s1", scope, skillID: id })
      yield* db.run(sql`UPDATE sources SET commit_sha=${"c".repeat(40)}`)
      expect((yield* selected(db, db, { sessionID: "s1", scope, skillID: id }).pipe(Effect.exit))._tag).toBe("Failure")
    }),
  ))
test("native remove never activates or executes a skill", () =>
  run((db) =>
    Effect.gen(function* () {
      yield* approve(db)
      yield* select(db, db, { sessionID: "s1", scope, skillID: id })
      yield* remove(db, "s1", scope, id)
      expect((yield* selected(db, db, { sessionID: "s1", scope, skillID: id }).pipe(Effect.exit))._tag).toBe("Failure")
    }),
  ))

test("native selection invalidates when approved companion bundle changes", () =>
  run((db) =>
    Effect.gen(function* () {
      yield* approve(db)
      yield* select(db, db, { sessionID: "s1", scope, skillID: id })
      yield* db.run(sql`UPDATE approval_context SET bundle_sha=${"d".repeat(64)}`)
      expect((yield* selected(db, db, { sessionID: "s1", scope, skillID: id }).pipe(Effect.exit))._tag).toBe("Failure")
    }),
  ))

test("agent preferences isolate owners and remain distinct from session attachments", () =>
  run((db) =>
    Effect.gen(function* () {
      yield* approve(db)
      yield* selectForAgent(db, db, { scope, skillID: id })
      expect((yield* selectedForAgent(db, db, { scope, skillID: id })).bundleSha256).toBe("c".repeat(64))
      expect(
        (yield* selectedForAgent(db, db, { scope: { ...scope, agent: "other" }, skillID: id }).pipe(Effect.exit))._tag,
      ).toBe("Failure")
      expect((yield* selected(db, db, { sessionID: "s1", scope, skillID: id }).pipe(Effect.exit))._tag).toBe("Failure")
    }),
  ))
test("revocation and removal invalidate agent preference without instruction loading", () =>
  run((db) =>
    Effect.gen(function* () {
      yield* approve(db)
      yield* selectForAgent(db, db, { scope, skillID: id })
      yield* db.run(sql`DELETE FROM approvals WHERE skill_id=${id}`)
      expect((yield* selectedForAgent(db, db, { scope, skillID: id }).pipe(Effect.exit))._tag).toBe("Failure")
      yield* removeForAgent(db, scope, id)
      expect(yield* db.get(sql`SELECT * FROM _watoom_agent_skill_selection WHERE skill_id=${id}`)).toBeUndefined()
    }),
  ))

test("agent and session selections survive SQLite reopen and revocation remains durable", async () => {
  const filename = path.join(process.env.TMPDIR!, "watoom-catalog-" + randomUUID() + ".sqlite")
  try {
    await run(
      (db) =>
        Effect.gen(function* () {
          yield* approve(db)
          yield* selectForAgent(db, db, { scope, skillID: id })
          yield* select(db, db, { sessionID: "s1", scope, skillID: id })
        }),
      filename,
    )
    await run(
      (db) =>
        Effect.gen(function* () {
          expect((yield* selectedForAgent(db, db, { scope, skillID: id })).sha256).toBe("a".repeat(64))
          expect((yield* selected(db, db, { sessionID: "s1", scope, skillID: id })).sha256).toBe("a".repeat(64))
          yield* db.run(sql`DELETE FROM approvals WHERE skill_id=${id}`)
        }),
      filename,
      false,
    )
    await run(
      (db) =>
        Effect.gen(function* () {
          expect((yield* selectedForAgent(db, db, { scope, skillID: id }).pipe(Effect.exit))._tag).toBe("Failure")
          expect((yield* selected(db, db, { sessionID: "s1", scope, skillID: id }).pipe(Effect.exit))._tag).toBe(
            "Failure",
          )
        }),
      filename,
      false,
    )
  } finally {
    await fs.unlink(filename).catch(() => {})
  }
})

test("catalog browse returns bounded metadata, counts and pagination without instructions", () =>
  run((db) =>
    Effect.gen(function* () {
      const unapproved = yield* browse(db, { approvedOnly: false })
      expect(unapproved.discovered).toBe(1)
      expect(unapproved.validated).toBe(1)
      expect(unapproved.approved).toBe(0)
      expect(unapproved.rows[0].bundle_sha).toBeNull()
      expect(Object.keys(unapproved.rows[0])).not.toContain("raw")
      expect(Object.keys(unapproved.rows[0])).not.toContain("content")
      expect((yield* browse(db)).matched).toBe(0)
      expect((yield* browse(db, { approvedOnly: false, offset: 1 })).rows).toEqual([])
      expect((yield* browse(db, { approvedOnly: false, license: "GPL" })).matched).toBe(0)
      expect((yield* browse(db, { approvedOnly: false, query: "fixture" })).matched).toBe(1)
    }),
  ))
test("catalog browse never marks malformed approval bundle as approved", () =>
  run((db) =>
    Effect.gen(function* () {
      yield* approve(db)
      yield* db.run(sql`UPDATE approval_context SET bundle_sha='not-a-hash'`)
      expect((yield* browse(db)).rows).toEqual([])
      const page = yield* browse(db, { approvedOnly: false })
      expect(page.approved).toBe(0)
      expect(page.rows[0].approved).toBe(0)
    }),
  ))
test("catalog browse bounds reject oversized queries and offsets", () =>
  run((db) =>
    Effect.gen(function* () {
      for (const input of [
        { query: "x".repeat(257) },
        { limit: 33 },
        { offset: 10001 },
        { offset: -1 },
        { license: "x".repeat(129) },
      ])
        expect((yield* browse(db, input).pipe(Effect.exit))._tag).toBe("Failure")
    }),
  ))
