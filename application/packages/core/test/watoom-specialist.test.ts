import { test, expect } from "bun:test"
import { Effect } from "effect"
import type { SqlClient } from "effect/sql/SqlClient"
import { SqliteClient } from "@effect/sql-sqlite-bun"
import { sql } from "drizzle-orm"
import { EffectDrizzleSqlite } from "@opencode/core/database/drizzle"
import { Workflow } from "@opencode/core/watoom/workflow"
import {
  Registry,
  migration,
  dispatch,
  recoverJob,
  type Descriptor,
  type GpuAuthority,
  type Lease,
  type ModelIdentity,
  type Outcome,
} from "@opencode/core/watoom/specialist"
const primary: ModelIdentity = {
  model: "fixture-primary",
  modelSha256: "a".repeat(64),
  configurationSha256: "b".repeat(64),
  projectorSha256: "c".repeat(64),
  deploymentUID: "fixture-uid",
  router: "fixture-router",
}
const outcome: Outcome = {
  summary: "fixture verified",
  artifacts: [{ reference: "artifact:fixture/result", sha256: "d".repeat(64), bytes: 10 }],
}
const descriptor = (id = "cpu", execution: Descriptor["execution"] = "cpu"): Descriptor => ({
  id,
  capabilities: ["vision.inspect"],
  backend: "fixture-backend",
  model: { ...primary, model: id },
  execution,
  inputSchema: "fixture.input.v1",
  outputSchema: "fixture.output.v1",
  timeoutMs: 100,
  maxInputBytes: 4096,
  resources: { cpuCores: 1, ramMiB: 128, gpuMiB: execution === "exclusive-gpu" ? 1024 : 0, diskMiB: 64 },
  requiredSkills: [],
  requiredTools: [],
  cancellation: "cooperative-abort",
  recovery: "positive-receipt-only",
  restoration: "exact-primary-identity",
  sourceCommit: "a".repeat(40),
  evidence: "fixture",
})
const request = {
  scope: { project: "fixture", repository: "fixture-repo", agent: "fixture-agent" },
  job: "job1",
  capability: "vision.inspect",
  payload: { asset: "fixture" },
  primary,
}
class GPU implements GpuAuthority {
  kind = "simulation" as const
  generation = 0
  owner?: string
  calls: string[] = []
  restored?: ModelIdentity
  failAcquire = false
  failActivate = false
  failRestore = false
  stale = false
  async acquire(job: string, snapshot: ModelIdentity) {
    this.calls.push("acquire")
    if (this.failAcquire) throw Error("acquisition failed")
    if (this.owner) throw Error("concurrent ownership")
    expect(snapshot).toEqual(primary)
    this.owner = job
    return { job, generation: ++this.generation }
  }
  check(lease: Lease) {
    if (lease.job !== this.owner || lease.generation !== this.generation) throw Error("stale generation")
  }
  async activate(lease: Lease) {
    this.calls.push("activate")
    if (this.stale) this.generation++
    this.check(lease)
    if (this.failActivate) throw Error("startup failed")
  }
  async restore(lease: Lease, snapshot: ModelIdentity) {
    this.calls.push("restore")
    this.check(lease)
    if (this.failRestore) throw Error("restoration interrupted")
    this.restored = { ...snapshot }
    this.owner = undefined
  }
  async validatePrimary(_lease: Lease, snapshot: ModelIdentity) {
    this.calls.push("validate")
    return JSON.stringify(this.restored) === JSON.stringify(snapshot)
  }
  async recover(lease: Lease, snapshot: ModelIdentity, ownerExited: boolean) {
    if (!ownerExited) throw Error("lease expiration does not establish death")
    this.check(lease)
    await this.restore(lease, snapshot)
  }
}
const run = <A>(
  body: (
    db: Effect.Success<ReturnType<typeof EffectDrizzleSqlite.makeWithDefaults>>,
  ) => Effect.Effect<A, unknown, SqlClient>,
) =>
  Effect.runPromise(
    Effect.gen(function* () {
      const db = yield* EffectDrizzleSqlite.makeWithDefaults()
      yield* db.transaction((tx) => Workflow.migration.up(tx))
      yield* db.transaction((tx) => migration.up(tx))
      return yield* body(db)
    }).pipe(Effect.provide(SqliteClient.layer({ filename: ":memory:", disableWAL: true })), Effect.scoped),
  )
