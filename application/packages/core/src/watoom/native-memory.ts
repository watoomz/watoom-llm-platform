export * as NativeMemory from "./native-memory.js"
import { Context, Effect, Layer, Stream, Semaphore } from "effect"
import { sql } from "drizzle-orm"
import { makeGlobalNode } from "@opencode/util/effect/app-node"
import { Database } from "../database/database.js"
import { Bus } from "../bus.js"
import { SessionProjector } from "../session/projector.js"
import { SessionEvent } from "../session/event.js"
import { Workflow } from "./workflow.js"
import { Memory } from "./memory.js"
import { Knowledge } from "./knowledge.js"
import { Learning } from "./learning.js"
import { MemoryStatus } from "./memory-status.js"
import { Delivery } from "./delivery.js"
import { envelope, exactKeys, type Scope, type Event, type Envelope } from "./contract.js"

export class Service extends Context.Service<
  Service,
  {
    enabled: boolean
    required: boolean
    status: Effect.Effect<MemoryStatus.Snapshot>
    revise: (scope: Scope, input: Knowledge.Change) => Effect.Effect<{ id: string; state: string }, Error>
    flush: Effect.Effect<void>
    search: (scope: Scope, query: string) => Effect.Effect<Envelope[], Error>
    remember: (event: Event) => Effect.Effect<{ id: string; state: string }, Error>
    learn: (
      scope: Scope,
      sessionID: string,
      input: Learning.Input,
    ) => Effect.Effect<{ id: string; state: string; status: string; duplicate: boolean }, Error>
    recall: (scope: Scope, query: string, budget: number) => Effect.Effect<string[]>
  }
