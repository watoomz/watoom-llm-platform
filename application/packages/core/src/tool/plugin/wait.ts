export * as WaitTool from "./wait.js"

import type { Context } from "@opencode/plugin/effect/plugin"
import { Duration, Effect, Schema } from "effect"

export const names = ["wait", "sleep"] as const

export const MAX_SECONDS = 600

export const Input = Schema.Struct({
  seconds: Schema.Number.check(Schema.isBetween({ minimum: 1, maximum: MAX_SECONDS })).annotate({
    description: `Seconds to wait (1-${MAX_SECONDS}).`,
  }),
  reason: Schema.optional(Schema.String).annotate({
    description: "What you are waiting for, e.g. a job id or a build.",
  }),
})

export const Output = Schema.Struct({ waited: Schema.Number })

const DESCRIPTION =
  "Pause for a number of seconds while a job, build, deploy or another agent finishes. " +
  "Also callable as sleep. Calling it is not a repeated-tool-cycle attempt: it is ignored by the loop guard and never disables tools. " +
  "Check status again after waiting; if the status is unchanged, change approach rather than waiting indefinitely."

export const Plugin = {
  id: "watoom.tool.wait",
  effect: Effect.fn("WaitTool.Plugin")(function* (ctx: Context) {
    yield* ctx.tool
      .transform((editor) => {
        for (const name of names)
          editor.add({
            name,
            options: { codemode: false },
            description: DESCRIPTION,
            input: Input,
            output: Output,
            execute: (input) =>
              Effect.sleep(Duration.seconds(input.seconds)).pipe(
                Effect.as({
                  output: { waited: input.seconds },
                  content: `Waited ${input.seconds}s${input.reason ? ` for ${input.reason}` : ""}.`,
                }),
              ),
          })
      })
      .pipe(Effect.orDie)
  }),
}
