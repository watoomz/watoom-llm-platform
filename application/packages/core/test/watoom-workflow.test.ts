import { test, expect } from "bun:test"
import { Effect } from "effect"
import type { SqlClient } from "effect/sql/SqlClient"
import { sql } from "drizzle-orm"
import { SqliteClient } from "@effect/sql-sqlite-bun"
import { EffectDrizzleSqlite } from "@opencode/core/database/drizzle"
import {
  migration,
  checkpointOnCommit,
  claim,
  uncertain,
  acknowledge,
  recover,
  unresolved,
} from "@opencode/core/watoom/workflow"
const event = {
  scope: { project: "p", repository: "r", agent: "a" },
  job: "j",
  seq: 1,
  kind: "checkpoint" as const,
  content: "verified test result",
}
const run = (effect: Effect.Effect<unknown, unknown, SqlClient>) =>
  Effect.runPromise(
    effect.pipe(Effect.provide(SqliteClient.layer({ filename: ":memory:", disableWAL: true })), Effect.scoped),
  )
test("actual OpenCode Effect Drizzle transaction captures native checkpoint and outbox", async () => {
  await run(
    Effect.gen(function* () {
      const db = yield* EffectDrizzleSqlite.makeWithDefaults()
      yield* db.transaction((tx) => migration.up(tx))
      yield* db.transaction(() => checkpointOnCommit(db, event, { status: "verified" })(0))
      expect((yield* db.get<{ n: number }>(sql`SELECT count(*) n FROM _watoom_outbox`))?.n).toBe(1)
      yield* db.transaction(() => checkpointOnCommit(db, event, { status: "verified" })(1))
      expect((yield* db.get<{ n: number }>(sql`SELECT count(*) n FROM _watoom_outbox`))?.n).toBe(1)
    }),
  )
})
test("actual native rollback removes session change checkpoint and memory effect", async () => {
  await run(
    Effect.gen(function* () {
      const db = yield* EffectDrizzleSqlite.makeWithDefaults()
      yield* db.transaction((tx) => migration.up(tx))
      yield* db.run(sql`CREATE TABLE session_test(id TEXT)`)
      const failed = yield* db
        .transaction(() =>
          Effect.gen(function* () {
            yield* db.run(sql`INSERT INTO session_test VALUES('s')`)
            yield* checkpointOnCommit(db, event, { status: "verified" })(0)
            return yield* Effect.die(Error("injected owner failure"))
          }),
        )
        .pipe(Effect.exit)
      expect(failed._tag).toBe("Failure")
      for (const table of ["session_test", "_watoom_checkpoint", "_watoom_outbox"])
        expect((yield* db.get<{ n: number }>(sql.raw("SELECT count(*) n FROM " + table)))?.n).toBe(0)
    }),
  )
})
test("native participant refuses conflicting event retry", async () => {
  await run(
    Effect.gen(function* () {
      const db = yield* EffectDrizzleSqlite.makeWithDefaults()
      yield* db.transaction((tx) => migration.up(tx))
      yield* db.transaction(() => checkpointOnCommit(db, event, { v: 1 })(0))
      const result = yield* db.transaction(() => checkpointOnCommit(db, event, { v: 2 })(1)).pipe(Effect.exit)
      expect(result._tag).toBe("Failure")
      expect((yield* db.get<{ n: number }>(sql`SELECT count(*) n FROM _watoom_outbox`))?.n).toBe(1)
    }),
  )
})

test("native participant rejects capture outside owner transaction", async () => {
  await run(
    Effect.gen(function* () {
      const db = yield* EffectDrizzleSqlite.makeWithDefaults()
      yield* db.transaction((tx) => migration.up(tx))
      const result = yield* checkpointOnCommit(db, event, {})(0).pipe(Effect.exit)
      expect(result._tag).toBe("Failure")
    }),
  )
})

test("native ordering uncertainty and positive reconciliation", async () => {
  await run(
    Effect.gen(function* () {
      const db = yield* EffectDrizzleSqlite.makeWithDefaults()
      yield* db.transaction((tx) => migration.up(tx))
      yield* db.transaction(() => checkpointOnCommit(db, event, { status: "first" })(0))
      yield* db.transaction(() => checkpointOnCommit(db, { ...event, seq: 2 }, { status: "second" })(1))
      const e = yield* claim(db)
      expect(e?.seq).toBe(1)
      if (!e) throw Error("missing event")
      yield* uncertain(db, e.id)
      expect(yield* claim(db)).toBeUndefined()
      expect((yield* unresolved(db)).length).toBe(1)
      yield* acknowledge(db, e, {
        id: e.id,
        digest: e.digest,
        scope: e.scope,
        memoryId: "mem_fixture",
        durability: "observed",
      })
      expect((yield* claim(db))?.seq).toBe(2)
    }),
  )
})
test("native recovery never blindly requeues claimed delivery", async () => {
  await run(
    Effect.gen(function* () {
      const db = yield* EffectDrizzleSqlite.makeWithDefaults()
      yield* db.transaction((tx) => migration.up(tx))
      yield* db.transaction(() => checkpointOnCommit(db, event, {})(0))
      yield* claim(db)
      expect(
        (yield* recover(db, { previousProcessExited: false, exclusiveDatabaseOwner: true }).pipe(Effect.exit))._tag,
      ).toBe("Failure")
      yield* recover(db, { previousProcessExited: true, exclusiveDatabaseOwner: true })
      yield* recover(db, { previousProcessExited: true, exclusiveDatabaseOwner: true })
      expect(yield* claim(db)).toBeUndefined()
      expect((yield* unresolved(db)).length).toBe(1)
    }),
  )
})
test("native durable receipt label fails conservatively", async () => {
  await run(
    Effect.gen(function* () {
      const db = yield* EffectDrizzleSqlite.makeWithDefaults()
      yield* db.transaction((tx) => migration.up(tx))
      yield* db.transaction(() => checkpointOnCommit(db, event, {})(0))
      const e = yield* claim(db)
      if (!e) throw Error("missing event")
      expect(
        (yield* acknowledge(db, e, {
          id: e.id,
          digest: e.digest,
          scope: e.scope,
          memoryId: "mem_fixture",
          durability: "durable",
        }).pipe(Effect.exit))._tag,
      ).toBe("Failure")
      expect((yield* db.get<{ state: string }>(sql`SELECT state FROM _watoom_outbox`))?.state).toBe("sending")
    }),
  )
})
test("native corrupt persisted content cannot dispatch", async () => {
  await run(
    Effect.gen(function* () {
      const db = yield* EffectDrizzleSqlite.makeWithDefaults()
      yield* db.transaction((tx) => migration.up(tx))
      yield* db.transaction(() => checkpointOnCommit(db, event, {})(0))
      yield* db.run(sql`UPDATE _watoom_outbox SET digest='forged'`)
      expect((yield* claim(db).pipe(Effect.exit))._tag).toBe("Failure")
    }),
  )
})
