export * as MemoryObservability from "./memory-status.js"
import { Schema } from "effect"
const Time = Schema.NullOr(Schema.Number)
export const Status = Schema.Struct({
  memory: Schema.Struct({
    enabled: Schema.Boolean,
    required: Schema.Boolean,
    sampledAt: Schema.Number,
    outbox: Schema.Struct({
      pending: Schema.Number,
      sending: Schema.Number,
      uncertain: Schema.Number,
      observed: Schema.Number,
      attempts: Schema.Number,
      lastCheckpoint: Time,
      lastObserved: Time,
      oldestPending: Time,
    }),
    retrieval: Schema.Struct({
      attempts: Schema.Number,
      failures: Schema.Number,
      lastAttempt: Time,
      lastSuccess: Time,
      latencyMs: Time,
      unavailable: Schema.Boolean,
    }),
    warnings: Schema.Array(Schema.String),
    recent: Schema.Array(
      Schema.Struct({
        id: Schema.String,
        job: Schema.String,
        state: Schema.String,
        attempts: Schema.Number,
        created: Time,
        observed: Time,
      }),
    ),
  }),
  ownership: Schema.Struct({
    available: Schema.Boolean,
    stale: Schema.Boolean,
    sampledAt: Time,
    phase: Schema.NullOr(Schema.String),
    owner: Schema.NullOr(Schema.String),
    generation: Time,
    uncertain: Schema.NullOr(Schema.Boolean),
    activeRequests: Time,
    primary: Schema.NullOr(Schema.String),
  }),
})
export type Status = typeof Status.Type
