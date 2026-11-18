export * as MemoryStatus from "./memory-status.js"
import { Effect } from "effect"
import { sql } from "drizzle-orm"
import type { EffectDrizzleSqlite } from "../database/drizzle.js"
type DB = Effect.Success<ReturnType<typeof EffectDrizzleSqlite.makeWithDefaults>>
export type Retrieval = {
  attempts: number
  failures: number
  lastAttempt: number | null
  lastSuccess: number | null
  latencyMs: number | null
  unavailable: boolean
}
export type Snapshot = {
  enabled: boolean
  required: boolean
  sampledAt: number
  outbox: {
    pending: number
    sending: number
    uncertain: number
    observed: number
    attempts: number
    lastCheckpoint: number | null
    lastObserved: number | null
    oldestPending: number | null
  }
  retrieval: Retrieval
  warnings: string[]
  recent: {
    id: string
    job: string
    state: string
    attempts: number
    created: number | null
    observed: number | null
  }[]
}
export function read(db: DB, enabled: boolean, required: boolean, retrieval: Retrieval) {
  return Effect.gen(function* () {
    const rows = yield* db.all<{ state: string; count: number }>(
      sql`SELECT state,count(*) AS count FROM _watoom_outbox GROUP BY state`,
    )
    const counts = Object.fromEntries(rows.map((row) => [row.state, row.count]))
    const times = yield* db.get<{
      attempts: number
      created: number | null
      observed: number | null
      oldest: number | null
    }>(
      sql`SELECT coalesce(sum(attempts),0) AS attempts,max(time_created) AS created,max(time_observed) AS observed,min(CASE WHEN state!='observed' THEN time_created END) AS oldest FROM _watoom_outbox`,
    )
    const recent = yield* db.all<{
      id: string
      job: string
      state: string
      attempts: number
      created: number | null
      observed: number | null
    }>(
      sql`SELECT id,job,state,attempts,time_created AS created,time_observed AS observed FROM _watoom_outbox ORDER BY rowid DESC LIMIT 20`,
    )
    const warnings = [
      ...(times?.oldest && Date.now() - times.oldest > 300000 ? ["delivery-backlog-stale"] : []),
      ...(!enabled ? ["memory-disabled"] : []),
      ...(counts.uncertain ? ["delivery-uncertain"] : []),
      ...(counts.pending || counts.sending ? ["delivery-pending"] : []),
      ...(retrieval.unavailable ? ["retrieval-unavailable"] : []),
      ...(!times?.observed && counts.observed ? ["historical-acknowledgment-time-unknown"] : []),
    ]
    return {
      enabled,
      required,
      sampledAt: Date.now(),
      outbox: {
        pending: counts.pending ?? 0,
        sending: counts.sending ?? 0,
        uncertain: counts.uncertain ?? 0,
        observed: counts.observed ?? 0,
        attempts: times?.attempts ?? 0,
        lastCheckpoint: times?.created ?? null,
        lastObserved: times?.observed ?? null,
        oldestPending: times?.oldest ?? null,
      },
      retrieval: { ...retrieval },
      warnings,
      recent,
    } satisfies Snapshot
  }).pipe(Effect.orDie)
}
