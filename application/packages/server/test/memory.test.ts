import path from "node:path"
import { expect } from "bun:test"
import { Effect } from "effect"
import { tmpdir } from "../../core/test/fixture/tmpdir"
import { it } from "../../core/test/lib/effect"
import { startServer } from "./fixture/server"
it.live("memory status requires server authentication and contains operational metadata only", () =>
  Effect.gen(function* () {
    const tmp = yield* Effect.acquireDisposable(Effect.promise(() => tmpdir("memory-status-api-")))
    const server = yield* startServer(path.join(tmp.path, "global"))
    const url = new URL("/api/memory/status", server.base)
    url.searchParams.set("location[directory]", tmp.path)
    const unauthorized = yield* Effect.promise(() => fetch(url))
    expect(unauthorized.status).toBe(401)
    const response = yield* Effect.promise(() => fetch(url, { headers: server.headers }))
    expect(response.status).toBe(200)
    const result = yield* Effect.promise(() => response.json())
    expect(result.data.memory.outbox.pending).toBe(0)
    expect(result.data.memory.recent).toEqual([])
    expect(result.data.ownership.available).toBe(false)
    expect(JSON.stringify(result)).not.toContain("AGENTMEMORY_SECRET")
  }),
)

it.live("installed skill index is authenticated and returns compact live metadata", () =>
  Effect.gen(function* () {
    const tmp = yield* Effect.acquireDisposable(Effect.promise(() => tmpdir("skill-index-api-")))
    const server = yield* startServer(path.join(tmp.path, "global"))
    const url = new URL("/api/skill/index", server.base)
    url.searchParams.set("location[directory]", tmp.path)
    expect((yield* Effect.promise(() => fetch(url))).status).toBe(401)
    const response = yield* Effect.promise(() => fetch(url, { headers: server.headers }))
    expect(response.status).toBe(200)
    const result = yield* Effect.promise(() => response.json())
    expect(result.data.ranked).toBe(false)
    expect(Array.isArray(result.data.entries)).toBe(true)
    expect(result.data.catalogueSize).toBe(result.data.entries.length)
    expect(result.data.entries.every((entry: Record<string, unknown>) => !("content" in entry))).toBe(true)
  }),
)
