import { Permission } from "@opencode/core/permission"
import { AbsolutePath } from "@opencode/schema/schema"
import { location } from "./fixture/location"
import { expect } from "bun:test"
import { Effect, Layer } from "effect"
import { sql } from "drizzle-orm"
import fs from "node:fs/promises"
import path from "node:path"
import { createHash } from "node:crypto"
import { AppNodeBuilder } from "@opencode/core/effect/app-node-builder"
import { LayerNode } from "@opencode/util/effect/layer-node"
import { Global } from "@opencode/util/global"
import { Config } from "@opencode/core/config"
import { Tool } from "@opencode/core/tool"
import { Bus } from "@opencode/core/bus"
import { Database } from "@opencode/core/database/database"
import { Location } from "@opencode/core/location"
import { SessionProjector } from "@opencode/core/session/projector"
import { SpecialistTool } from "@opencode/core/tool/plugin/watoom-specialist"
import { SessionEvent } from "@opencode/core/session/event"
import { Session } from "@opencode/schema/session"
import { Agent } from "@opencode/schema/agent"
import { Agent as AgentRuntime } from "@opencode/core/agent"
import { SessionMessage } from "@opencode/schema/session-message"
import { host } from "./plugin/host"
import { testEffect } from "./lib/effect"
const root = await fs.mkdtemp(path.join(process.env.TMPDIR!, "watoom-native-specialist-"))
await fs.mkdir(path.join(root, "artifacts"))
const artifact = Buffer.from("Owned local fixture artifact")
await fs.writeFile(path.join(root, "artifacts", "result.txt"), artifact)
let calls = 0
const server = Bun.serve({ hostname: "127.0.0.1", port: 0, async fetch(request) {
  if (request.method === "GET") return Response.json({ contract: "watoom-specialist/v1", capabilities: ["document.inspect"] })
  calls++
  const body = await request.json() as { operationID: string; input: { corrupt?: boolean } }
  return Response.json({ contract: "watoom-specialist/v1", operationID: body.operationID, outcome: { summary: "Owned local service inspected document", artifacts: [{ reference: "artifact:result.txt", sha256: body.input.corrupt ? "f".repeat(64) : createHash("sha256").update(artifact).digest("hex"), bytes: artifact.length }] } })
} })
const descriptor = { id: "local-document", capabilities: ["document.inspect"], backend: "owned-local-fixture", model: { model: "fixture", modelSha256: "a".repeat(64), configurationSha256: "b".repeat(64), deploymentUID: "fixture-service", router: "none:cpu" }, execution: "independent", inputSchema: "fixture-document/v1", outputSchema: "watoom-specialist/v1", timeoutMs: 5000, maxInputBytes: 1024, resources: { cpuCores: 1, ramMiB: 128, gpuMiB: 0, diskMiB: 64 }, requiredSkills: [], requiredTools: [], cancellation: "cooperative-abort", recovery: "positive-receipt-only", restoration: "exact-primary-identity", sourceCommit: "a".repeat(40), evidence: "fixture" }
await fs.writeFile(path.join(root, "opencode.jsonc"), JSON.stringify({ watoom_specialists: { entries: [{ descriptor, backend: "local-http", url: server.url.origin, artifactRoot: path.join(root, "artifacts") }] }, agents: {
  "watoom-fixture": { description: "Owned local fixture", mode: "primary", permissions: [{ action: "*", resource: "*", effect: "deny" }, { action: "watoom_specialist_*", resource: "*", effect: "allow" }] },
  "watoom-denied": { description: "Denied fixture", mode: "primary", permissions: [{ action: "*", resource: "*", effect: "deny" }] },
} }))
const it = testEffect(AppNodeBuilder.build(LayerNode.group([Tool.node, AgentRuntime.node, Config.node, Global.node, Location.node, Database.node, Bus.node, SessionProjector.node, Permission.node]), [
  Config.node.replace(Config.configured({ file: path.join(root, "opencode.jsonc"), project: false })),
  Location.node.replace(Layer.succeed(Location.Service, Location.Service.of(location({ directory: AbsolutePath.make(root) })))),
  Global.node.replace(Global.layerWith({ config: root, data: path.join(root, "data"), cache: path.join(root, "cache") })),
  Database.node.replace(Database.configured({ path: path.join(root, "native.sqlite") })),
  Bus.node.replace(Bus.configured({ persist: true })),
]))
it.effect("native permission admission, generic local HTTP delegation, hashes and idempotency", () => Effect.gen(function* () {
  yield* Effect.addFinalizer(() => Effect.promise(() => server.stop(true)))
  const tools = yield* Tool.Service
  const base = host()
  yield* SpecialistTool.Plugin.effect(host({ tool: { ...base.tool, transform: tools.transform } }))
  const bus = yield* Bus.Service
  const location = yield* Location.Service
  const database = yield* Database.Service
  yield* database.db.run(sql`INSERT OR IGNORE INTO project(id,worktree,time_created,time_updated,time_active,sandboxes) VALUES(${location.project.id},${root},0,0,0,'[]')`)
  const sessionID = Session.ID.make("ses_owned_specialist")
  yield* bus.publish(SessionEvent.Created, { sessionID, projectID: location.project.id, location: { directory: location.directory }, slug: "native-specialist", version: "fixture", agent: Agent.ID.make("watoom-fixture") })
  const agents = yield* AgentRuntime.Service
  yield* agents.transform((editor) => {
    editor.update(Agent.ID.make("watoom-fixture"), (info) => {
      info.permissions = [
        { action: "*", resource: "*", effect: "deny" },
        { action: "watoom_specialist_run", resource: "*", effect: "allow" },
      ]
    })
    editor.update(Agent.ID.make("watoom-denied"), (info) => {
      info.permissions = [{ action: "*", resource: "*", effect: "deny" }]
    })
  })
  const snapshot = yield* tools.snapshot()
  const execute = (agent: string, job: string, corrupt = false) => snapshot.execute({ sessionID, agent: Agent.ID.make(agent), messageID: SessionMessage.ID.make("msg_owned_specialist"), call: { type: "tool-call", id: "owned-call", name: "watoom_specialist_run", input: { capability: "document.inspect", job, payload: { corrupt } } } })
  expect((yield* execute("watoom-denied", "denied").pipe(Effect.exit))._tag).toBe("Failure")
  expect(calls).toBe(0)
  const result = yield* execute("watoom-fixture", "owned-job")
  expect(result.output).toMatchObject({ summary: "Owned local service inspected document" })
  yield* execute("watoom-fixture", "owned-job")
  expect(calls).toBe(1)
  expect((yield* execute("watoom-fixture", "corrupt-job", true).pipe(Effect.exit))._tag).toBe("Failure")
  expect((yield* database.db.get<{ phase: string }>(sql`SELECT phase FROM _watoom_specialist_job WHERE job='corrupt-job'`))?.phase).toBe("uncertain")
}), { timeout: 30000 })
