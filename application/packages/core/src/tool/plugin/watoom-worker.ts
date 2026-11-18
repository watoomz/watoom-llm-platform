export * as WorkerTool from "./watoom-worker.js"
import { Effect, Schema } from "effect"
import type { Context } from "@opencode/plugin/effect/plugin"
import { ToolFailure } from "@opencode/ai/effect"
import { Config } from "../../config.js"
import { FileAccess } from "../../file-access.js"
import { Permission } from "../../permission.js"
import { IsolatedWorker } from "../../watoom/worker.js"
import { mkdir, chmod } from "node:fs/promises"
import path from "node:path"
import { randomUUID } from "node:crypto"

export const Input = Schema.Struct({
  workspace: Schema.String,
  command: Schema.Array(Schema.String.check(Schema.isMinLength(1), Schema.isMaxLength(8192))).check(Schema.isMinLength(1), Schema.isMaxLength(64)),
  artifacts: Schema.Array(Schema.String).check(Schema.isMaxLength(32)),
})
export const Output = Schema.Struct({
  status: Schema.Literals(["PASS", "FAIL", "TIMEOUT", "CANCELLED"]),
  exitCode: Schema.NullOr(Schema.Number), output: Schema.String, truncated: Schema.Boolean,
  artifacts: Schema.Array(Schema.Struct({ path: Schema.String, sha256: Schema.String, bytes: Schema.Number })),
  directory: Schema.String,
})
export const Plugin = {
  id: "watoom.tool.worker",
  effect: Effect.fn("WorkerTool.Plugin")(function* (ctx: Context) {
    const config = yield* Config.Service
    const permission = yield* Permission.Service
    const access = yield* FileAccess.Service
    const settings = Config.latest(yield* config.entries(), "watoom_worker")
    if (!settings) return
    yield* ctx.tool.transform((editor) => editor.add({
      name: "watoom_worker_run",
      options: { codemode: false, permission: "watoom_worker_run" },
      description: "Run an approved command in a disposable CPU container. Workspace is read-only; write new required outputs under /output. Success requires all requested output files. No network, credentials, GPU or host shell access.",
      input: Input, output: Output,
      execute: (input, context) => Effect.gen(function* () {
        const target = yield* access.resolve({ path: input.workspace, kind: "directory" })
        yield* access.authorizeExternal([target], context)
        yield* permission.assert({ action: "watoom_worker_run", resources: [input.command.join(" "), target.absolute],
          save: [], sessionID: context.sessionID, agent: context.agent,
          source: { type: "tool", messageID: context.messageID, id: context.id } })
        const directory = path.join(settings.output, "job-" + randomUUID())
        yield* Effect.tryPromise(async () => {
          await mkdir(directory, { recursive: false, mode: 0o777 })
          // mkdir mode is masked by the server umask; the distinct container UID needs output access.
          await chmod(directory, 0o777)
        })
        const output = yield* Effect.tryPromise((signal) => IsolatedWorker.execute({ ...settings, workspace: target.absolute, output: directory,
          command: input.command, artifacts: input.artifacts }, signal))
        return { output: { ...output, directory }, content: JSON.stringify({ ...output, directory }) }
      }).pipe(Effect.mapError((error) => new ToolFailure({ message: "Isolated worker failed", error }))),
    })).pipe(Effect.asVoid)
  }),
}
