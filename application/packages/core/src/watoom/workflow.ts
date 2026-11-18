export * as Workflow from "./workflow.js"

/** Isolated source overlay for pinned OpenCode cd9a14a. Not registered or deployed. */
import { Effect, Option } from "effect"
import { sql } from "drizzle-orm"
import type { EffectDrizzleSqlite } from "../database/drizzle.js"
import { migrationID, statements } from "./schema.js"
import {
  envelope,
  scopeKey,
  checkpointJson,
  exactKeys,
  matches,
  type Event,
  type Envelope,
  type Receipt,
} from "./contract.js"
type DB = Effect.Success<ReturnType<typeof EffectDrizzleSqlite.makeWithDefaults>>
type Transaction = Parameters<Parameters<DB["transaction"]>[0]>[0]
export const migration = {
  id: migrationID,
  up: (tx: Transaction) =>
    Effect.gen(function* () {
      for (const statement of statements) yield* tx.run(sql.raw(statement))
    }),
}
/** Supply to Bus.PublishOptions.commit on the same native database fiber/transaction.
 * Never invoke an HTTP request here. The caller must validate the exact lifecycle event.
 */
export function checkpointOnCommit(db: DB, event: Event, checkpoint: unknown, pendingLimit = 128) {
  return (_nativeSequence: number) =>
    Effect.gen(function* () {
      const transaction = yield* Effect.serviceOption(db.$client.transactionService)
      if (Option.isNone(transaction)) return yield* Effect.die(Error("native transaction required"))
      const e = envelope(event),
        scope = scopeKey(e.scope),
        body = checkpointJson(checkpoint)
      if (
        Buffer.byteLength(body) > 16384 ||
        /(?:-----BEGIN .*PRIVATE KEY|Bearer\s+\S+|(?:password|api[_-]?key|secret)["\s]*[:=]["\s]*\S+)/i.test(body)
      )
        return yield* Effect.die(Error("unsafe checkpoint"))
      const prior = yield* db.get<{ digest: string; checkpoint_body: string }>(
        sql`SELECT digest,checkpoint_body FROM _watoom_outbox WHERE id=${e.id}`,
      )
      if (prior) {
        if (prior.digest !== e.digest || prior.checkpoint_body !== body)
          return yield* Effect.die(Error("event conflict"))
        return
      }
      const current = yield* db.get<{ seq: number }>(
        sql`SELECT seq FROM _watoom_checkpoint WHERE scope=${scope} AND job=${e.job}`,
      )
      if (e.seq !== (current?.seq ?? 0) + 1) return yield* Effect.die(Error("noncontiguous workflow sequence"))
      const count = yield* db.get<{ n: number }>(
        sql`SELECT count(*) AS n FROM _watoom_outbox WHERE state IN ('pending','sending','uncertain')`,
      )
      if (pendingLimit > 0 && (count?.n ?? 0) >= pendingLimit) return yield* Effect.die(Error("workflow backpressure"))
      yield* db.run(
        sql`INSERT INTO _watoom_outbox(id,scope,job,seq,digest,body,checkpoint_body,state,time_created) VALUES(${e.id},${scope},${e.job},${e.seq},${e.digest},${JSON.stringify(e)},${body},'pending',${Date.now()})`,
      )
      yield* db.run(
        sql`INSERT INTO _watoom_checkpoint VALUES(${scope},${e.job},${e.seq},${body}) ON CONFLICT(scope,job) DO UPDATE SET seq=excluded.seq,body=excluded.body`,
      )
    }).pipe(Effect.orDie)
}

