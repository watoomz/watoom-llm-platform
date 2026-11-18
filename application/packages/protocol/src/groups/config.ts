import { InvalidRequestError } from "../errors.js"
import { ProfileSchema } from "@opencode/schema/profiles"
import { Config } from "@opencode/schema/config"
import { ConfigShell } from "@opencode/schema/config/shell"
import { Schema } from "effect"
import { HttpApiEndpoint, HttpApiGroup, HttpApiSchema, OpenApi } from "effect/http-api"
import { LocationQuery, locationQueryOpenApi } from "./location.js"

export const ConfigGroup = HttpApiGroup.make("server.config")
  .add(
    HttpApiEndpoint.get("config.get", "/api/config", {
      query: LocationQuery,
      success: Schema.Array(Config.Entry),
    })
      .annotateMerge(locationQueryOpenApi)
      .annotateMerge(
        OpenApi.annotations({
          identifier: "config.get",
          summary: "Get configuration",
          description:
            "Return configuration documents and discovery sources for the requested location, from lowest to highest priority.",
        }),
      ),
  )
  .add(
    HttpApiEndpoint.get("config.shells", "/api/config/shell", {
      success: Schema.Array(ConfigShell.Option),
    }).annotateMerge(
      OpenApi.annotations({
        identifier: "config.shells",
        summary: "List available shells",
        description: "Return shells available to terminal and agent execution.",
      }),
    ),
  )
  .add(
    HttpApiEndpoint.patch("config.update", "/api/experimental/config", {
      payload: Config.Patch,
      success: HttpApiSchema.NoContent,
    }).annotateMerge(
      OpenApi.annotations({
        identifier: "experimental.config.update",
        summary: "Update global configuration",
        description: "Patch supported fields in the highest-precedence global configuration document.",
      }),
    ),
  )
  .add(
    HttpApiEndpoint.get("config.spaces", "/api/config/spaces", { success: Schema.Array(Config.Space) }).annotateMerge(
      OpenApi.annotations({
        identifier: "config.spaces",
        summary: "List project spaces",
        description: "Return the project spaces the deployment publishes for grouping and creating projects in the new-session picker.",
      }),
    ),
  )
  .add(HttpApiEndpoint.get("config.profiles.export", "/api/config/profiles/export", { success: Schema.Struct({ configuration: Schema.String }) }))
  .add(HttpApiEndpoint.get("config.profiles.list", "/api/config/profiles", { success: ProfileSchema.Catalog }))
  .add(HttpApiEndpoint.post("config.profiles.install", "/api/config/profiles", { payload: ProfileSchema.Install, success: ProfileSchema.Resolution, error: InvalidRequestError }))
  .add(HttpApiEndpoint.post("config.profiles.rollback", "/api/config/profiles/rollback", {
    payload: ProfileSchema.Rollback,
    success: Schema.Struct({ status: Schema.String, transaction: Schema.String }),
  }))
  .annotateMerge(OpenApi.annotations({ title: "config", description: "Location-scoped configuration routes." }))