function registered(mode: Descriptor["execution"] = "cpu", execute = async () => outcome, verify = async () => true) {
  const registry = new Registry()
  registry.register(descriptor("specialist", mode), { validateInput: () => {}, execute, verifyArtifacts: verify })
  return registry
}
test("registry selects multiple specialist capabilities and rejects unknown", () => {
  const r = new Registry()
  r.register(descriptor("vision"), {
    validateInput: () => {},
    execute: async () => outcome,
    verifyArtifacts: async () => true,
  })
  r.register(
    { ...descriptor("audio"), capabilities: ["audio.transcribe"] },
    { validateInput: () => {}, execute: async () => outcome, verifyArtifacts: async () => true },
  )
  expect(r.select("audio.transcribe").descriptor.id).toBe("audio")
  expect(() => r.select("unknown")).toThrow()
})
test("registry accepts native Toolkit 3D capabilities and rejects malformed capability names", () => {
  const backend = { validateInput: () => {}, execute: async () => outcome, verifyArtifacts: async () => true }
  const registry = new Registry()
  registry.register({ ...descriptor("toolkit"), capabilities: ["3d.generate", "3d.inspect", "3d.repair"] }, backend)
  expect(registry.select("3d.generate").descriptor.id).toBe("toolkit")
  for (const capability of [".3d", "-3d", "3d generate", "3d/generate"])
    expect(() => new Registry().register({ ...descriptor("invalid"), capabilities: [capability] }, backend)).toThrow()
})
test("registry rejects duplicate invalid and ambiguous identities", () => {
  const r = registered()
  expect(() =>
    r.register(descriptor("specialist"), {
      validateInput: () => {},
      execute: async () => outcome,
      verifyArtifacts: async () => true,
    }),
  ).toThrow()
  expect(() =>
    r.register(
      { ...descriptor("bad"), sourceCommit: "bad" },
      { validateInput: () => {}, execute: async () => outcome, verifyArtifacts: async () => true },
    ),
  ).toThrow()
  r.register(descriptor("another"), {
    validateInput: () => {},
    execute: async () => outcome,
    verifyArtifacts: async () => true,
  })
  expect(() => r.select("vision.inspect")).toThrow()
})
test("CPU dispatch leaves GPU untouched and commits outbox lifecycle", () =>
  run((db) =>
    Effect.gen(function* () {
      const gpu = new GPU()
      expect(yield* dispatch(db, registered(), request, gpu)).toEqual(outcome)
      expect(gpu.calls).toEqual([])
      expect((yield* db.get<{ n: number }>(sql`SELECT count(*) n FROM _watoom_outbox`))?.n).toBe(2)
    }),
  ))
test("exclusive GPU simulation restores exact primary identity", () =>
  run((db) =>
    Effect.gen(function* () {
      const gpu = new GPU()
      yield* dispatch(db, registered("exclusive-gpu"), request, gpu)
      expect(gpu.restored).toEqual(primary)
      expect(gpu.calls).toEqual(["acquire", "activate", "restore", "validate"])
    }),
  ))
test("exclusive delegation without simulation authority is closed", () =>
  run((db) =>
    Effect.gen(function* () {
      expect((yield* dispatch(db, registered("exclusive-gpu"), request).pipe(Effect.exit))._tag).toBe("Failure")
      expect((yield* db.get<{ n: number }>(sql`SELECT count(*) n FROM _watoom_outbox`))?.n).toBe(0)
    }),
  ))
test("completed duplicate operation returns stored outcome without side effect replay", () =>
  run((db) =>
    Effect.gen(function* () {
      let calls = 0
      const r = registered("cpu", async () => {
        calls++
        return outcome
      })
      yield* dispatch(db, r, request)
      yield* dispatch(db, r, request)
      expect(calls).toBe(1)
    }),
  ))
test("changed input cannot reuse stable operation identity", () =>
  run((db) =>
    Effect.gen(function* () {
      const r = registered()
      yield* dispatch(db, r, request)
      expect((yield* dispatch(db, r, { ...request, payload: { asset: "different" } }).pipe(Effect.exit))._tag).toBe(
        "Failure",
      )
    }),
  ))
test("timeout marks uncertain and refuses duplicate replay", () =>
  run((db) =>
    Effect.gen(function* () {
      let calls = 0
      const r = registered("cpu", async () => {
        calls++
        return new Promise<Outcome>(() => {})
      })
      expect((yield* dispatch(db, r, request).pipe(Effect.exit))._tag).toBe("Failure")
      expect((yield* dispatch(db, r, request).pipe(Effect.exit))._tag).toBe("Failure")
      expect(calls).toBe(1)
      expect((yield* db.get<{ phase: string }>(sql`SELECT phase FROM _watoom_specialist_job`))?.phase).toBe("uncertain")
    }),
  ))
test("failed specialist startup restores primary without executing", () =>
  run((db) =>
    Effect.gen(function* () {
      let calls = 0
      const gpu = new GPU()
      gpu.failActivate = true
      expect(
        (yield* dispatch(
          db,
          registered("exclusive-gpu", async () => {
            calls++
            return outcome
          }),
          request,
          gpu,
        ).pipe(Effect.exit))._tag,
      ).toBe("Failure")
      expect(calls).toBe(0)
      expect(gpu.restored).toEqual(primary)
    }),
  ))
test("stale generation forbids restoration and requires recovery", () =>
  run((db) =>
    Effect.gen(function* () {
      const gpu = new GPU()
      gpu.stale = true
      expect((yield* dispatch(db, registered("exclusive-gpu"), request, gpu).pipe(Effect.exit))._tag).toBe("Failure")
      expect(gpu.restored).toBeUndefined()
      expect((yield* db.get<{ phase: string }>(sql`SELECT phase FROM _watoom_specialist_job`))?.phase).toBe(
        "recovery_required",
      )
    }),
  ))
