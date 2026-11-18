import { expect, test } from "bun:test"
import { SqliteClient } from "@effect/sql-sqlite-bun"
import { EffectDrizzleSqlite } from "@opencode/core/database/drizzle"
import { DatabaseMigration } from "@opencode/core/database/migration"
import { migrations } from "@opencode/core/database/migration.gen"
import selection from "@opencode/core/database/migration/20261014020000_watoom_skill_selection"
import agentSelection from "@opencode/core/database/migration/20261014030000_watoom_agent_skill_selection"
import { Global } from "@opencode/util/global"
import { Effect } from "effect"
import { SqlClient } from "effect/sql"
import { sql } from "drizzle-orm"
import path from "node:path"
const run = <A, E>(effect: Effect.Effect<A, E, SqlClient.SqlClient | Global.Service>) =>
  Effect.runPromise(
    effect.pipe(
      Effect.provideService(Global.Service, Global.make({ data: path.join(process.cwd(), ".test-data") })),
      Effect.provide(SqliteClient.layer({ filename: ":memory:", disableWAL: true })),
      Effect.scoped,
    ),
  )
test("fresh native bootstrap registers skill schemas and original migration IDs exactly once", () =>
  run(
    Effect.gen(function* () {
      const db = yield* EffectDrizzleSqlite.makeWithDefaults()
      yield* DatabaseMigration.apply(db)
      for (const entry of [selection, agentSelection]) {
        expect(migrations.filter((item) => item.id === entry.id)).toHaveLength(1)
        expect(yield* db.get(sql`SELECT id FROM migration WHERE id=${entry.id}`)).toEqual({ id: entry.id })
      }
      expect((yield* db.all(sql`PRAGMA table_info(_watoom_skill_selection)`)).length).toBe(6)
      expect((yield* db.all(sql`PRAGMA table_info(_watoom_agent_skill_selection)`)).length).toBe(5)
    }),
  ))
test("legacy selection tables upgrade without losing rows or replaying completed migrations", () =>
  run(
    Effect.gen(function* () {
      const db = yield* EffectDrizzleSqlite.makeWithDefaults()
      yield* db.transaction((tx) => selection.up(tx))
      yield* db.transaction((tx) => agentSelection.up(tx))
      yield* db.run(
        sql`INSERT INTO _watoom_skill_selection VALUES('owned-session','owned-scope','owned-skill','owned-sha','owned-commit','owned-bundle')`,
      )
      yield* DatabaseMigration.applyOnly(db, [selection, agentSelection])
      yield* DatabaseMigration.applyOnly(db, [selection, agentSelection])
      expect(yield* db.all(sql`SELECT session_id,scope,skill_id FROM _watoom_skill_selection`)).toEqual([
        { session_id: "owned-session", scope: "owned-scope", skill_id: "owned-skill" },
      ])
      expect((yield* db.all(sql`SELECT id FROM migration`)).length).toBe(2)
    }),
  ))
