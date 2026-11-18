export * as Delivery from "./delivery.js"
import { Effect } from "effect"
import type { EffectDrizzleSqlite } from "../database/drizzle.js"
import type { MemoryPort } from "./contract.js"
import { Workflow } from "./workflow.js"
type DB = Effect.Success<ReturnType<typeof EffectDrizzleSqlite.makeWithDefaults>>
/** Explicit post-commit/wakeup processing. No interval, daemon or second database. */
export function drain(db: DB, memory: MemoryPort, budget = 16, timeoutMs = 1000) {
  if (
    !Number.isInteger(budget) ||
    budget < 1 ||
    budget > 32 ||
    !Number.isInteger(timeoutMs) ||
    timeoutMs < 1 ||
    timeoutMs > 30000
  )
    return Effect.die(Error("native delivery bounds"))
  return Effect.gen(function* () {
    for (let i = 0; i < budget; i++) {
      const e = yield* Workflow.claim(db)
      if (!e) return
      yield* Effect.uninterruptibleMask((restore) =>
        restore(Effect.tryPromise((signal) => memory.remember(e, signal)).pipe(Effect.timeout(timeoutMs))).pipe(
          Effect.flatMap((r) => Workflow.acknowledge(db, e, r)),
          Effect.exit,
          Effect.flatMap((exit) => (exit._tag === "Failure" ? Workflow.uncertain(db, e.id) : Effect.void)),
        ),
      )
    }
  })
}
export function reconcile(db: DB, memory: MemoryPort, limit = 16, includeSending = false) {
  return Effect.gen(function* () {
    const events = yield* Workflow.unresolved(db, limit, includeSending)
    for (const e of events) {
      yield* Workflow.attempted(db, e.id)
      const result = yield* Effect.tryPromise((signal) => memory.reconcile(e, signal)).pipe(
        Effect.timeout(5000),
        Effect.exit,
      )
      if (result._tag === "Success" && result.value) yield* Workflow.acknowledge(db, e, result.value).pipe(Effect.exit)
      // Unverified, rejected and unavailable responses leave the row unresolved until its next backoff slot.
    }
  })
}
