import { expect, test } from "bun:test"
import { SqliteClient } from "@effect/sql-sqlite-bun"
import { EffectDrizzleSqlite } from "@opencode/core/database/drizzle"
import { DatabaseMigration } from "@opencode/core/database/migration"
import { migrations } from "@opencode/core/database/migration.gen"
import operational from "@opencode/core/database/migration/20261015113533_watoom_operational_state"
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
test("native workflow and specialist schemas bootstrap and preserve state across repeated migrations", () => run(Effect.gen(function* () {
  const db = yield* EffectDrizzleSqlite.makeWithDefaults()
  yield* DatabaseMigration.apply(db)
  expect(migrations.filter((entry) => entry.id === operational.id)).toHaveLength(1)
  yield* db.run(sql`INSERT INTO _watoom_checkpoint VALUES('project-session','job',1,'{"done":false}')`)
  yield* DatabaseMigration.apply(db)
  expect(yield* db.get(sql`SELECT seq FROM _watoom_checkpoint WHERE scope='project-session'`)).toEqual({ seq: 1 })
  expect((yield* db.all(sql`PRAGMA table_info(_watoom_specialist_job)`)).length).toBe(13)
})))

test("interrupted operational migration rolls back and upgrade resumes preserving skill selections", () => run(Effect.gen(function* () {
  const db = yield* EffectDrizzleSqlite.makeWithDefaults()
  yield* DatabaseMigration.applyOnly(db, [selection, agentSelection])
  yield* db.run(sql`INSERT INTO _watoom_skill_selection VALUES('session','scope','skill','sha','commit','bundle')`)
  const interrupted = { ...operational, up: (tx: Parameters<typeof operational.up>[0]) => operational.up(tx).pipe(Effect.andThen(Effect.die(Error("simulated process interruption before commit")))) }
  expect((yield* DatabaseMigration.applyOnly(db, [interrupted]).pipe(Effect.exit))._tag).toBe("Failure")
  expect(yield* db.get(sql`SELECT name FROM sqlite_master WHERE name='_watoom_checkpoint'`)).toBeUndefined()
  yield* DatabaseMigration.applyOnly(db, [operational])
  yield* DatabaseMigration.applyOnly(db, [operational])
  expect(yield* db.get(sql`SELECT skill_id FROM _watoom_skill_selection`)).toEqual({ skill_id: "skill" })
  expect((yield* db.all(sql`SELECT id FROM migration WHERE id=${operational.id}`)).length).toBe(1)
})))
