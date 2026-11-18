import { Agent } from "../agent.js"
import { SkillCatalog } from "../skill/catalog.js"
export * as SessionSkill from "./skill.js"

import type { Session } from "@opencode/schema/session"
import { Effect, Option } from "effect"
import { Instance } from "../instance/service.js"
import { Plugin } from "../plugin/service.js"
import { Skill } from "../skill.js"
import { SkillNotFoundError } from "./error.js"

export const get = Effect.fn("SessionSkill.get")(function* (input: { session: Session.Info; skill: Skill.ID }) {
  const instances = yield* Instance.Service
  const notFound = () => new SkillNotFoundError({ skill: input.skill })
  // One location scope for the native lookup and the WatooM catalogue fallback.
  const skill = yield* Effect.gen(function* () {
    const skills = yield* Plugin.awaitActivation.pipe(Effect.andThen(Skill.Service))
    const registered = yield* skills.get(input.skill)
    if (registered) return registered
    // Instances without Agent or catalogue services cannot hold catalogue selections.
    const agents = yield* Effect.serviceOption(Agent.Service)
    const catalog = yield* Effect.serviceOption(SkillCatalog.Service)
    if (Option.isNone(agents) || Option.isNone(catalog)) return undefined
    const selected = yield* agents.value.select(input.session.agent)
    if (!selected.info) return undefined
    return yield* catalog.value.resolve({ sessionID: input.session.id, agent: selected.id, skillID: input.skill }).pipe(
      Effect.catchTags({
        "SkillCatalog.Rejected": () => Effect.fail(notFound()),
        "SkillCatalog.Unavailable": () => Effect.fail(notFound()),
      }),
    )
  }).pipe(instances.provide(input.session))
  if (!skill) return yield* notFound()
  return skill
})
