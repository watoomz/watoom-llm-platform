import { describe, expect, test } from "bun:test"
import { routerInventory } from "../../src/plugin/provider/watoom-router"
import { make } from "../../src/plugin/provider/watoom-router"
import { Config } from "@opencode/core/config"
import { ConfigProviderPlugin } from "../../src/config/plugin/provider"
import { Model } from "@opencode/core/model"
import { Plugin } from "@opencode/core/plugin"
import { PluginHost } from "@opencode/core/plugin/host"
import { Provider } from "@opencode/core/provider"
import { Document, Info } from "@opencode/schema/config"
import { Effect, Layer, Schema } from "effect"
import { testEffect } from "../lib/effect"
import { PluginTestLayer } from "./fixture"

describe("WatooM router metadata", () => {
  test("distinguishes advertised names, resolvable IDs and currently loaded aliases", () => {
    const result = routerInventory({ data: [
      { id: "swift", name: "Authoritative Swift" }, { id: "other", name: "Other" },
      { id: "stale" }, { id: "active-model" }, { id: "swift", name: "Authoritative Swift" },
    ] }, { available_model_ids: ["swift", "other"] }, { active_model: "swift", active_aliases: [] })
    expect(result).toEqual([
      { id: "swift", name: "Authoritative Swift", availability: "loaded" },
      { id: "other", name: "Other", availability: "on-demand" },
      { id: "stale", name: "stale", availability: "unavailable" },
      { id: "active-model", name: "active-model", availability: "loaded" },
    ])
  })
  test("does not claim an active alias is loaded when the router has no active model", () => {
    expect(routerInventory({ data: [{ id: "active-model" }] }, { available_model_ids: [] },
      { active_model: null, active_aliases: [] })[0]?.availability).toBe("unavailable")
  })
})

const it = testEffect(Layer.merge(PluginTestLayer, Config.testLayer()))
for (const providerOwned of [false, true]) it.live("discovers through metadata GETs; provider-owned settings=" + providerOwned, () =>
  Effect.acquireUseRelease(
    Effect.sync(() => {
      const requests: string[] = []
      const state = { failing: false }
      const server = Bun.serve({ port: 0, fetch: (request) => {
        const path = new URL(request.url).pathname
        requests.push(request.method + " " + path)
        if (state.failing) return new Response(null, { status: 503 })
        if (path === "/v1/models") return Response.json({ data: [{ id: "swift", name: "Verified Swift" }, { id: "other", name: "Verified Other" }] })
        if (path === "/models") return Response.json({ available_model_ids: ["swift", "other"] })
        if (path === "/models/status") return Response.json({ active_model: "swift", active_aliases: [] })
        return new Response(null, { status: 400 })
      } })
      return { server, requests, state }
    }),
    ({ server, requests, state }) => Effect.gen(function* () {
      const config = yield* Config.Test
      yield* config.setEntries(providerOwned ? [] : [new Document({ type: "document", info: Schema.decodeUnknownSync(Info)({
        providers: { watoom: { package: "@opencode/ai/providers/openai-compatible", settings: { baseURL: server.url.origin + "/v1", watoomRouterDiscovery: true } } },
      }) })])
      const providers = yield* Provider.Service
      const id = Provider.ID.make("watoom")
      const plugin = yield* Plugin.Service
      const host = yield* PluginHost.make(plugin)
      if (providerOwned) {
        yield* providers.transform((editor) => editor.update(id, (provider) => {
          provider.activation = "enabled"
          provider.package = "@opencode/ai/providers/openai-compatible"
          provider.settings = { baseURL: server.url.origin + "/v1", watoomRouterDiscovery: true }
        }))
      } else {
        // Match native post-plugin order: configured providers exist before
        // discovery decorates their catalog.
        yield* ConfigProviderPlugin.Plugin.effect(host)
      }
      yield* make("10 millis").effect(host)
      const models = yield* Model.Service
      for (let attempt = 0; attempt < 100; attempt++) {
        if (yield* models.get(id, Model.ID.make("other"))) break
        yield* Effect.promise(() => Bun.sleep(10))
      }
      expect(yield* models.get(id, Model.ID.make("swift"))).toMatchObject({ settings: { watoomAvailability: "loaded" } })
      expect(yield* models.get(id, Model.ID.make("other"))).toMatchObject({ name: "Verified Other", settings: { watoomAvailability: "on-demand", watoomMetadataVerified: false } })
      expect(yield* models.get(id, Model.ID.make("other"))).toMatchObject({ capabilities: { tools: false, input: ["text"], output: ["text"] }, limit: { context: 8192, output: 2048 } })
      expect([...new Set(requests)]).toEqual(["GET /v1/models", "GET /models", "GET /models/status"])
      expect(Provider.nativeSettings({ watoomAvailability: "loaded", watoomMetadataVerified: false, watoomRouterDiscovery: true, temperature: 0.2 })).toEqual({ temperature: 0.2 })
      state.failing = true
      for (let attempt = 0; attempt < 100; attempt++) {
        if ((yield* models.get(id, Model.ID.make("swift")))?.settings?.watoomAvailability === "unknown") break
        yield* Effect.promise(() => Bun.sleep(10))
      }
      expect(yield* models.get(id, Model.ID.make("swift"))).toMatchObject({ enabled: false, settings: { watoomAvailability: "unknown" } })
    }),
    ({ server }) => Effect.promise(() => server.stop(true)),
  ),
)
