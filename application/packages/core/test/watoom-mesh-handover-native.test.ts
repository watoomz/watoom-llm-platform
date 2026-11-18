import { test, expect } from "bun:test"
import { Effect } from "effect"
import type { Context } from "@opencode/plugin/effect/plugin"
import { MeshHandoverPlugin } from "../src/plugin/watoom-mesh-handover"
import { NativeMemory } from "../src/watoom/native-memory"
import { Location } from "../src/location"
import { Session } from "../src/session"
import { Permission } from "../src/permission"
import type { ToolEditor } from "@opencode/plugin/effect/tool"
import type { Tool } from "@opencode/schema/tool"

async function fixture(denied = false, wrongProject = false) {
  let transform: ((editor: ToolEditor) => void) | undefined
  const writes: string[] = []
  let calls = 0
  const context = {
    tool: {
      transform: (callback: typeof transform) =>
        Effect.sync(() => {
          transform = callback
        }),
    },
  } as unknown as Context
  await Effect.runPromise(
    MeshHandoverPlugin.Plugin.effect(context).pipe(
      Effect.provideService(NativeMemory.Service, {
        enabled: true,
        required: false,
        status: Effect.die(Error("unused status fixture")),
        revise: () => Effect.fail(Error("unused revision fixture")),
        flush: Effect.void,
        learn: () => Effect.die(Error("unused learning fixture")),
        recall: () => Effect.die(Error("unused recall fixture")),
        search: () => Effect.succeed([]),
        remember: (event) =>
          Effect.sync(() => {
            writes.push(JSON.parse(event.content).phase)
            return { id: "fixture", state: "observed" }
          }),
      }),
      Effect.provideService(Location.Service, { project: { id: "p" }, directory: "/fixture" } as never),
      Effect.provideService(Session.Service, {
        get: () => Effect.succeed({ projectID: wrongProject ? "other" : "p", location: { directory: "/fixture" } }),
      } as never),
      Effect.provideService(Permission.Service, {
        assert: () => (denied ? Effect.fail(Error("denied")) : Effect.void),
      } as never),
      Effect.scoped,
    ),
  )
  const fresh = () => {
    const tool = {
      name: "generate",
      execute: () =>
        Effect.sync(() => {
          calls++
          return {
            output: {
              job_id: "20261017T000000Z-12345678",
              manifest: {
                result: "PASS",
                PRIMARY_QWEN_RESTORED: "yes",
                primary_health: { ready: "yes", inference: "PASS", model: "swift-qwen38-coder" },
                glb_sha256: "a".repeat(64),
              },
            },
            content: [{ type: "text", text: "Verified fixture" }],
          }
        }),
    } as unknown as Tool.Info
    transform!({
      update: (id, callback) => {
        if (id === "watoom-llama-mesh_generate") callback(tool)
      },
    } as ToolEditor)
    return tool
  }
  const run = (tool: Tool.Info) =>
    Effect.runPromise(
      tool.execute({ request_id: "fixture_request", prompt: "cube" }, {
        sessionID: "ses_fixture",
        agent: "fixture",
        messageID: "msg_fixture",
        id: "call_fixture",
      } as never),
    )
  return { fresh, run, writes, calls: () => calls }
}
test("native MCP override preserves checkpoints after a catalog refresh", async () => {
  const f = await fixture()
  await f.run(f.fresh())
  await f.run(f.fresh())
  expect(f.calls()).toBe(2)
  expect(f.writes).toEqual(["GPU_HANDOVER_PENDING", "PRIMARY_RESTORED", "GPU_HANDOVER_PENDING", "PRIMARY_RESTORED"])
})
test("native permission and scope rejection happen before checkpoints and GPU calls", async () => {
  for (const f of [await fixture(true), await fixture(false, true)]) {
    await expect(f.run(f.fresh())).rejects.toThrow()
    expect(f.calls()).toBe(0)
    expect(f.writes).toHaveLength(0)
  }
})
