import { SessionMessage } from "@opencode/schema/session-message"
import { Model } from "@opencode/schema/model"
import { Provider } from "@opencode/schema/provider"
import { Money } from "@opencode/schema/money"
import { RelativePath } from "@opencode/schema/schema"
import { LayerNode } from "@opencode/util/effect/layer-node"
import { Effect } from "effect"
import { sql } from "drizzle-orm"
import { AppNodeBuilder } from "@opencode/core/effect/app-node-builder"
import { Database } from "@opencode/core/database/database"
import { Bus } from "@opencode/core/bus"
import { NativeMemory } from "@opencode/core/watoom/native-memory"
import { Global } from "@opencode/util/global"
import { Session } from "@opencode/schema/session"
import { Project } from "@opencode/schema/project"
import { Agent } from "@opencode/schema/agent"
import { AbsolutePath } from "@opencode/schema/schema"
import { Event } from "@opencode/schema/event"
import { SessionEvent } from "@opencode/core/session/event"
const database = process.argv[2]!
const mode = process.argv[3]!
const directory = process.argv[4]!
const scope = {
  project: process.env.WATOOM_MEMORY_TEST_PROJECT ?? "memory-fixture",
  repository: directory,
  agent: "fixture",
}
await Effect.runPromise(
  Effect.gen(function* () {
    const memory = yield* NativeMemory.Service
    const db = (yield* Database.Service).db
    const bus = yield* Bus.Service
    if (mode !== "recover") {
      yield* db.run(
        sql`INSERT OR IGNORE INTO project(id,worktree,time_created,time_updated,time_active,sandboxes) VALUES(${scope.project},${directory},0,0,0,'[]')`,
      )
      const parentID = Session.ID.make("ses_native_memory_parent")
      if (mode === "lifecycle")
        yield* bus.publish(SessionEvent.Created, {
          sessionID: parentID,
          projectID: Project.ID.make(scope.project),
          location: { directory: AbsolutePath.make(directory) },
          slug: "parent-fixture",
          version: "fixture",
          agent: Agent.ID.make("fixture-parent"),
        })
      const sessionID = Session.ID.make("ses_native_memory_fixture")
      if (!(yield* db.get(sql`SELECT id FROM session_v2 WHERE id=${sessionID}`)))
        yield* bus.publish(SessionEvent.Created, {
          sessionID,
          projectID: Project.ID.make(scope.project),
          location: { directory: AbsolutePath.make(directory) },
          slug: "memory-fixture",
          version: "fixture",
          ...(mode === "lifecycle" ? { parentID } : {}),
          agent: Agent.ID.make(scope.agent),
        })
      if (mode === "knowledge" || mode === "knowledge-outage") {
        const a = yield* memory.remember({
          scope,
          job: "knowledge-source-a",
          seq: 1,
          kind: "checkpoint",
          content: "The port is 8000.",
        })
        const b = yield* memory.remember({
          scope,
          job: "knowledge-source-b",
          seq: 1,
          kind: "checkpoint",
          content: "The service is private.",
        })
        const input = {
          requestID: "fix-port",
          action: "correct" as const,
          targets: [a.id],
          summary: "The port is 9000.",
          reason: "Confirmed current configuration",
        }
        const corrected = yield* memory.revise(scope, input)
        if (mode === "knowledge-outage") {
          const found = yield* memory.search(scope, "8000")
          process.stdout.write(JSON.stringify({ corrected, found, status: yield* memory.status }) + "\n")
          return
        }
        const duplicate = yield* memory.revise(scope, input)
        const conflict = yield* memory.revise(scope, { ...input, summary: "conflicting content" }).pipe(Effect.exit)
        const isolated = yield* memory
          .revise({ ...scope, project: "other" }, { ...input, requestID: "cross-project" })
          .pipe(Effect.exit)
        const before = yield* memory.search(scope, "8000")
        const consolidated = yield* memory.revise(scope, {
          requestID: "merge",
          action: "consolidate",
          targets: [corrected.id, b.id],
          summary: "The private service uses port 9000.",
          reason: "Combine verified service facts",
        })
        const merged = yield* memory.search(scope, "service")
        const withdrawn = yield* memory.revise(scope, {
          requestID: "withdraw",
          action: "withdraw",
          targets: [consolidated.id],
          summary: "",
          reason: "User revoked the service note",
        })
        const after = yield* memory.search(scope, "service")
        const status = yield* memory.status
        process.stdout.write(
          JSON.stringify({
            a,
            b,
            corrected,
            duplicate,
            conflict: conflict._tag,
            isolated: isolated._tag,
            before,
            consolidated,
            merged,
            withdrawn,
            after,
            status,
          }) + "\n",
        )
        return
      }
      if (mode === "learning") {
        // Runtime tool records for this session: the only accepted evidence source.
        const tool = (id: string, command: string, status: "completed" | "error", exit: number, time: number) =>
          JSON.stringify({
            type: "assistant",
            content: [
              {
                type: "tool",
                id,
                name: "shell",
                time: { created: time - 1, completed: time },
                state: { status, input: { command }, content: [{ type: "text", text: "fixture" }], metadata: { exit } },
              },
            ],
          })
        const rows = [
          ["msg_learn_1", tool("call_deploy", "ansible-playbook -i inventories/homelab playbooks/llm-bge-embeddings.yml", "completed", 0, 1000)],
          ["msg_learn_2", tool("call_broken", "ansible-playbook playbooks/llm-bge-embeddings.yml --wait-all", "completed", 2, 2000)],
          ["msg_learn_3", tool("call_ls", "ls -la", "completed", 0, 3000)],
        ]
        for (const [index, [id, data]] of rows.entries())
          yield* db.run(
            sql`INSERT OR IGNORE INTO session_message(id,session_id,type,seq,time_created,time_updated,data) VALUES(${id},${sessionID},'assistant',${index + 1},${index},${index},${data})`,
          )
        const base = {
          kind: "procedure" as const,
          title: "Deploy BGE embeddings service",
          environment: "homelab k3s, llama-cpp namespace",
          problem: "AgentMemory needs a GPU embedding endpoint",
          solution: "Run the BGE playbook from the ansible directory; it waits only on the Deployment.",
          commands: ["ansible-playbook -i inventories/homelab playbooks/llm-bge-embeddings.yml"],
          prerequisites: ["Swift running"],
          expectedResults: ["384-dimension probe passes"],
          failureConditions: ["Service wait timeout"],
          rollback: "Delete the bge-embeddings Deployment, Service and NetworkPolicy",
          evidence: [{ tool: "shell", contains: "llm-bge-embeddings.yml" }],
        }
        const attempt = (input: typeof base | Record<string, unknown>, scopeOverride = scope) =>
          memory.learn(scopeOverride, sessionID, input as never).pipe(
            Effect.map((value) => ({ ok: true as const, value })),
            Effect.catch((error: Error) => Effect.succeed({ ok: false as const, error: error.message })),
          )
        const verified = yield* attempt({ ...base, evidence: [{ tool: "shell", contains: "-i inventories/homelab" }] })
        const duplicate = yield* attempt({ ...base, evidence: [{ tool: "shell", contains: "-i inventories/homelab" }] })
        const revised = yield* attempt({
          ...base,
          solution: "Run the BGE playbook; Service and NetworkPolicy apply first, then the Deployment wait.",
          evidence: [{ tool: "shell", contains: "-i inventories/homelab" }],
        })
        const failedOnly = yield* attempt({ ...base, title: "Deploy BGE with wait-all", commands: [], evidence: [{ tool: "shell", contains: "--wait-all" }] })
        const wrongCommand = yield* attempt({ ...base, title: "Deploy BGE proven by ls", evidence: [{ tool: "shell", contains: "ls -la" }] })
        const missing = yield* attempt({ ...base, title: "Deploy BGE without evidence", evidence: [{ tool: "shell", contains: "never-ran" }] })
        const knownFailure = yield* attempt({
          ...base,
          kind: "known-failure",
          title: "BGE playbook wait-all flag fails",
          commands: [],
          evidence: [{ tool: "shell", contains: "--wait-all" }],
        })
        const secret = yield* attempt({ ...base, title: "Deploy BGE with token", solution: "export api_key=abcdef123456 then run" })
        yield* memory.flush
        const recalled = yield* memory.recall(scope, "how do I deploy the BGE embeddings", 2000)
        const otherProject = yield* memory.recall({ ...scope, project: "other-project" }, "how do I deploy the BGE embeddings", 2000)
        const knowledgeRows = yield* db.all(
          sql`SELECT job,seq,state FROM _watoom_outbox WHERE job LIKE 'learn:%' ORDER BY job,seq`,
        )
        process.stdout.write(
          JSON.stringify({ verified, duplicate, revised, failedOnly, wrongCommand, missing, knownFailure, secret, recalled, otherProject, knowledgeRows }) + "\n",
        )
        return
      }
      if (mode === "learning-offline") {
        const recalled = yield* memory.recall(scope, "deploy the BGE embeddings", 2000)
        process.stdout.write(JSON.stringify({ recalled }) + "\n")
        return
      }
      if (mode === "commands" || mode === "commands-recover") {
        if (mode === "commands-recover") {
          const found = yield* memory.search(scope, "platypus-204420")
          process.stdout.write(JSON.stringify({ found }) + "\n")
          return
        }
        const saved = yield* memory.remember({
          scope,
          job: "explicit-fixture",
          seq: 1,
          kind: "checkpoint",
          content: "unique durable fact: platypus-204420",
        })
        const duplicate = yield* memory.remember({
          scope,
          job: "explicit-fixture",
          seq: 1,
          kind: "checkpoint",
          content: "unique durable fact: platypus-204420",
        })
        const found = yield* memory.search(scope, "platypus-204420")
        const isolated = yield* memory.search({ ...scope, project: "other-project" }, "platypus-204420")
        process.stdout.write(JSON.stringify({ saved, duplicate, found, isolated }) + "\n")
        return
      }
      if (mode === "lifecycle") {
        yield* bus.publish(SessionEvent.Execution.Started, { sessionID })
        const assistantMessageID = SessionMessage.ID.make("msg_milestone_fixture")
        yield* bus.publish(SessionEvent.Step.Started, {
          sessionID,
          assistantMessageID,
          agent: Agent.ID.make(scope.agent),
          model: { id: Model.ID.make("fixture"), providerID: Provider.ID.make("fixture") },
          started: 1,
        })
        const milestone = {
          sessionID,
          assistantMessageID,
          finish: "stop" as const,
          cost: Money.USD.zero,
          tokens: { input: 0, output: 0, reasoning: 0, cache: { read: 0, write: 0 } },
          files: [RelativePath.make("src/fixture.ts")],
        }
        yield* bus.publish(SessionEvent.Step.Ended, milestone, { id: Event.ID.make("evt_milestone_fixture") })
        yield* bus
          .publish(SessionEvent.Step.Ended, milestone, { id: Event.ID.make("evt_milestone_fixture") })
          .pipe(Effect.exit)
        yield* bus.publish(SessionEvent.Compaction.Started, { sessionID, reason: "manual" })
        yield* bus.publish(SessionEvent.Execution.Interrupted, { sessionID, reason: "shutdown" })
        yield* memory.flush
        const facts = yield* db.all(sql`SELECT body,checkpoint_body,state FROM _watoom_outbox`)
        process.stdout.write(JSON.stringify({ facts }) + "\n")
        return
      }
      const publication = bus.publish(
        SessionEvent.Execution.Succeeded,
        { sessionID },
        { id: Event.ID.make("evt_memory_fixture_completed") },
      )
      if (mode === "duplicate") yield* publication.pipe(Effect.exit)
      if (mode !== "duplicate") yield* publication
      process.stdout.write("NATIVE_EVENT_COMMITTED\n")
    }
    yield* memory.flush
    const rows = yield* db.all<{ state: string; attempts: number }>(
      sql`SELECT state,attempts FROM _watoom_outbox WHERE job LIKE '%evt_memory_fixture_completed'`,
    )
    const retrieved = yield* memory.search(scope, "native fixture")
    const isolated = yield* memory.search({ ...scope, project: "other-project" }, "native fixture")
    process.stdout.write(JSON.stringify({ rows, retrieved: retrieved.length, isolated: isolated.length }) + "\n")
  }).pipe(
    Effect.provide(
      AppNodeBuilder.build(LayerNode.group([NativeMemory.node, Database.node, Bus.node]), [
        Database.node.replace(Database.configured({ path: database })),
        Bus.node.replace(Bus.configured({ persist: true })),
        Global.node.replace(Global.layerWith({ data: directory + "/global" })),
      ]),
    ),
    Effect.scoped,
  ),
)
