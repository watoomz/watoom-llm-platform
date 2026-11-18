export * as MeshHandoverPlugin from "./watoom-mesh-handover.js"

import { Effect } from "effect"
import { ToolFailure } from "@opencode/ai/effect"
import type { Context } from "@opencode/plugin/effect/plugin"
import { NativeMemory } from "../watoom/native-memory.js"
import { MeshHandover } from "../watoom/mesh-handover.js"
import { Location } from "../location.js"
import { Session } from "../session.js"
import { Permission } from "../permission.js"

export const Plugin = {
  id: "watoom.mesh.handover",
  effect: Effect.fn("MeshHandoverPlugin")(function* (ctx: Context) {
    const memory = yield* NativeMemory.Service
    const location = yield* Location.Service
    const sessions = yield* Session.Service
    const permission = yield* Permission.Service
    // Standard transforms replay after MCP refresh; no separate executable registry.
    yield* ctx.tool.transform((editor) => {
      for (const name of ["generate", "submit"]) editor.update("watoom-llama-mesh_" + name, (tool) => {
        const execute = tool.execute
        tool.execute = (args, context) => Effect.gen(function* () {
          yield* permission.assert({
            action: "watoom-llama-mesh_" + name, resources: ["*"], save: ["*"],
            sessionID: context.sessionID, agent: context.agent,
            source: { type: "tool", messageID: context.messageID, id: context.id },
          })
          return yield* MeshHandover.run({
            server: "watoom-llama-mesh", tool: name, args, sessionID: context.sessionID, memory,
            scope: Effect.gen(function* () {
              const session = yield* sessions.get(context.sessionID)
              if (session.projectID !== location.project.id || session.location.directory !== location.directory)
                return yield* Effect.fail(Error("GPU checkpoint scope mismatch"))
              return { project: location.project.id, repository: location.directory, agent: context.agent }
            }),
          }, execute(args, context))
        }).pipe(Effect.mapError((error) =>
          error instanceof ToolFailure ? error : new ToolFailure({ message: "Mesh checkpoint or restoration validation failed", error })))
      })
    })
  }),
}
