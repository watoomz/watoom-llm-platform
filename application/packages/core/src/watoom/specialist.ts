export * as Specialist from "./specialist.js"

/** Generic delegation over native persistence. Live GPU ownership is deliberately unavailable. */
import { Effect } from "effect"
import { sql } from "drizzle-orm"
import { createHash } from "node:crypto"
import type { EffectDrizzleSqlite } from "../database/drizzle.js"
import { checkpointOnCommit } from "./workflow.js"
import { checkpointJson, scopeKey, exactKeys, type Scope } from "./contract.js"
type DB = Effect.Success<ReturnType<typeof EffectDrizzleSqlite.makeWithDefaults>>
type Transaction = Parameters<Parameters<DB["transaction"]>[0]>[0]
export type ModelIdentity = {
  model: string
  modelSha256: string
  configurationSha256: string
  projectorSha256?: string
  deploymentUID: string
  router: string
}
export type Artifact = { reference: string; sha256: string; bytes: number }
export type Outcome = { summary: string; artifacts: Artifact[] }
export type Descriptor = {
  id: string
  capabilities: readonly string[]
  backend: string
  model: ModelIdentity
  execution: "cpu" | "independent" | "exclusive-gpu"
  inputSchema: string
  outputSchema: string
  timeoutMs: number
  maxInputBytes: number
  resources: { cpuCores: number; ramMiB: number; gpuMiB: number; diskMiB: number }
  requiredSkills: readonly string[]
  requiredTools: readonly string[]
  cancellation: "cooperative-abort"
  recovery: "positive-receipt-only"
  restoration: "exact-primary-identity"
  sourceCommit: string
  evidence: "fixture" | "verified-source"
}
export interface Backend {
  validateInput(input: unknown, capability?: string): void
  execute(operationID: string, input: unknown, signal: AbortSignal): Promise<Outcome>
  verifyArtifacts(outcome: Outcome): Promise<boolean>
}
export type Lease = { job: string; generation: number }
/** Semantic controller boundary, not a claim that these are deployed wire action names. */
export interface GpuAuthority {
  kind: "simulation" | "g3h-g3g"
  reconcileLease?: (operationID: string) => Promise<Lease | undefined>
  acquire(job: string, primary: ModelIdentity): Promise<Lease>
  activate(lease: Lease, specialist: Descriptor): Promise<void>
  restore(lease: Lease, primary: ModelIdentity): Promise<void>
  validatePrimary(lease: Lease, primary: ModelIdentity): Promise<boolean>
  recover(lease: Lease, primary: ModelIdentity, ownerExited: boolean): Promise<void>
}
const sha = (s: string) => createHash("sha256").update(s).digest("hex")
function identity(value: ModelIdentity) {
  exactKeys(value, [
    "model",
    "modelSha256",
    "configurationSha256",
    "deploymentUID",
    "router",
    ...(Object.prototype.hasOwnProperty.call(value, "projectorSha256") ? ["projectorSha256"] : []),
  ])
  if (
    !value ||
    !value.model ||
    !value.deploymentUID ||
    !value.router ||
    ![value.modelSha256, value.configurationSha256, ...(value.projectorSha256 ? [value.projectorSha256] : [])].every(
      (x) => /^[a-f0-9]{64}$/.test(x),
    )
  )
    throw Error("unverified model identity")
  checkpointJson(value)
}
export class Registry {
  private entries = new Map<string, { descriptor: Descriptor; backend: Backend }>()
  register(input: Descriptor, backend: Backend) {
    exactKeys(input, [
      "id",
      "capabilities",
      "backend",
      "model",
      "execution",
      "inputSchema",
      "outputSchema",
      "timeoutMs",
      "maxInputBytes",
      "resources",
      "requiredSkills",
      "requiredTools",
      "cancellation",
      "recovery",
      "restoration",
      "sourceCommit",
      "evidence",
    ])
    identity(input.model)
    exactKeys(input.resources, ["cpuCores", "ramMiB", "gpuMiB", "diskMiB"])
    if (
      !Number.isInteger(input.resources.cpuCores) ||
      input.resources.cpuCores < 1 ||
      input.resources.cpuCores > 4 ||
      !Number.isInteger(input.resources.ramMiB) ||
      input.resources.ramMiB < 1 ||
      input.resources.ramMiB > 2048 ||
      !Number.isInteger(input.resources.gpuMiB) ||
      input.resources.gpuMiB < 0 ||
      input.resources.gpuMiB > 20480 ||
      !Number.isInteger(input.resources.diskMiB) ||
      input.resources.diskMiB < 1 ||
      input.resources.diskMiB > 1024 ||
      (input.execution === "cpu" && input.resources.gpuMiB !== 0) ||
      !Array.isArray(input.requiredSkills) ||
      !Array.isArray(input.requiredTools) ||
      input.requiredSkills.length > 16 ||
      input.requiredTools.length > 16 ||
      input.cancellation !== "cooperative-abort" ||
      input.recovery !== "positive-receipt-only" ||
      input.restoration !== "exact-primary-identity"
    )
      throw Error("invalid specialist resource or recovery contract")
    if (
      !/^[a-z][a-z0-9.-]{0,63}$/.test(input.id) ||
      !input.capabilities.length ||
      input.capabilities.some((x) => !/^[a-z0-9][a-z0-9.-]{0,63}$/.test(x)) ||
      !input.backend ||
      !input.inputSchema ||
      !input.outputSchema ||
      !["cpu", "independent", "exclusive-gpu"].includes(input.execution) ||
      !Number.isInteger(input.timeoutMs) ||
      input.timeoutMs < 1 ||
      input.timeoutMs > 900000 ||
      !Number.isInteger(input.maxInputBytes) ||
      input.maxInputBytes < 1 ||
      input.maxInputBytes > 16384 ||
      !/^[a-f0-9]{40}$/.test(input.sourceCommit) ||
      !["fixture", "verified-source"].includes(input.evidence) ||
      this.entries.has(input.id)
    )
      throw Error("invalid or duplicate specialist")
    const descriptor = Object.freeze({
      ...input,
      capabilities: Object.freeze([...input.capabilities]),
      model: Object.freeze({ ...input.model }),
      resources: Object.freeze({ ...input.resources }),
      requiredSkills: Object.freeze([...input.requiredSkills]),
      requiredTools: Object.freeze([...input.requiredTools]),
    })
    this.entries.set(input.id, { descriptor, backend })
  }
  list() { return [...this.entries.values()].map((entry) => entry.descriptor) }
  select(capability: string, specialistID?: string) {
    const entries = [...this.entries.values()].filter(
      (x) => x.descriptor.capabilities.includes(capability) && (!specialistID || x.descriptor.id === specialistID),
    )
    if (entries.length !== 1) throw Error("unknown or ambiguous specialist capability")
    return entries[0]
  }
}
export const migration = {
  id: "20261014010000_watoom_specialist",
  up: (tx: Transaction) =>
    tx
      .run(
        sql`CREATE TABLE _watoom_specialist_job(id TEXT PRIMARY KEY,scope TEXT NOT NULL,job TEXT NOT NULL,specialist TEXT NOT NULL,capability TEXT NOT NULL,input_digest TEXT NOT NULL,phase TEXT NOT NULL,primary_body TEXT NOT NULL,specialist_body TEXT NOT NULL,generation INTEGER,body TEXT,outcome TEXT,error TEXT)`,
      )
      .pipe(Effect.asVoid),
}
type Row = {
  id: string
  scope: string
  job: string
  specialist: string
  capability: string
  input_digest: string
  phase: string
  primary_body: string
  specialist_body: string
  body: string
  generation: number | null
  outcome: string | null
}
function checkedOutcome(outcome: Outcome): Outcome {
  const encoded = checkpointJson(outcome)
  if (/(?:-----BEGIN .*PRIVATE KEY|Bearer\s+\S+|(?:password|api[_-]?key|secret)["\s]*[:=]["\s]*\S+)/i.test(encoded))
    throw Error("sensitive specialist outcome")
  if (
    Buffer.byteLength(encoded) > 8192 ||
    typeof outcome.summary !== "string" ||
    outcome.summary.length > 2048 ||
    !Array.isArray(outcome.artifacts) ||
    outcome.artifacts.length > 16 ||
    outcome.artifacts.some(
      (x) =>
        !/^artifact:[A-Za-z0-9_./:-]{1,500}$/.test(x.reference) ||
        x.reference.includes("..") ||
        !/^[a-f0-9]{64}$/.test(x.sha256) ||
        !Number.isSafeInteger(x.bytes) ||
        x.bytes < 0 ||
        x.bytes > 64 * 1024 * 1024,
    )
  )
    throw Error("invalid specialist artifacts")
  return JSON.parse(encoded)
}
async function deadline<T>(operation: (signal: AbortSignal) => Promise<T>, ms: number, parent?: AbortSignal) {
  const abort = new AbortController()
  const cancel = () => abort.abort()
  parent?.addEventListener("abort", cancel, { once: true })
  let timer: ReturnType<typeof setTimeout>
  try {
    return await Promise.race([
      operation(abort.signal),
      new Promise<T>((_, reject) => {
        timer = setTimeout(() => {
          abort.abort()
          reject(Error("specialist outcome uncertain timeout"))
        }, ms)
      }),
    ])
  } finally {
    clearTimeout(timer!)
    parent?.removeEventListener("abort", cancel)
  }
}
export function dispatch(
  db: DB,
  registry: Registry,
  input: {
    scope: Scope
    job: string
    capability: string
    specialistID?: string
    payload: unknown
    primary: ModelIdentity
  },
  authority?: GpuAuthority,
) {
  return Effect.gen(function* () {
    const chosen = registry.select(input.capability, input.specialistID)
    identity(input.primary)
    const scope = scopeKey(input.scope)
    const payload = checkpointJson(input.payload)
    if (
      !input.job ||
      input.job.length > 256 ||
      Buffer.byteLength(payload) > chosen.descriptor.maxInputBytes ||
      /(?:-----BEGIN .*PRIVATE KEY|Bearer\s+\S+|(?:password|api[_-]?key|secret)["\s]*[:=]["\s]*\S+)/i.test(payload)
    )
      return yield* Effect.die(Error("unsafe specialist input"))
    chosen.backend.validateInput(JSON.parse(payload), input.capability)
    if (chosen.descriptor.execution === "exclusive-gpu" && (!authority || !["simulation", "g3h-g3g"].includes(authority.kind)))
      return yield* Effect.die(Error("verified authoritative GPU adapter required; live transitions remain approval gated"))
    const digest = sha(payload)
    const id = sha(JSON.stringify([scope, input.job, input.capability, chosen.descriptor.id]))
    const checkpointJob = "specialist:" + id
    const prior = yield* db.get<Row>(sql`SELECT * FROM _watoom_specialist_job WHERE id=${id}`)
    if (prior) {
      if (
        prior.input_digest !== digest ||
        prior.primary_body !== JSON.stringify(input.primary) ||
        prior.specialist_body !== JSON.stringify(chosen.descriptor)
      )
        return yield* Effect.die(Error("operation identity reused with different input or primary"))
      if (prior.phase === "completed" && prior.outcome) return checkedOutcome(JSON.parse(prior.outcome))
      return yield* Effect.die(Error("existing specialist operation requires reconciliation; replay refused"))
    }
    yield* db.transaction(
      () =>
        Effect.gen(function* () {
          yield* checkpointOnCommit(
            db,
            {
              scope: input.scope,
              job: checkpointJob,
              seq: 1,
              kind: "checkpoint",
              content: "Specialist delegation intent " + chosen.descriptor.id + " capability " + input.capability,
            },
            { specialist: chosen.descriptor.id, inputDigest: digest, primary: input.primary },
          )(0)
          yield* db.run(
            sql`INSERT INTO _watoom_specialist_job(id,scope,job,specialist,capability,input_digest,phase,primary_body,specialist_body,body) VALUES(${id},${scope},${input.job},${chosen.descriptor.id},${input.capability},${digest},'checkpointed',${JSON.stringify(input.primary)},${JSON.stringify(chosen.descriptor)},${payload})`,
          )
        }),
      { behavior: "immediate" },
    )
    let lease: Lease | undefined
    const result = yield* Effect.uninterruptibleMask((restore) =>
      restore(
        Effect.gen(function* () {
          if (chosen.descriptor.execution === "exclusive-gpu") {
            yield* db.run(sql`UPDATE _watoom_specialist_job SET phase='acquiring' WHERE id=${id}`)
            lease = yield* Effect.tryPromise((signal) =>
              deadline(() => authority!.acquire(id, input.primary), chosen.descriptor.timeoutMs, signal),
            )
            if (lease.job !== id || !Number.isSafeInteger(lease.generation) || lease.generation < 1)
              return yield* Effect.die(Error("invalid GPU ownership generation"))
            yield* db.run(sql`UPDATE _watoom_specialist_job SET generation=${lease.generation} WHERE id=${id}`)
            yield* Effect.tryPromise((signal) =>
              deadline(() => authority!.activate(lease!, chosen.descriptor), chosen.descriptor.timeoutMs, signal),
            )
          }
          yield* db.run(sql`UPDATE _watoom_specialist_job SET phase='executing' WHERE id=${id}`)
          const outcome = checkedOutcome(
            yield* Effect.tryPromise((signal) =>
              deadline(
                (child) => chosen.backend.execute(id, JSON.parse(payload), child),
                chosen.descriptor.timeoutMs,
                signal,
              ),
            ),
          )
          if (
            !(yield* Effect.tryPromise((signal) =>
              deadline(() => chosen.backend.verifyArtifacts(outcome), chosen.descriptor.timeoutMs, signal),
            ))
          )
            return yield* Effect.die(Error("specialist artifact persistence unverified"))
          yield* db.run(
            sql`UPDATE _watoom_specialist_job SET outcome=${JSON.stringify(outcome)},phase=${lease ? "restoring" : "verified"} WHERE id=${id}`,
          )
          if (lease) {
            yield* Effect.tryPromise((signal) =>
              deadline(() => authority!.restore(lease!, input.primary), chosen.descriptor.timeoutMs, signal),
            )
            if (
              !(yield* Effect.tryPromise((signal) =>
                deadline(() => authority!.validatePrimary(lease!, input.primary), chosen.descriptor.timeoutMs, signal),
              ))
            )
              return yield* Effect.die(Error("primary functionality restoration unverified"))
          }
          return outcome
        }),
      ).pipe(
        Effect.exit,
        Effect.flatMap((result) =>
          Effect.gen(function* () {
            if (result._tag === "Failure") {
              const restoration = lease
                ? yield* Effect.tryPromise((signal) =>
                    deadline(() => authority!.restore(lease!, input.primary), chosen.descriptor.timeoutMs, signal),
                  ).pipe(Effect.exit)
                : undefined
              const phase = restoration?._tag === "Failure" ? "recovery_required" : "uncertain"
              yield* db.run(
                sql`UPDATE _watoom_specialist_job SET phase=${phase},error='ambiguous external operation; explicit reconciliation required' WHERE id=${id}`,
              )
            }
            return result
          }),
        ),
      ),
    )
    if (result._tag === "Failure") return yield* result
    yield* db.transaction(
      () =>
        Effect.gen(function* () {
          yield* checkpointOnCommit(
            db,
            {
              scope: input.scope,
              job: checkpointJob,
              seq: 2,
              kind: "completion",
              content: "Specialist operation verified; artifact references " + JSON.stringify(result.value.artifacts),
            },
            { outcome: result.value },
          )(1)
          yield* db.run(sql`UPDATE _watoom_specialist_job SET phase='completed' WHERE id=${id}`)
        }),
      { behavior: "immediate" },
    )
    return result.value
  })
}

