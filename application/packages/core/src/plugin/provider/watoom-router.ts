import { define } from "@opencode/plugin/effect/plugin"
import { Duration, Effect, Schedule, Schema, Stream } from "effect"
import { HttpClient, HttpClientRequest, HttpClientResponse } from "effect/http"
import { Provider } from "../../provider.js"
import { Model } from "../../model.js"
import type { PluginInternal } from "../internal.js"
import { configuredSettings } from "./configured.js"

const Models = Schema.Struct({ data: Schema.Array(Schema.Struct({ id: Schema.String, name: Schema.optional(Schema.String) })) })
const Catalog = Schema.Struct({ available_model_ids: Schema.Array(Schema.String) })
const Status = Schema.Struct({ active_model: Schema.NullOr(Schema.String), active_aliases: Schema.Array(Schema.String) })

type RouterModel = { id: string; name: string; availability: "loaded" | "on-demand" | "unavailable" | "unknown" }
export function routerInventory(models: typeof Models.Type, catalog: typeof Catalog.Type, status: typeof Status.Type): RouterModel[] {
  const resolvable = new Set(catalog.available_model_ids)
  const loaded = new Set([status.active_model, ...status.active_aliases])
  return [...new Map(models.data.filter((item) => item.id.length > 0 && item.id.length <= 256).map((item) => [item.id, {
    id: item.id,
    name: item.name || item.id,
    availability: item.id === "active-model"
      ? status.active_model ? "loaded" as const : "unavailable" as const
      : !resolvable.has(item.id) ? "unavailable" as const
      : loaded.has(item.id) ? "loaded" as const : "on-demand" as const,
  }])).values()]
}

// Opt-in native provider discovery. Only metadata GETs are made; loading and
// unloading remain the router's responsibility when the user submits inference.
export function make(interval: Duration.Input = "60 seconds") {
  return define({
    id: "watoom.provider.router",
    effect: Effect.fn(function* (ctx) {
      const http = HttpClient.filterStatusOk(yield* HttpClient.HttpClient)
      const source = { baseURL: "" }
      const inventory = { rows: [] as ReturnType<typeof routerInventory>, hash: "" }
      const discovered = new Set<string>()
      yield* ctx.provider.transform((providers) => {
        if (!source.baseURL) return
        const provider = providers.get("watoom")
        if (!provider) return
        for (const row of inventory.rows) {
          const existing = provider.models.get(row.id)
          providers.models.update("watoom", row.id, (model) => {
            model.modelID = Model.ID.make(row.id)
            if (!existing) {
              model.name = row.name
              // Router metadata does not verify tools, vision, limits or prices.
              // Apply a conservative text-only policy until model-specific metadata
              // is configured. Never inherit the native 200K/32K defaults.
              discovered.add(row.id)
              model.capabilities = { tools: false, input: ["text"], output: ["text"] }
              model.limit = { context: 8192, output: 2048 }
            }
            model.enabled = row.availability === "loaded" || row.availability === "on-demand"
            model.settings = { ...model.settings, watoomAvailability: row.availability,
              watoomMetadataVerified: !discovered.has(row.id) }
          })
        }
        for (const model of provider.models.values()) {
          if (inventory.rows.some((row) => row.id === model.id)) continue
          providers.models.update("watoom", model.id, (model) => {
            model.enabled = false
            model.settings = { ...model.settings, watoomAvailability: "unavailable" }
          })
        }
      })
      const refresh = Effect.fn("WatoomRouter.refresh")(function* () {
        const settings = yield* configuredSettings(Provider.ID.make("watoom"))
        if (settings?.watoomRouterDiscovery !== true || typeof settings.baseURL !== "string") {
          if (!source.baseURL) return
          source.baseURL = ""
          inventory.rows = []
          inventory.hash = ""
          yield* ctx.provider.reload()
          return
        }
        const baseURL = settings.baseURL.replace(/\/+$/, "")
        const root = baseURL.replace(/\/v1$/, "")
        const get = <A, I>(url: string, schema: Schema.Codec<A, I>) => http.execute(HttpClientRequest.get(url)).pipe(
          Effect.flatMap(HttpClientResponse.schemaBodyJson(schema)), Effect.timeout("3 seconds"),
        )
        const rows = yield* Effect.gen(function* () {
          const models = yield* get(baseURL + "/models", Models)
          const catalog = yield* get(root + "/models", Catalog)
          const status = yield* get(root + "/models/status", Status)
          return routerInventory(models, catalog, status)
        }).pipe(Effect.catch((cause) => Effect.logWarning("WatooM router discovery failed; catalog disabled until recovery", { cause }).pipe(
          Effect.as(inventory.rows.map((row) => ({ ...row, availability: "unknown" as const }))),
        )))
        const hash = JSON.stringify([baseURL, rows])
        if (hash === inventory.hash) return
        source.baseURL = baseURL
        inventory.rows = rows
        inventory.hash = hash
        yield* ctx.provider.reload()
      })
      yield* refresh().pipe(Effect.ignore, Effect.repeat(Schedule.spaced(interval)), Effect.forkScoped)
      yield* ctx.event.subscribe().pipe(Stream.filter((event) => event.type === "config.updated"),
        Stream.runForEach(() => refresh().pipe(Effect.ignore)), Effect.forkScoped)
    }),
  } satisfies PluginInternal.InternalPlugin)
}

export const WatoomRouterPlugin = make()
