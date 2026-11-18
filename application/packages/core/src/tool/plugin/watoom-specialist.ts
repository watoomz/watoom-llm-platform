export * as SpecialistTool from "./watoom-specialist.js"
import { Effect, Schema } from "effect"
import type { Context } from "@opencode/plugin/effect/plugin"
import { ToolFailure } from "@opencode/ai/effect"
import { Config } from "../../config.js"
import { Global } from "@opencode/util/global"
import { Location } from "../../location.js"
import { Permission } from "../../permission.js"
import { Database } from "../../database/database.js"
import { SpecialistBackends } from "../../watoom/specialist-backends.js"
import { Specialist } from "../../watoom/specialist.js"
import * as Creative from "../../watoom/creative-contract.js"
import path from "node:path"
export const Plugin = {
  id: "watoom.tool.specialist",
  effect: Effect.fn("SpecialistTool.Plugin")(function* (ctx: Context) {
    const config = yield* Config.Service
    const global = yield* Global.Service
    const location = yield* Location.Service
    const permission = yield* Permission.Service
    const database = yield* Database.Service
    const entries = yield* config.entries()
    const trusted = entries.filter((entry) => entry.type === "document" && entry.path !== undefined && path.dirname(entry.path) === global.config)
    const settings = Config.latest(trusted, "watoom_specialists")
    if (!settings?.entries.length) return
    const configured = SpecialistBackends.registry(settings.entries)
    yield* ctx.tool.transform((editor) => {
      editor.add({ name: "watoom_specialist_list", options: { codemode: false, permission: "watoom_specialist_list" }, description: "Discover operator-registered local specialist capabilities and actual backend availability. Unconfigured GPU backends remain inert.",
        input: Schema.Struct({}), output: Schema.Struct({ specialists: Schema.Array(Schema.Json) }),
        execute: (_input, context) => Effect.gen(function* () {
          yield* permission.assert({ action: "watoom_specialist_list", resources: [location.directory], save: [], sessionID: context.sessionID, agent: context.agent, source: { type: "tool", messageID: context.messageID, id: context.id } })
          const statuses = yield* Effect.promise(() => Promise.all(configured.discoveries.map(async (entry) => { try { await entry.discover(); const capabilities = [...configured.registry.list().find((descriptor) => descriptor.id === entry.id)!.capabilities]; return { id: entry.id, capabilities, contracts: Object.fromEntries(capabilities.filter((capability) => Creative.operations[capability]).map((capability) => [capability, { task: Creative.operations[capability].startsWith("asset-") ? Creative.operations[capability] : "3d-creative", operation: Creative.operations[capability].startsWith("asset-") ? null : Creative.operations[capability], asset_id: Creative.operations[capability].startsWith("asset-") ? null : "indexed ast_ reference required", optional: Creative.operations[capability].startsWith("asset-") ? ["limit","query","category","format"] : ["asset_ids","seed","parameters",...(capability==="world.compose"?["dungeon"]:[])] }])), status: "READY" } } catch { return { id: entry.id, capabilities: [] as string[], contracts: {}, status: "UNAVAILABLE" } } })))
          const output = { specialists: statuses }
          return { output, content: JSON.stringify(output) }
        }).pipe(Effect.mapError((error) => error instanceof ToolFailure ? error : new ToolFailure({ message: "Local specialist discovery failed", error }))),
      })
      editor.add({ name: "watoom_specialist_run", options: { codemode: false, permission: "watoom_specialist_run" }, description: "Delegate a typed capability to an operator-registered local backend. Durable job identity prevents uncertain replay. GPU transitions require a separate approved controller-owned host worker.",
        input: Schema.Struct({ capability: Schema.String, specialistID: Schema.optionalKey(Schema.String), job: Schema.String, payload: Schema.Json }),
        output: Schema.Struct({ summary: Schema.String, artifacts: Schema.Array(Schema.Struct({ reference: Schema.String, sha256: Schema.String, bytes: Schema.Number })) }),
        execute: (input, context) => Effect.gen(function* () {
          const chosen = configured.registry.select(input.capability, input.specialistID)
          yield* permission.assert({ action: "watoom_specialist_run", resources: [chosen.descriptor.id, input.capability], save: [], sessionID: context.sessionID, agent: context.agent, source: { type: "tool", messageID: context.messageID, id: context.id } })
          if (chosen.descriptor.execution === "exclusive-gpu") return yield* Effect.fail(new ToolFailure({ message: "GPU delegation requires an approved G3H/G3G systemd worker; model tools cannot grant --i-approve" }))
          const output = yield* Specialist.dispatch(database.db, configured.registry, { ...input, scope: { project: location.project.id, repository: location.directory, agent: context.agent }, primary: chosen.descriptor.model })
          return { output, content: JSON.stringify(output) }
        }).pipe(Effect.mapError((error) => error instanceof ToolFailure ? error : new ToolFailure({ message: "Local specialist delegation failed", error }))),
      })
    }).pipe(Effect.asVoid)
  }),
}
