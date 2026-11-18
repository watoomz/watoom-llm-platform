import { expect } from "bun:test"
import { Agent } from "@opencode/core/agent"
import { AppNodeBuilder } from "@opencode/core/effect/app-node-builder"
import { PluginPromise } from "@opencode/core/plugin/promise"
import { Tool } from "@opencode/core/tool"
import { Location } from "@opencode/core/location"
import { AbsolutePath } from "@opencode/core/schema"
import { Session } from "@opencode/schema/session"
import { SessionMessage } from "@opencode/schema/session-message"
import { Cause, Deferred, Effect, Exit, Fiber, Result } from "effect"
import { testEffect } from "../lib/effect"
import { host } from "./host"
// v2.2.5 tools are location-scoped; bind a fixed location like watoom-toolkit-runtime.test.ts.
const it = testEffect(
  AppNodeBuilder.build(Tool.node, [Location.node.replace(Location.boundNode({ directory: AbsolutePath.make("/project") }))]),
)
const input = {
  sessionID: Session.ID.make("ses_owned_boundary"),
  agent: Agent.ID.make("build"),
  messageID: SessionMessage.ID.make("msg_owned_boundary"),
  call: { type: "tool-call" as const, id: "call_boundary", name: "owned", input: {} },
}
it.live("Promise tool rejection is a typed Tool.Error", () =>
  Effect.gen(function* () {
    const tools = yield* Tool.Service
    yield* PluginPromise.fromPromise({
      id: "owned",
      async setup(ctx) {
        await ctx.tool.transform((editor) =>
          editor.add({
            name: "owned",
            description: "Owned failure",
            input: {},
            output: {},
            options: { codemode: false },
            async execute() {
              throw new Error("OWNED_FAILURE")
            },
          }),
        )
      },
    }).effect(host({ tool: { ...host().tool, transform: tools.transform } }))
    const snapshot = yield* tools.snapshot()
    const result = yield* snapshot.execute(input).pipe(Effect.result)
    expect(Result.isFailure(result)).toBe(true)
    if (Result.isFailure(result)) {
      expect(result.failure).toBeInstanceOf(Tool.Error)
      expect(result.failure.message).toBe("OWNED_FAILURE")
    }
  }),
)
it.live("Promise tool cancellation remains interruption with an aborted signal", () =>
  Effect.gen(function* () {
    const tools = yield* Tool.Service
    const started = yield* Deferred.make<AbortSignal>()
    yield* PluginPromise.fromPromise({
      id: "owned",
      async setup(ctx) {
        await ctx.tool.transform((editor) =>
          editor.add({
            name: "owned",
            description: "Owned cancellation",
            input: {},
            output: {},
            options: { codemode: false },
            execute: (_input, context) =>
              new Promise<never>((_resolve, reject) => {
                context.signal.addEventListener("abort", () => reject(new Error("owned abort")), { once: true })
                Effect.runSync(Deferred.succeed(started, context.signal))
              }),
          }),
        )
      },
    }).effect(host({ tool: { ...host().tool, transform: tools.transform } }))
    const snapshot = yield* tools.snapshot()
    const fiber = yield* snapshot.execute(input).pipe(Effect.forkScoped)
    const signal = yield* Deferred.await(started)
    yield* Fiber.interrupt(fiber)
    const exit = yield* Fiber.await(fiber)
    expect(signal.aborted).toBe(true)
    expect(Exit.isFailure(exit) && Cause.hasInterruptsOnly(exit.cause)).toBe(true)
  }),
)