type OutboxRow = { id: string; scope: string; job: string; seq: number; digest: string; body: string; state: string }
function decode(row: OutboxRow): Envelope {
  const parsed = JSON.parse(row.body)
  exactKeys(parsed, ["scope", "job", "seq", "kind", "content", "version", "id", "digest"])
  const e = envelope({
    scope: parsed.scope,
    job: parsed.job,
    seq: parsed.seq,
    kind: parsed.kind,
    content: parsed.content,
  })
  if (
    parsed.version !== 2 ||
    parsed.id !== e.id ||
    parsed.digest !== e.digest ||
    row.id !== e.id ||
    row.digest !== e.digest ||
    row.scope !== scopeKey(e.scope) ||
    row.job !== e.job ||
    row.seq !== e.seq
  )
    throw Error("native outbox integrity failure")
  Object.freeze(e.scope)
  return Object.freeze(e)
}
export function claim(db: DB) {
  return db
    .transaction(
      () =>
        Effect.gen(function* () {
          const row = yield* db.get<OutboxRow>(
            sql`SELECT a.* FROM _watoom_outbox a WHERE a.state='pending' AND NOT EXISTS(SELECT 1 FROM _watoom_outbox b WHERE b.scope=a.scope AND b.job=a.job AND b.seq<a.seq AND b.state!='observed') ORDER BY a.rowid LIMIT 1`,
          )
          if (!row) return undefined
          const e = decode(row)
          yield* db.run(
            sql`UPDATE _watoom_outbox SET state='sending',attempts=attempts+1,time_attempted=${Date.now()} WHERE id=${e.id} AND state='pending'`,
          )
          return e
        }),
      { behavior: "immediate" },
    )
    .pipe(Effect.orDie)
}
export function uncertain(db: DB, id: string) {
  return db
    .run(
      sql`UPDATE _watoom_outbox SET state='uncertain',last_error='ambiguous acknowledgment' WHERE id=${id} AND state='sending'`,
    )
    .pipe(Effect.orDie, Effect.asVoid)
}
/** Record a reconciliation attempt so backoff applies to the next one. */
export function attempted(db: DB, id: string, now = Date.now()) {
  return db
    .run(
      sql`UPDATE _watoom_outbox SET attempts=attempts+1,time_attempted=${now} WHERE id=${id} AND state IN ('sending','uncertain')`,
    )
    .pipe(Effect.orDie, Effect.asVoid)
}
export function acknowledge(db: DB, e: Envelope, r: Receipt) {
  return db
    .transaction(
      () =>
        Effect.gen(function* () {
          const row = yield* db.get<OutboxRow>(sql`SELECT * FROM _watoom_outbox WHERE id=${e.id}`)
          if (!row || !["sending", "uncertain"].includes(row.state))
            return yield* Effect.die(Error("invalid native receipt transition"))
          const stored = decode(row)
          if (
            e.id !== stored.id ||
            e.digest !== stored.digest ||
            scopeKey(e.scope) !== scopeKey(stored.scope) ||
            !matches(stored, r) ||
            r.durability !== "observed"
          )
            return yield* Effect.die(Error("native receipt mismatch or unverified durability"))
          yield* db.run(
            sql`UPDATE _watoom_outbox SET state='observed',receipt=${JSON.stringify(r)},last_error=NULL,time_observed=${Date.now()} WHERE id=${stored.id} AND state IN ('sending','uncertain')`,
          )
        }),
      { behavior: "immediate" },
    )
    .pipe(Effect.orDie)
}
export function recover(db: DB, proof: { previousProcessExited: boolean; exclusiveDatabaseOwner: boolean }) {
  if (!proof.previousProcessExited || !proof.exclusiveDatabaseOwner)
    return Effect.die(Error("native owner-death proof required"))
  return db
    .run(
      sql`UPDATE _watoom_outbox SET state='uncertain',last_error='previous process stopped before verified receipt' WHERE state='sending'`,
    )
    .pipe(Effect.orDie, Effect.asVoid)
}
export function unresolved(db: DB, limit = 16, includeSending = false, now = Date.now()) {
  if (!Number.isInteger(limit) || limit < 1 || limit > 32) return Effect.die(Error("invalid reconciliation bound"))
  return db
    .all<OutboxRow>(
      // The first reconciliation after a send is immediate (crash recovery); later retries back off
      // exponentially (30 s doubling, capped at 1 h) because flush runs on every session event.
      sql`SELECT * FROM _watoom_outbox WHERE (state='uncertain' OR (${includeSending} AND state='sending')) AND COALESCE(time_attempted,0) <= ${now} - (CASE WHEN attempts <= 1 THEN 0 ELSE MIN(3600000, 30000 * (1 << MIN(attempts - 2, 7))) END) ORDER BY rowid LIMIT ${limit}`,
    )
    .pipe(
      Effect.map((rows) => rows.map(decode)),
      Effect.orDie,
    )
}
