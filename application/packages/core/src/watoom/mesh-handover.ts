export * as MeshHandover from "./mesh-handover.js"

import { createHash } from "node:crypto"
import { Effect } from "effect"
import { ToolFailure } from "@opencode/ai/effect"
import type { Tool } from "@opencode/schema/tool"
import type { Event, Scope } from "./contract.js"

type Memory = {
  enabled: boolean
  remember: (event: Event) => Effect.Effect<{ id: string; state: string }, Error>
}

/** The existing controller-owned Mesh pipeline owns GPU mutation and restoration. */
export function run<E, R>(
  input: {
    server: string
    tool: string
    args: Record<string, unknown>
    sessionID: string
    memory: Memory
    scope: Effect.Effect<Scope, Error, R>
  },
  execute: Effect.Effect<Tool.Result, E, R>,
) {
  if (input.server !== "watoom-llama-mesh" || !["generate", "submit"].includes(input.tool)) return execute
  return Effect.gen(function* () {
    if (input.tool === "submit")
      return yield* new ToolFailure({ message: "Use synchronous Mesh generate: the CPU tool must span GPU restoration before Qwen resumes." })
    if (!input.memory.enabled)
      return yield* new ToolFailure({ message: "GPU handover requires the native durable AgentMemory checkpoint/outbox." })
    const requestID = input.args.request_id
    if (typeof requestID !== "string" || !/^[A-Za-z0-9_-]{1,80}$/.test(requestID))
      return yield* new ToolFailure({ message: "Mesh generate requires a stable request_id; reuse it after an uncertain outcome." })
    const scope = yield* input.scope
    const digest = createHash("sha256").update(JSON.stringify(Object.fromEntries(Object.entries(input.args).sort(([a], [b]) => a.localeCompare(b))))).digest("hex")
    const checkpoint = (seq: number, phase: string, fields: Record<string, unknown> = {}) =>
      input.memory.remember({
        scope,
        job: (phase === "GPU_OUTCOME_UNCERTAIN" ? "gpu-uncertain:" : "gpu:") + input.sessionID + ":" + requestID,
        seq,
        kind: seq === 2 ? "completion" : "checkpoint",
        content: JSON.stringify({ phase, requestID, inputDigest: digest, ...fields }),
      }).pipe(Effect.flatMap((receipt) =>
        ["pending", "sending", "uncertain", "observed"].includes(receipt.state)
          ? Effect.succeed(receipt)
          : Effect.fail(Error("GPU checkpoint has no verified local durable state"))))
    // remember commits SQLite checkpoint/outbox before attempting remote delivery.
    yield* checkpoint(1, "GPU_HANDOVER_PENDING")
    return yield* Effect.gen(function* () {
      const result = yield* execute
      const receipt = yield* Effect.try({
        try: () => {
          const text = typeof result.content === "string" ? result.content :
            result.content?.flatMap((part) => part.type === "text" ? [part.text] : []).join("\n")
          if (result.output === undefined && !text) throw Error("Missing Mesh receipt")
          return (result.output ?? JSON.parse(text!)) as {
            job_id?: string
            manifest?: {
              result?: string
              PRIMARY_QWEN_RESTORED?: string
              primary_health?: { ready?: string; inference?: string; model?: string }
              glb_sha256?: string
            }
          }
        },
        catch: () => Error("Invalid Mesh restoration receipt"),
      })
      const manifest = receipt.manifest
      if (!receipt.job_id || !/^[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}$/.test(receipt.job_id) ||
          manifest?.result !== "PASS" || manifest.PRIMARY_QWEN_RESTORED !== "yes" ||
          manifest.primary_health?.ready !== "yes" || manifest.primary_health.inference !== "PASS" ||
          !manifest.primary_health.model || !/^[a-f0-9]{64}$/.test(manifest.glb_sha256 ?? ""))
        return yield* new ToolFailure({ message: "Mesh did not provide verified primary restoration and artifact evidence; reconcile the existing job." })
      yield* checkpoint(2, "PRIMARY_RESTORED", {
        controllerJob: receipt.job_id,
        primaryModel: manifest.primary_health.model,
        artifactSha256: manifest.glb_sha256,
      })
      return result
    }).pipe(Effect.onExit((exit) =>
      exit._tag === "Failure"
        ? checkpoint(1, "GPU_OUTCOME_UNCERTAIN").pipe(Effect.asVoid, Effect.catch(() => Effect.void))
        : Effect.void))
  })
}