>()("@opencode/NativeMemory") {}
export type Options = { url?: string; secret?: string; required?: boolean }
export function layer(options: Options) {
  return Layer.effect(
    Service,
    Effect.gen(function* () {
      const db = (yield* Database.Service).db
      const bus = yield* Bus.Service
      if (!options.url && options.required) return yield* Effect.die(Error("Mandatory AgentMemory endpoint is missing"))
      const retrieval = {
        attempts: 0,
        failures: 0,
        lastAttempt: null as number | null,
        lastSuccess: null as number | null,
        latencyMs: null as number | null,
        unavailable: false,
      }
      if (!options.url)
        return Service.of({
          enabled: false,
          required: false,
          status: MemoryStatus.read(db, false, false, retrieval),
          flush: Effect.void,
          search: () => Effect.succeed([]),
          remember: () => Effect.fail(Error("AgentMemory disabled")),
          revise: () => Effect.fail(Error("AgentMemory disabled")),
          learn: () => Effect.fail(Error("AgentMemory disabled")),
          recall: () => Effect.succeed([]),
        })
      const url = new URL(options.url)
      if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.search || url.hash)
        return yield* Effect.die(Error("Invalid AgentMemory endpoint"))
      const memory = new Memory.AgentMemory({
        post: async (route, body, signal) => {
          const response = await fetch(new URL(route, url), {
            method: "POST",
            headers: {
              "content-type": "application/json",
              ...(options.secret ? { authorization: "Bearer " + options.secret } : {}),
            },
            body: JSON.stringify(body),
            signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(5000)]) : AbortSignal.timeout(5000),
          })
          if (!response.ok) throw Error("AgentMemory HTTP " + response.status)
          const text = await response.text()
          if (Buffer.byteLength(text) > 262144) throw Error("AgentMemory response exceeds limit")
          return JSON.parse(text)
        },
      })
      // Sending rows can be positively reconciled without claiming another process is dead or resending them.
      const serial = yield* Semaphore.make(1)
      const flush = serial.withPermit(
        Delivery.reconcile(db, memory, 32, true).pipe(
          Effect.andThen(Delivery.drain(db, memory, 32, 5000)),
          Effect.catchCause(() => Effect.void),
        ),
      )
      const definitions = [
        SessionEvent.Created,
        SessionEvent.Execution.Started,
        SessionEvent.Step.Ended,
        SessionEvent.Tool.Called,
        SessionEvent.Tool.Success,
        SessionEvent.Tool.Failed,
        SessionEvent.Compaction.Started,
        SessionEvent.Compaction.Ended,
        SessionEvent.Compaction.Failed,
        SessionEvent.Step.Failed,
        SessionEvent.Execution.Succeeded,
        SessionEvent.Execution.Failed,
        SessionEvent.Execution.Interrupted,
      ] as const
      for (const definition of definitions) {
        yield* bus.project(definition, (event) =>
          Effect.gen(function* () {
            const data = event.data as {
              sessionID: string
              parentID?: string
              files?: string[]
              snapshot?: string
              recent?: string
              reason?: string
              id?: string
            }
            if (event.type === "session.created" && !data.parentID) return
            const row = yield* db.get<{
              project_id: string
              directory: string
              agent: string | null
              parent_id: string | null
            }>(sql`SELECT project_id,directory,agent,parent_id FROM session_v2 WHERE id=${data.sessionID}`)
            if (!row) return
            const references = yield* db.all<{ id: string; seq: number; type: string }>(
              sql`SELECT id,seq,type FROM session_message WHERE session_id=${data.sessionID} ORDER BY seq DESC LIMIT 8`,
            )
            const content = JSON.stringify({
              sessionID: data.sessionID,
              event: event.type,
              time: event.created,
              parentID: row.parent_id ?? data.parentID,
              snapshot: data.snapshot,
              toolCallID: data.id,
              files: data.files?.filter((x) => x.length <= 256 && !/[\x00-\x1f]/.test(x)).slice(0, 16),
              // Compaction state stays in the native journal. Store references, never raw transcript/tool logs.
              recent: data.recent && /^[A-Za-z0-9_:-]{1,256}$/.test(data.recent) ? data.recent : undefined,
              reason: data.reason,
              references,
            })
            const kind =
              event.type === "session.compaction.started"
                ? ("compaction" as const)
                : event.type.startsWith("session.execution.") && event.type !== "session.execution.started"
                  ? ("completion" as const)
                  : ("checkpoint" as const)
            const fact = {
              scope: { project: row.project_id, repository: row.directory, agent: row.agent ?? "default" },
              job: data.sessionID + ":" + event.id,
              seq: 1,
              kind,
              content,
            }
            yield* Workflow.checkpointOnCommit(
              db,
              fact,
              { sessionID: data.sessionID, nativeEventID: event.id, time: event.created, references },
              0,
            )(0)
            if (row.parent_id) {
              const parent = yield* db.get<{ project_id: string; directory: string; agent: string | null }>(
                sql`SELECT project_id,directory,agent FROM session_v2 WHERE id=${row.parent_id}`,
              )
              if (parent && parent.project_id === row.project_id && parent.directory === row.directory)
                yield* Workflow.checkpointOnCommit(
                  db,
                  {
                    ...fact,
                    scope: {
                      project: parent.project_id,
                      repository: parent.directory,
                      agent: parent.agent ?? "default",
                    },
                    job: row.parent_id + ":child:" + event.id,
                  },
                  { childSessionID: data.sessionID, nativeEventID: event.id, references },
                  0,
                )(0)
            }
          }).pipe(Effect.orDie),
        )
      }
      yield* bus.subscribe(definitions).pipe(
        Stream.runForEach(() => flush),
        Effect.forkScoped({ startImmediately: true }),
      )
      const remember = (event: Event) =>
        Effect.gen(function* () {
          const e = yield* Effect.try({
            try: () => envelope(event),
            catch: () => Error("Invalid or sensitive memory content"),
          })
          yield* db.transaction(() => Workflow.checkpointOnCommit(db, eEvent(e), { explicit: true, id: e.id })(0), {
            behavior: "immediate",
          })
          yield* flush
          const row = yield* db.get<{ state: string }>(sql`SELECT state FROM _watoom_outbox WHERE id=${e.id}`)
          return { id: e.id, state: row?.state ?? "unknown" }
        })
      yield* flush.pipe(Effect.forkScoped({ startImmediately: true }))
      const revisions = (scope: Scope) =>
        db
          .all<{
            body: string
          }>(
            sql`SELECT body FROM _watoom_outbox WHERE scope=${JSON.stringify([scope.project, scope.repository, scope.agent])} AND job LIKE 'knowledge:%' ORDER BY rowid`,
          )
          .pipe(Effect.map((rows) => rows.map((row) => JSON.parse(row.body) as Envelope)))
      const revise = (scope: Scope, input: Knowledge.Change) =>
        Effect.gen(function* () {
          if (!input || !Array.isArray(input.targets) || input.targets.length > 16)
            return yield* Effect.fail(Error("Invalid memory targets"))
          const saved = yield* db.transaction(
            () =>
              Effect.gen(function* () {
                const sources: Envelope[] = []
                for (const id of input.targets) {
                  const row = yield* db.get<{ body: string; state: string }>(
                    sql`SELECT body,state FROM _watoom_outbox WHERE id=${id}`,
                  )
                  if (!row || row.state !== "observed")
                    return yield* Effect.fail(Error("Memory source has no verified acknowledgment"))
                  sources.push(JSON.parse(row.body) as Envelope)
                }
                const event = yield* Effect.try({
                  try: () => Knowledge.prepare(scope, input, sources),
                  catch: () => Error("Invalid or cross-scope memory change"),
                })
                const prior = yield* db.get<{ digest: string }>(
                  sql`SELECT digest FROM _watoom_outbox WHERE id=${event.id}`,
                )
                if (prior && prior.digest !== event.digest)
                  return yield* Effect.fail(Error("Memory change request conflicts with an existing revision"))
                if (!prior && Knowledge.active(sources, yield* revisions(scope)).length !== sources.length)
                  return yield* Effect.fail(Error("Memory source is superseded; revise its current successor"))
                yield* Workflow.checkpointOnCommit(
                  db,
                  eEvent(event),
                  { knowledge: true, targets: [...input.targets].sort(), action: input.action },
                  0,
                )(0)
                return event
              }),
            { behavior: "immediate" },
          )
          yield* flush
          const row = yield* db.get<{ state: string }>(sql`SELECT state FROM _watoom_outbox WHERE id=${saved.id}`)
          return { id: saved.id, state: row?.state ?? "unknown" }
        })
      const learn = (scope: Scope, sessionID: string, input: Learning.Input) =>
        Effect.gen(function* () {
          const invalid = Learning.validate(input)
          if (invalid) return yield* Effect.fail(Error(invalid))
          // Evidence is read from the runtime's own records of this session and its direct children.
          const rows = yield* db
            .all<{ session_id: string; time_created: number; data: string }>(
              sql`SELECT session_id,time_created,data FROM session_message WHERE type='assistant' AND session_id IN (SELECT id FROM session_v2 WHERE id=${sessionID} OR parent_id=${sessionID}) ORDER BY time_created DESC LIMIT 600`,
            )
            .pipe(Effect.orDie)
          const verified = Learning.verify(input, rows.flatMap((row) => toolRecords(row)))
          if (typeof verified === "string") return yield* Effect.fail(Error(verified))
          const base = { project: scope.project, repository: scope.repository }
          const key = JSON.stringify([scope.project, scope.repository, Learning.AGENT])
          const prior = yield* db
            .all<{ id: string; seq: number; body: string; state: string }>(
              sql`SELECT id,seq,body,state FROM _watoom_outbox WHERE scope=${key} AND job=${Learning.job(input)} ORDER BY seq DESC`,
            )
            .pipe(Effect.orDie)
          const fingerprint = Learning.fingerprint(input)
          const same = prior.find((row) => {
            try {
              return JSON.parse((JSON.parse(row.body) as Envelope).content).fingerprint === fingerprint
            } catch {
              return false
            }
          })
          if (same) return { id: same.id, state: same.state, status: verified.status, duplicate: true }
          const next = yield* Effect.try({
            try: () => Learning.event(base, input, verified, { sessionID, seq: (prior[0]?.seq ?? 0) + 1, recordedBy: scope.agent }),
            catch: (error) => (error instanceof Error ? error : Error("LEARN_INVALID")),
          })
          const saved = yield* remember(next)
          return { ...saved, status: verified.status, duplicate: false }
        })
      // Targeted retrieval of learned knowledge: one bounded search, compact summaries, never fails the caller.
      const recall = (scope: Scope, query: string, budget: number) =>
        Effect.tryPromise({
          try: async (signal) => {
            const knowledge = { project: scope.project, repository: scope.repository, agent: Learning.AGENT }
            retrieval.attempts++
            retrieval.lastAttempt = Date.now()
            const started = performance.now()
            try {
              const result = (await memory.search(
                { query: query.slice(0, 1024), project: scope.project, agentId: Learning.AGENT, limit: 16, format: "full" },
                AbortSignal.any([signal, AbortSignal.timeout(2500)]),
              )) as { results?: { observation?: { narrative?: string } }[] }
              retrieval.lastSuccess = Date.now()
              retrieval.unavailable = false
              const values = decodeResults(result.results ?? [], knowledge).flatMap((value) => Learning.read(value) ?? [])
              return Learning.render(Learning.current(values).slice(0, 6), budget)
            } catch (error) {
              retrieval.failures++
              retrieval.unavailable = true
              throw error
            } finally {
              retrieval.latencyMs = Math.round(performance.now() - started)
            }
          },
          catch: () => Error("recall unavailable"),
        }).pipe(Effect.orElseSucceed(() => [] as string[]))
      return Service.of({
        enabled: true,
        learn,
        recall,
        required: options.required ?? false,
        status: MemoryStatus.read(db, true, options.required ?? false, retrieval),
        flush,
        remember,
        revise,
        search: (scope, query) =>
          Effect.gen(function* () {
            const history = yield* revisions(scope)
            const observed = new Set(
              (yield* db
                .all<{ id: string }>(
                  sql`SELECT id FROM _watoom_outbox WHERE scope=${JSON.stringify([scope.project, scope.repository, scope.agent])} AND job LIKE 'knowledge:%' AND state='observed'`,
                )
                .pipe(Effect.orDie)).map((row) => row.id),
            )
            return yield* Effect.tryPromise({
              try: async (signal) => {
                retrieval.attempts++
                retrieval.lastAttempt = Date.now()
                const started = performance.now()
                try {
                  const result = (await memory.search(
                    { query, project: scope.project, agentId: scope.agent, limit: 16, format: "full" },
                    signal,
                  )) as { results?: { observation?: { narrative?: string } }[] }
                  const found = decodeResults(result.results ?? [], scope)
                  const successors = Knowledge.active(history, history)
                    .filter((revision) =>
                      Knowledge.change(revision)?.targets.some((id) => found.some((value) => value.id === id)),
                    )
                    .slice(-4)
                  // Successor revisions are this scope's own outbox envelopes: exact-key, already
                  // acknowledged by AgentMemory. No BM25 search is issued for revision hashes.
                  const additional = successors.filter((revision) => observed.has(revision.id))
                  const unique = [
                    ...new Map([...found, ...additional].map((value) => [value.id, value])).values(),
                  ].slice(0, 32)
                  retrieval.lastSuccess = Date.now()
                  retrieval.unavailable = false
                  return Knowledge.active(unique, history).slice(0, 16)
                } catch (error) {
                  retrieval.failures++
                  retrieval.unavailable = true
                  throw error
                } finally {
                  retrieval.latencyMs = Math.round(performance.now() - started)
                }
              },
              catch: () => Error("AgentMemory retrieval unavailable"),
            })
          }),
      })
    }),
  )
}
export function configured(options: Options) {
  return makeGlobalNode({
    service: Service,
    layer: layer(options),
    deps: [Database.node, Bus.node, SessionProjector.node],
  })
}
export const node = configured({
  url: process.env.AGENTMEMORY_URL,
  secret: process.env.AGENTMEMORY_SECRET,
  required: process.env.WATOOM_MEMORY_REQUIRED === "true",
})

