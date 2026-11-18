import { AbsolutePath } from "@opencode/core/schema"
import { Location } from "@opencode/core/location"
import { expect } from "bun:test"
import { Agent } from "@opencode/core/agent"
import { AppNodeBuilder } from "@opencode/core/effect/app-node-builder"
import { PluginPromise } from "@opencode/core/plugin/promise"
import { Tool } from "@opencode/core/tool"
import { Session } from "@opencode/schema/session"
import { SessionMessage } from "@opencode/schema/session-message"
import { Effect, Result } from "effect"
import { testEffect } from "./lib/effect"
import { host } from "./plugin/host"
import plugin from "./fixture/toolkit-native"

const it = testEffect(AppNodeBuilder.build(Tool.node, [Location.node.replace(Location.boundNode({ directory: AbsolutePath.make("/project") }))]))
const runtime = process.env.WATOOM_OWNED_TOOLKIT_PROXY ? it.live : it.live.skip
runtime(
  "Toolkit promise plugin runs real disposable Godot through native Tool.Service and HTTP",
  () =>
    Effect.gen(function* () {
      if (
        !process.env.WATOOM_OWNED_TOOLKIT_PROXY ||
        process.env.HTTP_PROXY !== process.env.WATOOM_OWNED_TOOLKIT_PROXY ||
        new URL(process.env.WATOOM_OWNED_TOOLKIT_PROXY).hostname !== "127.0.0.1"
      )
        throw new Error("Start the isolated fixture harness; no production fallback")
      const tools = yield* Tool.Service
      const base = host()
      yield* PluginPromise.fromPromise(plugin).effect(host({ tool: { ...base.tool, transform: tools.transform } }))
      const snapshot = yield* tools.snapshot()
      const execute = (agent: string, path: string) =>
        snapshot.execute({
          sessionID: Session.ID.make("ses_owned_toolkit"),
          agent: Agent.ID.make(agent),
          messageID: SessionMessage.ID.make("msg_owned_toolkit"),
          call: {
            type: "tool-call" as const,
            id: "call_owned_toolkit",
            name: "watoom_toolkit_godotImport",
            input: { path },
          },
        })
      const denied = yield* execute("watoom-reviewer", "positive").pipe(Effect.result)
      expect(Result.isFailure(denied)).toBe(true)
      const result = yield* execute("watoom-builder", "positive")
      expect(result.output).toMatchObject({ status: "PASS", exit_code: 0, verification: { status: "PASS" } })
      const negative = yield* execute("watoom-builder", "negative").pipe(Effect.result)
      expect(Result.isFailure(negative)).toBe(true)
      const filtered = yield* tools.snapshot([{ action: "watoom_toolkit_*", resource: "*", effect: "deny" }])
      expect(filtered.definitions.some((item) => item.name.startsWith("watoom_toolkit_"))).toBe(false)
    }),
  { timeout: 40000 },
)