export type ExecutionReceipt = { operationID: string; inputDigest: string; specialistSha256: string; outcome: Outcome }
/** Recovery accepts positive artifact-backed evidence only. Absence never retries an external action. */
export function recoverJob(
  db: DB,
  registry: Registry,
  input: {
    operationID: string
    scope: Scope
    previousProcessExited: boolean
    exclusiveDatabaseOwner: boolean
    receipt?: ExecutionReceipt
  },
  authority?: GpuAuthority,
) {
  return Effect.gen(function* () {
    if (!/^[a-f0-9]{64}$/.test(input.operationID) || !input.previousProcessExited || !input.exclusiveDatabaseOwner)
      return yield* Effect.die(Error("specialist recovery ownership proof required"))
    const row = yield* db.get<Row>(sql`SELECT * FROM _watoom_specialist_job WHERE id=${input.operationID}`)
    if (
      !row ||
      row.scope !== scopeKey(input.scope) ||
      sha(row.body) !== row.input_digest ||
      sha(JSON.stringify([row.scope, row.job, row.capability, row.specialist])) !== row.id
    )
      return yield* Effect.die(Error("specialist persisted identity/scope mismatch"))
    const chosen = registry.select(row.capability, row.specialist)
    if (row.specialist_body !== JSON.stringify(chosen.descriptor))
      return yield* Effect.die(Error("specialist revision changed; recovery blocked"))
    const primary = JSON.parse(row.primary_body) as ModelIdentity
    identity(primary)
    const receipt = input.receipt
    if (receipt) exactKeys(receipt, ["operationID", "inputDigest", "specialistSha256", "outcome"])
    if (
      receipt &&
      (receipt.operationID !== row.id ||
        receipt.inputDigest !== row.input_digest ||
        receipt.specialistSha256 !== chosen.descriptor.model.modelSha256)
    )
      return yield* Effect.die(Error("specialist receipt identity mismatch"))
    if (
      chosen.descriptor.execution === "exclusive-gpu" &&
      row.phase !== "completed" &&
      row.phase !== "primary_restored"
    ) {
      if (!authority || !["simulation", "g3h-g3g"].includes(authority.kind) )
        return yield* Effect.die(Error("authoritative GPU recovery unavailable"))
      const lease = row.generation ? { job: row.id, generation: row.generation } : yield* Effect.tryPromise(() => authority.reconcileLease?.(row.id) ?? Promise.resolve(undefined))
      if (!lease) return yield* Effect.die(Error("GPU ownership receipt unavailable; replay blocked"))
      if (!row.generation) yield* db.run(sql`UPDATE _watoom_specialist_job SET generation=${lease.generation} WHERE id=${row.id}`)
      yield* Effect.tryPromise((signal) =>
        deadline(() => authority.recover(lease, primary, true), chosen.descriptor.timeoutMs, signal),
      )
      if (
        !(yield* Effect.tryPromise((signal) =>
          deadline(() => authority.validatePrimary(lease, primary), chosen.descriptor.timeoutMs, signal),
        ))
      )
        return yield* Effect.die(Error("restored primary verification failed"))
      yield* db.run(sql`UPDATE _watoom_specialist_job SET phase='primary_restored' WHERE id=${row.id}`)
    }
    const outcome = receipt
      ? checkedOutcome(receipt.outcome)
      : row.outcome
        ? checkedOutcome(JSON.parse(row.outcome))
        : undefined
    if (!outcome) return { state: "OUTCOME_UNVERIFIED" as const }
    if (
      !(yield* Effect.tryPromise((signal) =>
        deadline(() => chosen.backend.verifyArtifacts(outcome), chosen.descriptor.timeoutMs, signal),
      ))
    )
      return yield* Effect.die(Error("recovered artifact verification failed"))
    if (row.phase !== "completed")
      yield* db.transaction(
        () =>
          Effect.gen(function* () {
            yield* checkpointOnCommit(
              db,
              {
                scope: input.scope,
                job: "specialist:" + row.id,
                seq: 2,
                kind: "completion",
                content: "Specialist operation verified; artifact references " + JSON.stringify(outcome.artifacts),
              },
              { outcome },
            )(1)
            yield* db.run(
              sql`UPDATE _watoom_specialist_job SET phase='completed',outcome=${JSON.stringify(outcome)},error=NULL WHERE id=${row.id}`,
            )
          }),
        { behavior: "immediate" },
      )
    return { state: "COMPLETED" as const, outcome }
  })
}