function decodeResults(items: { observation?: { narrative?: string } }[], scope: Scope): Envelope[] {
  return items.slice(0, 16).flatMap((item) => {
    try {
      const value = JSON.parse(item.observation?.narrative ?? "")
      exactKeys(value, ["scope", "job", "seq", "kind", "content", "version", "id", "digest"])
      const verified = envelope({
        scope: value.scope,
        job: value.job,
        seq: value.seq,
        kind: value.kind,
        content: value.content,
      })
      return value.version === 2 &&
        value.id === verified.id &&
        value.digest === verified.digest &&
        verified.scope.project === scope.project &&
        verified.scope.repository === scope.repository &&
        verified.scope.agent === scope.agent
        ? [verified]
        : []
    } catch {
      return []
    }
  })
}

/** Settled tool calls from one stored assistant message. */
export function toolRecords(row: { session_id: string; time_created: number; data: string }): Learning.ToolRecord[] {
  try {
    const content = (JSON.parse(row.data) as { content?: unknown[] }).content ?? []
    return content.flatMap((part) => {
      const p = part as {
        type?: string
        id?: string
        name?: string
        time?: { completed?: number }
        state?: { status?: string; input?: unknown; metadata?: { exit?: unknown } }
      }
      if (p.type !== "tool" || typeof p.id !== "string" || typeof p.name !== "string") return []
      if (p.state?.status !== "completed" && p.state?.status !== "error") return []
      const exit = p.state.metadata?.exit
      return [
        {
          sessionID: row.session_id,
          id: p.id,
          name: p.name,
          status: p.state.status,
          input: p.state.input,
          exit: typeof exit === "number" ? exit : undefined,
          time: p.time?.completed ?? row.time_created,
        },
      ]
    })
  } catch {
    return []
  }
}

function eEvent(e: Envelope): Event {
  return { scope: e.scope, job: e.job, seq: e.seq, kind: e.kind, content: e.content }
}