test("failed artifact persistence conservatively blocks replay", () =>
  run((db) =>
    Effect.gen(function* () {
      expect(
        (yield* dispatch(
          db,
          registered(
            "cpu",
            async () => outcome,
            async () => false,
          ),
          request,
        ).pipe(Effect.exit))._tag,
      ).toBe("Failure")
      expect((yield* db.get<{ phase: string }>(sql`SELECT phase FROM _watoom_specialist_job`))?.phase).toBe("uncertain")
    }),
  ))
test("checkpoint failure precedes acquisition", () =>
  run((db) =>
    Effect.gen(function* () {
      yield* db.run(
        sql.raw(
          "CREATE TRIGGER fixture_fail BEFORE INSERT ON _watoom_outbox BEGIN SELECT RAISE(ABORT,'fixture checkpoint failure'); END",
        ),
      )
      const gpu = new GPU()
      expect((yield* dispatch(db, registered("exclusive-gpu"), request, gpu).pipe(Effect.exit))._tag).toBe("Failure")
      expect(gpu.calls).toEqual([])
    }),
  ))
test("concurrent controller acquisition rejects a second owner", async () => {
  const gpu = new GPU()
  await gpu.acquire("first", primary)
  await expect(gpu.acquire("second", primary)).rejects.toThrow()
})
test("lease expiration never authorizes reclamation", async () => {
  const gpu = new GPU()
  const lease = await gpu.acquire("first", primary)
  await expect(gpu.recover(lease, primary, false)).rejects.toThrow()
  expect(gpu.owner).toBe("first")
})
test("AgentMemory outage leaves native semantic intent pending", () =>
  run((db) =>
    Effect.gen(function* () {
      yield* dispatch(db, registered(), request)
      expect((yield* db.get<{ n: number }>(sql`SELECT count(*) n FROM _watoom_outbox WHERE state='pending'`))?.n).toBe(
        2,
      )
    }),
  ))

test("restart recovery requires positive receipt and never reexecutes unknown action", () =>
  run((db) =>
    Effect.gen(function* () {
      let calls = 0
      const r = registered("cpu", async () => {
        calls++
        throw Error("lost acknowledgment")
      })
      yield* dispatch(db, r, request).pipe(Effect.exit)
      const row = yield* db.get<{ id: string; input_digest: string }>(
        sql`SELECT id,input_digest FROM _watoom_specialist_job`,
      )
      if (!row) throw Error("missing job")
      const proof = {
        operationID: row.id,
        scope: request.scope,
        previousProcessExited: true,
        exclusiveDatabaseOwner: true,
      }
      expect((yield* recoverJob(db, r, proof)).state).toBe("OUTCOME_UNVERIFIED")
      expect(calls).toBe(1)
      const receipt = {
        operationID: row.id,
        inputDigest: row.input_digest,
        specialistSha256: primary.modelSha256,
        outcome,
      }
      expect((yield* recoverJob(db, r, { ...proof, receipt })).state).toBe("COMPLETED")
      expect((yield* recoverJob(db, r, { ...proof, receipt })).state).toBe("COMPLETED")
      expect(calls).toBe(1)
    }),
  ))
test("recovery rejects wrong scope live owner and forged receipt", () =>
  run((db) =>
    Effect.gen(function* () {
      const r = registered("cpu", async () => {
        throw Error("lost")
      })
      yield* dispatch(db, r, request).pipe(Effect.exit)
      const row = yield* db.get<{ id: string; input_digest: string }>(
        sql`SELECT id,input_digest FROM _watoom_specialist_job`,
      )
      if (!row) throw Error("missing job")
      const proof = {
        operationID: row.id,
        scope: request.scope,
        previousProcessExited: true,
        exclusiveDatabaseOwner: true,
      }
      expect((yield* recoverJob(db, r, { ...proof, previousProcessExited: false }).pipe(Effect.exit))._tag).toBe(
        "Failure",
      )
      expect(
        (yield* recoverJob(db, r, { ...proof, scope: { ...request.scope, project: "other" } }).pipe(Effect.exit))._tag,
      ).toBe("Failure")
      expect(
        (yield* recoverJob(db, r, {
          ...proof,
          receipt: { operationID: row.id, inputDigest: "e".repeat(64), specialistSha256: primary.modelSha256, outcome },
        }).pipe(Effect.exit))._tag,
      ).toBe("Failure")
    }),
  ))
test("interrupted primary restoration remains recoverable with exact saved identity", () =>
  run((db) =>
    Effect.gen(function* () {
      const gpu = new GPU()
      gpu.failRestore = true
      const r = registered("exclusive-gpu")
      yield* dispatch(db, r, request, gpu).pipe(Effect.exit)
      const row = yield* db.get<{ id: string }>(sql`SELECT id FROM _watoom_specialist_job`)
      if (!row) throw Error("missing job")
      gpu.failRestore = false
      expect(
        (yield* recoverJob(
          db,
          r,
          { operationID: row.id, scope: request.scope, previousProcessExited: true, exclusiveDatabaseOwner: true },
          gpu,
        )).state,
      ).toBe("COMPLETED")
      expect(gpu.restored).toEqual(primary)
    }),
  ))
