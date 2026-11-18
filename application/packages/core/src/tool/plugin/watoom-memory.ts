export * as MemoryTool from "./watoom-memory.js"
import { Effect, Schema } from "effect"
import type { Context } from "@opencode/plugin/effect/plugin"
import { NativeMemory } from "../../watoom/native-memory.js"
import { Location } from "../../location.js"
import { Permission } from "../../permission.js"
import { ToolFailure } from "@opencode/ai/effect"
import { Learning } from "../../watoom/learning.js"
import { AutoRecall } from "../../watoom/auto-recall.js"
export const Plugin = {
  id: "watoom.tool.memory",
  effect: Effect.fn("MemoryTool.Plugin")(function* (ctx: Context) {
    const memory = yield* NativeMemory.Service
    const location = yield* Location.Service
    const permission = yield* Permission.Service
    if (!memory.enabled) return
    yield* ctx.tool
      .transform((editor) =>
        editor.add({
          name: "watoom_memory_recall",
          options: { codemode: false, permission: "watoom_memory_recall" },
          description:
            "Retrieve learned knowledge (verified procedures, known failures, decisions) for this project directory as short summaries with references, plus this agent's own lifecycle memories. Use a specific technical query.",
          input: Schema.Struct({ query: Schema.String.check(Schema.isMinLength(1), Schema.isMaxLength(1024)) }),
          output: Schema.Struct({ knowledge: Schema.Array(Schema.String), memories: Schema.Array(Schema.String) }),
          execute: (input, context) =>
            Effect.gen(function* () {
              yield* permission.assert({
                action: "watoom_memory_recall",
                resources: [location.directory],
                save: [],
                sessionID: context.sessionID,
                agent: context.agent,
                source: { type: "tool", messageID: context.messageID, id: context.id },
              })
              const scope = { project: location.project.id, repository: location.directory, agent: context.agent }
              const knowledge = yield* memory.recall(scope, input.query, 4000)
              const memories = yield* memory.search(scope, input.query)
              const output = { knowledge, memories: memories.slice(0, 8).map((memory) => JSON.stringify(memory)) }
              return { output, content: JSON.stringify(output) }
            }).pipe(
              Effect.mapError((error) => new ToolFailure({ message: "AgentMemory retrieval unavailable", error })),
            ),
        }),
      )
      .pipe(Effect.asVoid)
    yield* ctx.tool
      .transform((editor) =>
        editor.add({
          name: "watoom_memory_record",
          options: { codemode: false, permission: "watoom_memory_remember" },
          description:
            "Persist a significant goal, verified milestone, decision or safe-stop handoff to AgentMemory. Use stable requestID, concise summary, exact evidence references and nextAction; never include credentials. Native operational checkpoints are recorded separately even when inference is offline.",
          input: Schema.Struct({
            requestID: Schema.String,
            kind: Schema.Literals(["goal", "milestone", "decision", "safe-stop"]),
            summary: Schema.String,
            sourceRefs: Schema.Array(Schema.String),
            nextAction: Schema.String,
            confidence: Schema.Literals(["VERIFIED", "UNVERIFIED", "ASSUMPTION"]),
          }),
          output: Schema.Struct({ id: Schema.String, state: Schema.String }),
          execute: (input, context) =>
            Effect.gen(function* () {
              if (
                !/^[A-Za-z0-9_-]{1,80}$/.test(input.requestID) ||
                input.sourceRefs.length > 16 ||
                input.sourceRefs.some((value) => value.length > 512) ||
                !input.summary.trim()
              )
                return yield* Effect.fail(new ToolFailure({ message: "Invalid memory milestone bounds" }))
              yield* permission.assert({
                action: "watoom_memory_remember",
                resources: [location.directory],
                save: [],
                sessionID: context.sessionID,
                agent: context.agent,
                source: { type: "tool", messageID: context.messageID, id: context.id },
              })
              const output = yield* memory.remember({
                scope: { project: location.project.id, repository: location.directory, agent: context.agent },
                job: "milestone:" + input.requestID,
                seq: 1,
                kind: "checkpoint",
                content: JSON.stringify({ schema: "watoom.milestone.v1", ...input }),
              })
              return { output, content: JSON.stringify(output) }
            }).pipe(
              Effect.mapError(
                (error) =>
                  new ToolFailure({
                    message: "Memory milestone was not acknowledged; check the existing checkpoint before retry",
                    error,
                  }),
              ),
            ),
        }),
      )
      .pipe(Effect.asVoid)
    yield* ctx.tool
      .transform((editor) =>
        editor.add({
          name: "watoom_memory_learn",
          options: { codemode: false, permission: "watoom_memory_remember" },
          description:
            "Record reusable knowledge after real work: a procedure that worked, a known failure, a decision, a compatibility note or a project convention. Cite evidence as {tool, contains} references to tool calls made in this session (or its direct children): the runtime checks those calls actually succeeded (or, for known-failure, actually failed) and attaches the evidence itself; your own success claim is not evidence. Same kind+title revises the record. Never include credentials.",
          input: Schema.Struct({
            kind: Schema.Literals(Learning.KINDS),
            title: Schema.String,
            environment: Schema.String,
            problem: Schema.String,
            solution: Schema.String,
            commands: Schema.Array(Schema.String),
            prerequisites: Schema.Array(Schema.String),
            expectedResults: Schema.Array(Schema.String),
            failureConditions: Schema.Array(Schema.String),
            rollback: Schema.String,
            evidence: Schema.Array(Schema.Struct({ tool: Schema.String, contains: Schema.String })),
            sourceCommit: Schema.optional(Schema.String),
          }),
          output: Schema.Struct({ id: Schema.String, state: Schema.String, status: Schema.String, duplicate: Schema.Boolean }),
          execute: (input, context) =>
            Effect.gen(function* () {
              yield* permission.assert({
                action: "watoom_memory_remember",
                resources: [location.directory],
                save: [],
                sessionID: context.sessionID,
                agent: context.agent,
                source: { type: "tool", messageID: context.messageID, id: context.id },
              })
              const output = yield* memory.learn(
                { project: location.project.id, repository: location.directory, agent: context.agent },
                context.sessionID,
                input,
              )
              return { output, content: JSON.stringify(output) }
            }).pipe(
              Effect.mapError(
                (error) =>
                  new ToolFailure({
                    message: error instanceof ToolFailure ? error.message : error instanceof Error ? error.message : "LEARN_FAILED",
                    error,
                  }),
              ),
            ),
        }),
      )
      .pipe(Effect.asVoid)
    // Targeted automatic recall: one search per new user turn, risky command or failed tool,
    // injected as a short system note with references. Failures add nothing and never block.
    const recalled = AutoRecall.cache()
    yield* ctx.session.hook("context", (event) =>
      Effect.gen(function* () {
        const trigger = AutoRecall.trigger(event.messages)
        const prior = recalled.get(event.sessionID)
        if (trigger && trigger.key !== prior?.key) {
          const lines = yield* memory.recall(
            { project: location.project.id, repository: location.directory, agent: event.agent },
            trigger.query,
            AutoRecall.BUDGET,
          )
          recalled.set(event.sessionID, { key: trigger.key, note: AutoRecall.note(trigger.reason, lines) })
        }
        const note = recalled.get(event.sessionID)?.note
        if (note) event.system.push({ type: "text", text: note })
      }),
    )
    yield* ctx.tool
      .transform((editor) =>
        editor.add({
          name: "watoom_memory_revise",
          options: { codemode: false, permission: "watoom_memory_revise" },
          description:
            "Correct, supersede, consolidate or withdraw identified native memories in the current scope. Retain source provenance; use a stable requestID for retry reconciliation.",
          input: Schema.Struct({
            requestID: Schema.String,
            action: Schema.Literals(["correct", "supersede", "consolidate", "withdraw"]),
            targets: Schema.Array(Schema.String),
            summary: Schema.String,
            reason: Schema.String,
          }),
          output: Schema.Struct({ id: Schema.String, state: Schema.String }),
          execute: (input, context) =>
            Effect.gen(function* () {
              yield* permission.assert({
                action: "watoom_memory_revise",
                resources: [location.directory],
                save: [],
                sessionID: context.sessionID,
                agent: context.agent,
                source: { type: "tool", messageID: context.messageID, id: context.id },
              })
              const output = yield* memory.revise(
                { project: location.project.id, repository: location.directory, agent: context.agent },
                input,
              )
              return { output, content: JSON.stringify(output) }
            }).pipe(
              Effect.mapError(
                (error) =>
                  new ToolFailure({
                    message: "Scoped memory revision was not accepted; reconcile the same requestID",
                    error,
                  }),
              ),
            ),
        }),
      )
      .pipe(Effect.asVoid)
  }),
}
