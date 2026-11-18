import { test, expect } from "bun:test"
import { Effect } from "effect"
import { sql } from "drizzle-orm"
import { SqliteClient } from "@effect/sql-sqlite-bun"
import { EffectDrizzleSqlite } from "@opencode/core/database/drizzle"
import { Workflow } from "@opencode/core/watoom/workflow"
import { Delivery } from "@opencode/core/watoom/delivery"
import { Memory } from "@opencode/core/watoom/memory"
const event = {
  scope: { project: "p", repository: "r", agent: "a" },
  job: "j",
  seq: 1,
  kind: "checkpoint" as const,
  content: "verified fixture result",
}
const run = (
  body: (
    db: Effect.Success<ReturnType<typeof EffectDrizzleSqlite.makeWithDefaults>>,
  ) => Effect.Effect<unknown, unknown>,
) =>
  Effect.runPromise(
    Effect.gen(function* () {
      const db = yield* EffectDrizzleSqlite.makeWithDefaults()
      yield* db.transaction((tx) => Workflow.migration.up(tx))
      yield* db.transaction(() => Workflow.checkpointOnCommit(db, event, {})(0))
      return yield* body(db)
    }).pipe(Effect.provide(SqliteClient.layer({ filename: ":memory:", disableWAL: true })), Effect.scoped),
  )
test("native memory client and delivery validate source-backed acknowledgment", () =>
  run((db) =>
    Effect.gen(function* () {
      let calls = 0
      const memory = new Memory.AgentMemory({
        post: async (path, body) => {
          calls++
          expect(path).toBe("/agentmemory/remember")
          return {
            success: true,
            memory: { id: "mem_fixture", content: body.content, project: body.project, agentId: body.agentId },
          }
        },
      })
      yield* Delivery.drain(db, memory)
      expect(calls).toBe(1)
      expect((yield* db.get<{ state: string }>(sql`SELECT state FROM _watoom_outbox`))?.state).toBe("observed")
    }),
  ))
test("native unavailable memory becomes uncertain without blind replay", () =>
  run((db) =>
    Effect.gen(function* () {
      let calls = 0
      const memory = new Memory.AgentMemory({
        post: async () => {
          calls++
          throw Error("offline")
        },
      })
      yield* Delivery.drain(db, memory)
      yield* Delivery.drain(db, memory)
      expect(calls).toBe(1)
      expect((yield* db.get<{ state: string }>(sql`SELECT state FROM _watoom_outbox`))?.state).toBe("uncertain")
    }),
  ))
const later = Date.now() + 3600000
test("native lost acknowledgment reconciles by exact re-send without search", () =>
  run((db) =>
    Effect.gen(function* () {
      const paths: string[] = []
      let lose = true
      const memory = new Memory.AgentMemory({
        post: async (path, body) => {
          paths.push(path)
          if (lose) {
            lose = false
            throw Error("lost acknowledgment")
          }
          return {
            success: true,
            memory: { id: "mem_fixture", content: body.content, project: body.project, agentId: body.agentId },
          }
        },
      })
      yield* Delivery.drain(db, memory)
      expect((yield* db.get<{ state: string }>(sql`SELECT state FROM _watoom_outbox`))?.state).toBe("uncertain")
      yield* Delivery.reconcile(db, memory)
      expect(paths).toEqual(["/agentmemory/remember", "/agentmemory/remember"])
      const row = yield* db.get<{ state: string; receipt: string }>(sql`SELECT state,receipt FROM _watoom_outbox`)
      expect(row?.state).toBe("observed")
      expect(JSON.parse(row!.receipt).memoryId).toBe("mem_fixture")
    }),
  ))
test("native re-send with mismatched stored content stays unresolved", () =>
  run((db) =>
    Effect.gen(function* () {
      let calls = 0
      const memory = new Memory.AgentMemory({
        post: async (_path, body) => {
          if (++calls === 1) throw Error("lost")
          return { success: true, memory: { id: "mem_x", content: "different", project: body.project, agentId: body.agentId } }
        },
      })
      yield* Delivery.drain(db, memory)
      yield* Delivery.reconcile(db, memory)
      yield* Delivery.drain(db, memory)
      expect(calls).toBe(2)
      expect((yield* db.get<{ state: string }>(sql`SELECT state FROM _watoom_outbox`))?.state).toBe("uncertain")
    }),
  ))
test("native reconciliation backs off instead of retrying on every event", () =>
  run((db) =>
    Effect.gen(function* () {
      let calls = 0
      const memory = new Memory.AgentMemory({
        post: async () => {
          calls++
          throw Error("offline")
        },
      })
      yield* Delivery.drain(db, memory)
      // First reconciliation is immediate; the following events within the backoff window are no-ops.
      for (let i = 0; i < 5; i++) yield* Delivery.reconcile(db, memory)
      expect(calls).toBe(2)
      expect((yield* Workflow.unresolved(db, 16, false, later)).length).toBe(1)
      yield* db.run(sql`UPDATE _watoom_outbox SET time_attempted=0`)
      yield* Delivery.reconcile(db, memory)
      yield* Delivery.reconcile(db, memory)
      expect(calls).toBe(3)
      const row = yield* db.get<{ attempts: number }>(sql`SELECT attempts FROM _watoom_outbox`)
      expect(row?.attempts).toBe(3)
    }),
  ))
test("native timeout preserves uncertainty and no late replay", () =>
  run((db) =>
    Effect.gen(function* () {
      const memory = new Memory.AgentMemory({ post: async () => new Promise<unknown>(() => {}) })
      yield* Delivery.drain(db, memory, 1, 10)
      expect((yield* db.get<{ state: string }>(sql`SELECT state FROM _watoom_outbox`))?.state).toBe("uncertain")
    }),
  ))
