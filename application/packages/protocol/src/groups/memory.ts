import { MemoryObservability } from "@opencode/schema/memory-status"
import { Location } from "@opencode/schema/location"
import { HttpApiEndpoint, HttpApiGroup, OpenApi } from "effect/http-api"
import { LocationQuery, locationQueryOpenApi } from "./location.js"
export const MemoryGroup = HttpApiGroup.make("server.memory")
  .add(
    HttpApiEndpoint.get("memory.status", "/api/memory/status", {
      query: LocationQuery,
      success: Location.response(MemoryObservability.Status),
    })
      .annotateMerge(locationQueryOpenApi)
      .annotateMerge(
        OpenApi.annotations({ identifier: "memory.status", summary: "Native memory and read-only ownership status" }),
      ),
  )
  .annotateMerge(OpenApi.annotations({ title: "memory" }))
