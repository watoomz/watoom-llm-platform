import { SkillRouting } from "@opencode/schema/skill-routing"
import { SkillDetail } from "@opencode/core/watoom/skill-detail"
import { Tool } from "@opencode/core/tool"
import { SkillAdministration } from "@opencode/core/watoom/administration"
import { Config } from "@opencode/core/config"
import { Global } from "@opencode/util/global"
import { ServerAuth } from "../auth"
import { authorizedRequest } from "../middleware/authorization"
import { UnauthorizedError } from "@opencode/protocol/errors"
import path from "node:path"
import { Catalog } from "@opencode/core/watoom/catalog"
import { SkillCatalog } from "@opencode/core/skill/catalog"
import { Skill } from "@opencode/core/skill"
import { Effect } from "effect"
import { HttpApiBuilder } from "effect/http-api"
import { InvalidRequestError, ServiceUnavailableError } from "@opencode/protocol/errors"
import { Api } from "../api"
import { response } from "../location"

const apiError = (error: Catalog.Rejected | SkillCatalog.Unavailable) =>
  error instanceof Catalog.Rejected
    ? new InvalidRequestError({ message: error.message })
    : new ServiceUnavailableError({ message: error.message, service: "skill-catalog" })
export const SkillHandler = HttpApiBuilder.group(Api, "server.skill", (handlers) =>
  Effect.gen(function* () {
    const auth = yield* ServerAuth.Config
    const global = yield* Global.Service
    return handlers
      .handle("skill.index", (ctx) =>
        response(
          Effect.gen(function* () {
            const skills = yield* Skill.Service
            const sources = yield* skills.list()
            const entries = SkillRouting.catalogue(sources)
            const matches = ctx.query.query
              ? SkillRouting.rank(ctx.query.query, entries, 32, sources)
              : entries.toSorted((a, b) => a.id.localeCompare(b.id))
            return { catalogueSize: entries.length, entries: matches, ranked: Boolean(ctx.query.query) }
          }),
        ),
      )
      .handle(
        "skill.catalog.admin",
        Effect.fn(function* (ctx) {
          const request = ctx.request
          if (!ServerAuth.required(auth) || !(yield* authorizedRequest(request, auth)))
            return yield* new UnauthorizedError({ message: "Authenticated reviewer required" })
          return yield* response(
            Effect.gen(function* () {
              const config = yield* Config.Service
              const entries = yield* config.entries()
              const trusted = entries.filter(
                (entry) =>
                  entry.type === "document" && entry.path !== undefined && path.dirname(entry.path) === global.config,
              )
              const settings = Config.latest(trusted, "skill_catalog")
              if (
                !settings?.administration ||
                !settings.artifacts ||
                !path.isAbsolute(settings.database) ||
                !path.isAbsolute(settings.artifacts)
              )
                return yield* new Catalog.Rejected({
                  message: "Reviewer administration is disabled in user configuration",
                })
              const tools = yield* Tool.Service
              const installed = new Set((yield* tools.list()).map((tool) => tool.id))
              if (
                !["reject", "disable", "revoke"].includes(ctx.payload.action) &&
                ctx.payload.tools.some((tool) => !installed.has(tool))
              )
                return yield* new Catalog.Rejected({ message: "Reviewed native dependency unavailable or denied" })
              return yield* SkillAdministration.execute(
                { database: settings.database, artifacts: settings.artifacts, collection: settings.collection },
                "server-owner:" + auth.username,
                ctx.payload,
              )
            }),
          ).pipe(Effect.mapError(apiError))
        }),
      )
      .handle("skill.catalog.detail", (ctx) =>
        response(
          Effect.gen(function* () {
            const config = yield* Config.Service
            const settings = Config.latest(yield* config.entries(), "skill_catalog")
            if (!settings) return yield* new Catalog.Rejected({ message: "Skill catalog disabled" })
            return yield* SkillDetail.inspect(settings, ctx.query.skillID)
          }),
        ).pipe(Effect.mapError(apiError)),
      )
      .handle("skill.list", () => response(Skill.Service.use((skill) => skill.list())))
      .handle("skill.catalog.list", (ctx) =>
        response(SkillCatalog.Service.use((catalog) => catalog.browse(ctx.query))).pipe(Effect.mapError(apiError)),
      )
      .handle("skill.catalog.selection.list", (ctx) =>
        response(SkillCatalog.Service.use((catalog) => catalog.selections(ctx.query))).pipe(Effect.mapError(apiError)),
      )
      .handle("skill.catalog.selection.select", (ctx) =>
        response(SkillCatalog.Service.use((catalog) => catalog.select(ctx.payload))).pipe(Effect.mapError(apiError)),
      )
      .handle("skill.catalog.selection.remove", (ctx) =>
        response(
          SkillCatalog.Service.use((catalog) => catalog.remove(ctx.payload).pipe(Effect.as({ removed: true }))),
        ).pipe(Effect.mapError(apiError)),
      )
  }),
)
