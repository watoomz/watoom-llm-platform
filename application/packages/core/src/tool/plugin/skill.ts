import { SkillCatalog } from "../../skill/catalog.js"
export * as SkillTool from "./skill.js"

import type { Context } from "@opencode/plugin/effect/plugin"
import { ToolFailure } from "@opencode/ai/effect"
import { Effect, Schema } from "effect"
import { FSUtil } from "@opencode/util/fs-util"
import { Skill } from "../../skill.js"
import { Permission } from "../../permission.js"

export const name = "skill"

export const Input = Schema.Struct({
  id: Skill.ID.annotate({ description: "The ID of an available skill or a skill explicitly referenced by the user" }),
})

export const Output = Schema.Struct({
  name: Skill.Name,
  directory: Schema.String,
  output: Schema.String,
})
export const description = [
  "Load a specialized skill's instructions and resources into the current conversation when the task at hand matches its description.",
  "",
  "The skill ID must match an available skill or a skill explicitly referenced by the user. Search watoom_skill_search first. Explicit loading of an enabled, owner-approved imported package pins it to this session through native selection; unapproved packages remain blocked. This does not enable packages or grant tool permissions.",
].join("\n")

export const toModelOutput = Skill.toModelOutput

const unableToLoad = (name: string, error?: unknown) =>
  new ToolFailure({ message: `Unable to load skill ${name}`, error })

export const Plugin = {
  id: "opencode.tool.skill",
  effect: Effect.fn("SkillTool.Plugin")(function* (ctx: Context) {
    const fs = yield* FSUtil.Service
    const skills = yield* Skill.Service
    const permission = yield* Permission.Service
    const catalog = yield* SkillCatalog.Service
    yield* ctx.tool
      .transform((editor) =>
        editor.add({
          name,
          options: { codemode: false },
          description,
          input: Input,
          output: Output,
          execute: (input, context) =>
            Effect.gen(function* () {
              const native = yield* skills.get(input.id)
              const skill =
                native ??
                (yield* Effect.gen(function* () {
                  const selected = yield* catalog.resolve({
                    sessionID: context.sessionID,
                    agent: context.agent,
                    skillID: input.id,
                  })
                  if (selected) return selected
                  // Explicit invocation can select only an enabled, owner-approved pin.
                  // This reuses native ownership, permission, dependency and hash checks.
                  yield* catalog.select({
                    sessionID: context.sessionID,
                    agent: context.agent,
                    target: "session",
                    skillID: input.id,
                  })
                  return yield* catalog.resolve({
                    sessionID: context.sessionID,
                    agent: context.agent,
                    skillID: input.id,
                  })
                }).pipe(Effect.mapError(() => unableToLoad(input.id))))
              if (!skill) return yield* unableToLoad(input.id)
              yield* permission
                .assert({
                  action: name,
                  resources: [input.id],
                  save: [input.id],
                  sessionID: context.sessionID,
                  agent: context.agent,
                  source: { type: "tool", messageID: context.messageID, id: context.id },
                })
                .pipe(Effect.mapError((error) => unableToLoad(input.id, error)))
              return {
                name: skill.name,
                ...(yield* Skill.prepare(fs, skill).pipe(Effect.mapError((error) => unableToLoad(input.id, error)))),
              }
            }).pipe(
              Effect.map((output) => ({
                output,
                content: output.output,
                metadata: { name: output.name, directory: output.directory },
              })),
            ),
        }),
      )
      .pipe(Effect.orDie)
  }),
}
