import { Skill } from "../skill.js"
import { Tool } from "../tool.js"
import { SkillArtifact } from "../watoom/skill-artifact.js"
import { Session } from "@opencode/schema/session"
export * as SkillCatalog from "./catalog.js"

import { Cause, Context, Effect, Exit, Layer, Schema } from "effect"
import path from "node:path"
import { makeLocationNode } from "@opencode/util/effect/app-node"
import { Database } from "../database/database.js"
import { Agent } from "../agent.js"
import { SessionStore } from "../session/store.js"
import { Location } from "../location.js"
import { Permission } from "../permission.js"
import type { Scope } from "../watoom/contract.js"
import { Config } from "../config.js"
import { EffectDrizzleSqlite } from "../database/drizzle.js"
import { sqliteLayer } from "#sqlite"
import { Catalog } from "../watoom/catalog.js"
import { SkillCatalog } from "@opencode/schema/skill-catalog"

export type SelectionInput = { agent: Agent.ID; target: "agent" | "session"; sessionID?: string }
export class Unavailable extends Schema.TaggedError<Unavailable>()("SkillCatalog.Unavailable", {
  message: Schema.String,
}) {}
type DB = Effect.Success<ReturnType<typeof EffectDrizzleSqlite.makeWithDefaults>>
export interface Interface {
  readonly browse: (input: Catalog.Browse) => Effect.Effect<SkillCatalog.Page, Unavailable>
  readonly selections: (
    input: SelectionInput,
  ) => Effect.Effect<SkillCatalog.Selection[], Catalog.Rejected | Unavailable>
  readonly select: (
    input: SelectionInput & { skillID: string },
  ) => Effect.Effect<SkillCatalog.Selection, Catalog.Rejected | Unavailable>
  readonly remove: (input: SelectionInput & { skillID: string }) => Effect.Effect<void, Catalog.Rejected | Unavailable>
  readonly resolve: (input: {
    sessionID: Session.ID
    agent: Agent.ID
    skillID: string
  }) => Effect.Effect<Skill.VerifiedInfo | undefined, Catalog.Rejected | Unavailable>
}
export class Service extends Context.Service<Service, Interface>()("@opencode/SkillCatalog") {}
const layer = Layer.effect(
  Service,
  Effect.gen(function* () {
    const config = yield* Config.Service
    const { db: selections } = yield* Database.Service
    const agents = yield* Agent.Service
    const sessions = yield* SessionStore.Service
    const location = yield* Location.Service
    const tools = yield* Tool.Service
    const owner = Effect.fn("SkillCatalog.owner")(function* (input: SelectionInput) {
      const agent = yield* agents.resolve(input.agent)
      if (!agent) return yield* new Catalog.Rejected({ message: "Unknown skill selection agent" })
      if (input.target === "session") {
        if (!input.sessionID) return yield* new Catalog.Rejected({ message: "Session identity required" })
        const session = yield* sessions.get(input.sessionID as Parameters<typeof sessions.get>[0])
        const selected = session ? yield* agents.select(session.agent) : undefined
        if (
          !session ||
          selected?.id !== input.agent ||
          !selected.info ||
          session.location.directory !== location.directory
        )
          return yield* new Catalog.Rejected({ message: "Skill selection session owner or location mismatch" })
        return {
          scope: {
            project: location.project.id,
            repository: location.project.canonical,
            agent: input.agent,
          } satisfies Scope,
          permissions: Permission.merge(agent.permissions, session.permissions ?? []),
        }
      }
      if (input.sessionID)
        return yield* new Catalog.Rejected({ message: "Agent preference must not contain a session identity" })
      return {
        scope: {
          project: location.project.id,
          repository: location.project.canonical,
          agent: input.agent,
        } satisfies Scope,
        permissions: agent.permissions,
      }
    })
    const withCatalog = <A, E>(body: (db: DB) => Effect.Effect<A, E>) =>
      Effect.gen(function* () {
        const settings = Config.latest(yield* config.entries(), "skill_catalog")
        if (!settings || !path.isAbsolute(settings.database))
          return yield* new Unavailable({ message: "Skill catalog is disabled or invalid" })
        return yield* Effect.gen(function* () {
          return yield* body(yield* EffectDrizzleSqlite.makeWithDefaults())
        }).pipe(
          Effect.provide(
            sqliteLayer({
              filename: settings.database,
              readonly: true,
              readwrite: false,
              create: false,
              disableWAL: true,
            }),
          ),
          Effect.scoped,
          Effect.mapError((error) =>
            error instanceof Catalog.Rejected
              ? error
              : new Unavailable({ message: "Skill catalog operation unavailable" }),
          ),
          Effect.catchDefect(() => Effect.fail(new Unavailable({ message: "Skill catalog operation unavailable" }))),
        )
      })
    return Service.of({
      resolve: Effect.fn("SkillCatalog.resolve")(function* (input) {
        const settings = Config.latest(yield* config.entries(), "skill_catalog")
        if (!settings) return undefined
        const owned = yield* owner({ ...input, target: "session" })
        const sessionTable = yield* selections
          .get<{ name: string }>("SELECT name FROM sqlite_master WHERE name='_watoom_skill_selection'")
          .pipe(Effect.orDie)
        const agentTable = yield* selections
          .get<{ name: string }>("SELECT name FROM sqlite_master WHERE name='_watoom_agent_skill_selection'")
          .pipe(Effect.orDie)
        const sessionRefs = sessionTable
          ? yield* Catalog.selectionReferences(selections, owned.scope, input.sessionID).pipe(Effect.orDie)
          : []
        const agentRefs = agentTable
          ? yield* Catalog.selectionReferences(selections, owned.scope).pipe(Effect.orDie)
          : []
        const target = sessionRefs.some((ref) => ref.skill_id === input.skillID)
          ? "session"
          : agentRefs.some((ref) => ref.skill_id === input.skillID)
            ? "agent"
            : undefined
        if (!target) return undefined
        if (!settings.artifacts || !path.isAbsolute(settings.artifacts))
          return yield* new Unavailable({ message: "Reviewed skill artifact root unavailable" })
        return yield* withCatalog((catalog) =>
          Effect.gen(function* () {
            const reference = () =>
              target === "session"
                ? Catalog.selected(selections, catalog, {
                    sessionID: input.sessionID,
                    scope: owned.scope,
                    skillID: input.skillID,
                  })
                : Catalog.selectedForAgent(selections, catalog, { scope: owned.scope, skillID: input.skillID })
            const before = yield* reference()
            const capabilities = new Set(
              (yield* tools.list())
                .filter(
                  (tool) =>
                    Permission.evaluate(tool.options?.permission ?? tool.id, "*", owned.permissions).effect === "allow",
                )
                .map((tool) => tool.id),
            )
            const skill = yield* SkillArtifact.resolve(
              settings.artifacts!,
              before,
              owned.permissions,
              capabilities,
            ).pipe(
              Effect.mapError(
                () => new Catalog.Rejected({ message: "Selected skill artifact or dependencies failed verification" }),
              ),
            )
            const after = yield* reference()
            if (
              before.sha256 !== after.sha256 ||
              before.commit !== after.commit ||
              before.bundleSha256 !== after.bundleSha256
            )
              return yield* new Catalog.Rejected({ message: "Skill approval changed while verifying artifact" })
            return skill
          }),
        )
      }),
      select: Effect.fn("SkillCatalog.select")(function* (input) {
        const owned = yield* owner(input)
        if (Permission.evaluate("skill", input.skillID, owned.permissions).effect !== "allow")
          return yield* new Catalog.Rejected({ message: "Skill permission denied or approval required" })
        return yield* withCatalog((catalog) =>
          Effect.gen(function* () {
            yield* Catalog.approvedReference(catalog, input.skillID)
            const references = yield* Catalog.selectionReferences(
              selections,
              owned.scope,
              input.target === "session" ? input.sessionID : undefined,
            ).pipe(Effect.orDie)
            if (references.length >= 32 && !references.some((reference) => reference.skill_id === input.skillID))
              return yield* new Catalog.Rejected({ message: "Skill selection limit reached" })
            return yield* input.target === "agent"
              ? Catalog.selectForAgent(selections, catalog, { scope: owned.scope, skillID: input.skillID })
              : Catalog.select(selections, catalog, {
                  scope: owned.scope,
                  skillID: input.skillID,
                  sessionID: input.sessionID!,
                })
          }),
        )
      }),
      remove: Effect.fn("SkillCatalog.remove")(function* (input) {
        const owned = yield* owner(input)
        const settings = Config.latest(yield* config.entries(), "skill_catalog")
        if (!settings) return yield* new Unavailable({ message: "Skill catalog is disabled" })
        return yield* (
          input.target === "agent"
            ? Catalog.removeForAgent(selections, owned.scope, input.skillID)
            : Catalog.remove(selections, input.sessionID!, owned.scope, input.skillID)
        ).pipe(Effect.orDie)
      }),
      selections: Effect.fn("SkillCatalog.selections")(function* (input) {
        const owned = yield* owner(input)
        const settings = Config.latest(yield* config.entries(), "skill_catalog")
        if (!settings) return yield* new Unavailable({ message: "Skill catalog is disabled" })
        const references = yield* Catalog.selectionReferences(
          selections,
          owned.scope,
          input.target === "session" ? input.sessionID : undefined,
        ).pipe(Effect.orDie)
        return yield* withCatalog((catalog) =>
          Effect.forEach(references, (reference) =>
            Effect.gen(function* () {
              const current = yield* (
                input.target === "agent"
                  ? Catalog.selectedForAgent(selections, catalog, { scope: owned.scope, skillID: reference.skill_id })
                  : Catalog.selected(selections, catalog, {
                      scope: owned.scope,
                      skillID: reference.skill_id,
                      sessionID: input.sessionID!,
                    })
              ).pipe(Effect.exit)
              if (Exit.isFailure(current)) {
                if (Cause.hasInterrupts(current.cause)) return yield* Effect.failCause(current.cause)
                const error = Cause.findErrorOption(current.cause)
                if (error._tag !== "Some" || !(error.value instanceof Catalog.Rejected))
                  return yield* new Unavailable({ message: "Skill selection validation unavailable" })
              }
              const status = Exit.isFailure(current)
                ? ("REVOKED" as const)
                : Permission.evaluate("skill", reference.skill_id, owned.permissions).effect === "allow"
                  ? ("SELECTED_NOT_EXECUTED" as const)
                  : ("BLOCKED" as const)
              return {
                id: reference.skill_id,
                sha256: reference.content_sha,
                commit: reference.commit_sha,
                bundleSha256: reference.bundle_sha,
                status,
                ...(Exit.isSuccess(current)
                  ? { name: current.value.name, description: current.value.description }
                  : {}),
              }
            }),
          ),
        )
      }),
      browse: Effect.fn("SkillCatalog.browse")(function* (input) {
        const settings = Config.latest(yield* config.entries(), "skill_catalog")
        if (!settings)
          return { enabled: false, discovered: 0, validated: 0, approved: 0, matched: 0, offset: 0, rows: [] }
        if (!path.isAbsolute(settings.database))
          return yield* new Unavailable({ message: "Skill catalog path must be absolute" })
        return yield* Effect.gen(function* () {
          const db = yield* EffectDrizzleSqlite.makeWithDefaults()
          return yield* Catalog.browse(db, input)
        }).pipe(
          Effect.provide(
            sqliteLayer({
              filename: settings.database,
              readonly: true,
              readwrite: false,
              create: false,
              disableWAL: true,
            }),
          ),
          Effect.scoped,
          Effect.mapError(() => new Unavailable({ message: "Skill catalog is inaccessible or invalid" })),
          Effect.catchDefect(() =>
            Effect.fail(new Unavailable({ message: "Skill catalog is inaccessible or invalid" })),
          ),
        )
      }),
    })
  }),
)
export const node = makeLocationNode({
  service: Service,
  layer,
  deps: [Config.node, Database.node, Agent.node, SessionStore.node, Location.node, Tool.node],
})
