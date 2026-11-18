import { SkillRouting } from "@opencode/schema/skill-routing"
import { SkillAdministration } from "@opencode/schema/skill-administration"
import { SkillCatalog } from "@opencode/schema/skill-catalog"
import { Agent } from "@opencode/schema/agent"
import { Session } from "@opencode/schema/session"
import { InvalidRequestError, ServiceUnavailableError, UnauthorizedError } from "../errors.js"
import { Skill } from "@opencode/schema/skill"
import { Location } from "@opencode/schema/location"
import { Schema, SchemaGetter } from "effect"
import { HttpApiEndpoint, HttpApiGroup, OpenApi } from "effect/http-api"
import { LocationQuery, locationQueryOpenApi } from "./location.js"

const BooleanFromString = Schema.Literals(["true", "false"]).pipe(
  Schema.decodeTo(Schema.Boolean, {
    decode: SchemaGetter.transform((value) => value === "true"),
    encode: SchemaGetter.transform((value): "true" | "false" => (value ? "true" : "false")),
  }),
)

export const SkillGroup = HttpApiGroup.make("server.skill")
  .add(
    HttpApiEndpoint.get("skill.index", "/api/skill/index", {
      query: Schema.Struct({
        ...LocationQuery.fields,
        query: Schema.optional(Schema.String.check(Schema.isMaxLength(4096))),
      }),
      success: Location.response(SkillRouting.SearchSchema),
    })
      .annotateMerge(locationQueryOpenApi)
      .annotateMerge(
        OpenApi.annotations({
          identifier: "skill.index",
          summary: "Search the compact live skills and pipelines catalogue",
        }),
      ),
  )

  .add(
    HttpApiEndpoint.get("skill.list", "/api/skill", {
      query: LocationQuery,
      success: Location.response(Schema.Array(Skill.Info)),
    })
      .annotateMerge(locationQueryOpenApi)
      .annotateMerge(
        OpenApi.annotations({
          identifier: "skill.list",
          summary: "List skills",
          description: "Retrieve currently registered skills.",
        }),
      ),
  )
  .add(
    HttpApiEndpoint.get("skill.catalog.list", "/api/skill/catalog", {
      query: Schema.Struct({
        ...LocationQuery.fields,
        query: Schema.optional(Schema.String.check(Schema.isMaxLength(256))),
        limit: Schema.optional(
          Schema.NumberFromString.check(Schema.isInt(), Schema.isBetween({ minimum: 1, maximum: 32 })),
        ),
        offset: Schema.optional(
          Schema.NumberFromString.check(Schema.isInt(), Schema.isBetween({ minimum: 0, maximum: 10000 })),
        ),
        view: Schema.optional(Schema.Literals(["installed", "available", "pending", "disabled"])),
        sort: Schema.optional(Schema.Literals(["name", "source"])),
        approvedOnly: Schema.optional(BooleanFromString),
        validOnly: Schema.optional(BooleanFromString),
        license: Schema.optional(Schema.String.check(Schema.isMaxLength(128))),
        repo: Schema.optional(Schema.String.check(Schema.isMaxLength(256))),
      }),
      success: Location.response(SkillCatalog.Page),
      error: ServiceUnavailableError,
    })
      .annotateMerge(locationQueryOpenApi)
      .annotateMerge(
        OpenApi.annotations({
          identifier: "skill.catalog.list",
          summary: "Browse skill catalog metadata",
          description:
            "Read bounded catalog metadata. Approval is separate from selection; no acquired instructions or code are loaded.",
        }),
      ),
  )
  .add(
    HttpApiEndpoint.get("skill.catalog.selection.list", "/api/skill/catalog/selection", {
      query: Schema.Struct({
        ...LocationQuery.fields,
        agent: Agent.ID,
        target: Schema.Literals(["agent", "session"]),
        sessionID: Schema.optional(Session.ID),
      }),
      success: Location.response(Schema.Array(SkillCatalog.Selection)),
      error: [InvalidRequestError, ServiceUnavailableError],
    })
      .annotateMerge(locationQueryOpenApi)
      .annotateMerge(
        OpenApi.annotations({ identifier: "skill.catalog.selection.list", summary: "List scoped skill selections" }),
      ),
  )
  .add(
    HttpApiEndpoint.post("skill.catalog.selection.select", "/api/skill/catalog/selection", {
      query: LocationQuery,
      payload: Schema.Struct({
        agent: Agent.ID,
        target: Schema.Literals(["agent", "session"]),
        sessionID: Schema.optional(Session.ID),
        skillID: Schema.String.check(Schema.isMinLength(1), Schema.isMaxLength(512)),
      }),
      success: Location.response(SkillCatalog.Selection),
      error: [InvalidRequestError, ServiceUnavailableError],
    })
      .annotateMerge(locationQueryOpenApi)
      .annotateMerge(
        OpenApi.annotations({
          identifier: "skill.catalog.selection.select",
          summary: "Select an approved pinned skill",
          description:
            "Records scoped version references only. Does not approve or execute instructions, grant tools, or install dependencies.",
        }),
      ),
  )
  .add(
    HttpApiEndpoint.delete("skill.catalog.selection.remove", "/api/skill/catalog/selection", {
      query: LocationQuery,
      payload: Schema.Struct({
        agent: Agent.ID,
        target: Schema.Literals(["agent", "session"]),
        sessionID: Schema.optional(Session.ID),
        skillID: Schema.String.check(Schema.isMinLength(1), Schema.isMaxLength(512)),
      }),
      success: Location.response(Schema.Struct({ removed: Schema.Boolean })),
      error: [InvalidRequestError, ServiceUnavailableError],
    })
      .annotateMerge(locationQueryOpenApi)
      .annotateMerge(
        OpenApi.annotations({
          identifier: "skill.catalog.selection.remove",
          summary: "Remove a scoped skill preference",
        }),
      ),
  )
  .add(
    HttpApiEndpoint.post("skill.catalog.admin", "/api/skill/catalog/admin", {
      query: LocationQuery,
      payload: SkillAdministration.Request,
      success: Location.response(SkillAdministration.Receipt),
      error: [InvalidRequestError, ServiceUnavailableError, UnauthorizedError],
    }),
  )
  .add(
    HttpApiEndpoint.get("skill.catalog.detail", "/api/skill/catalog/detail", {
      query: Schema.Struct({
        ...LocationQuery.fields,
        skillID: Schema.String.check(Schema.isMinLength(1), Schema.isMaxLength(512)),
      }),
      success: Location.response(SkillCatalog.Detail),
      error: [InvalidRequestError, ServiceUnavailableError],
    }),
  )
  .annotateMerge(
    OpenApi.annotations({
      title: "skill",
      description: "Experimental skill routes.",
    }),
  )
