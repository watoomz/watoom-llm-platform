import { test, expect } from "bun:test"
import { Effect } from "effect"
import { MemoryCommand } from "../src/plugin/watoom-memory-command"
import { NativeMemory } from "../src/watoom/native-memory"
import { Location } from "../src/location"
import { Session } from "../src/session"
import { Bus } from "../src/bus"
import { Permission } from "../src/permission"
import type { Context } from "@opencode/plugin/effect/plugin"
import type { SessionHooks } from "@opencode/plugin/effect/session"
import type { Definition } from "../src/command"
async function fixture(denied = false, wrongProject = false) {
  let context: ((event: SessionHooks["context"]) => Effect.Effect<void>) | undefined
  const definitions = new Map<string, Definition>(),
    writes: unknown[] = [],
    published: unknown[] = [],
    searches: unknown[] = []
  const ctx = {
    command: {
      transform: (f: (e: { add: (d: Definition) => void }) => void) =>
        Effect.sync(() =>
          f({
            add: (d) => {
              definitions.set(d.name, d)
            },
          }),
        ),
    },
    session: {
      hook: (_name: string, callback: typeof context) =>
        Effect.sync(() => {
          context = callback
        }),
    },
  } as unknown as Context
  await Effect.runPromise(
    MemoryCommand.Plugin.effect(ctx).pipe(
      Effect.provideService(NativeMemory.Service, {
        enabled: true,
        required: false,
        status: Effect.die(Error("unused status fixture")),
        revise: () => Effect.fail(Error("unused revision fixture")),
        flush: Effect.void,
        learn: () => Effect.die(Error("unused learning fixture")),
        recall: () => Effect.succeed(["- [decision, verified 2026-11-21] fixture knowledge"]),
        remember: (e) =>
          Effect.sync(() => {
            writes.push(e)
            return { id: "receipt", state: "observed" }
          }),
        search: (scope, query) =>
          Effect.sync(() => {
            searches.push({ scope, query })
            return []
          }),
      }),
      Effect.provideService(Location.Service, { project: { id: "project-a" }, directory: "/fixture" } as never),
      Effect.provideService(Session.Service, {
        get: () =>
          Effect.succeed({
            projectID: wrongProject ? "project-b" : "project-a",
            location: { directory: "/fixture" },
            agent: "fixture",
          }),
      } as never),
      Effect.provideService(Bus.Service, {
        publish: (_event: unknown, data: unknown) =>
          Effect.sync(() => {
            published.push(data)
          }),
      } as never),
      Effect.provideService(Permission.Service, {
        assert: () => (denied ? Effect.fail(Error("denied")) : Effect.void),
      } as never),
      Effect.scoped,
    ),
  )
  const run = (name: string, text: string) =>
    Effect.runPromise(
      definitions.get(name)!.execute({ sessionID: "ses_fixture", prompt: { text }, delivery: "queue" } as never),
    )
  return {
    definitions,
    writes,
    published,
    searches,
    run,
    context: (event: SessionHooks["context"]) => Effect.runPromise(context!(event)),
  }
}
test("native command registration and execution use authenticated caller scope", async () => {
  const f = await fixture()
  expect([...f.definitions.keys()]).toEqual([
    "remember",
    "recall",
    "memory-correct",
    "memory-supersede",
    "memory-consolidate",
    "memory-withdraw",
    "memory-status",
  ])
  await f.run("remember", "project knowledge")
  await f.run("recall", "knowledge")
  expect(f.writes).toHaveLength(1)
  expect(f.searches).toEqual([
    { scope: { project: "project-a", repository: "/fixture", agent: "fixture" }, query: "knowledge" },
  ])
  expect(f.published).toHaveLength(2)
  expect(JSON.stringify(f.published[1])).toContain("fixture knowledge")
})
test("permission rejection, wrong project and invalid input cause no memory writes", async () => {
  for (const f of [await fixture(true), await fixture(false, true)]) {
    await expect(f.run("remember", "knowledge")).rejects.toThrow()
    expect(f.writes).toHaveLength(0)
  }
  const f = await fixture()
  await expect(f.run("remember", " ")).rejects.toThrow()
  await expect(f.run("recall", "x".repeat(1025))).rejects.toThrow()
  expect(f.writes).toHaveLength(0)
})

test("native first-context recall is scoped and bounded across routine context refreshes", async () => {
  const f = await fixture()
  const event = {
    sessionID: "ses_start_fixture",
    agent: "fixture",
    system: [],
    messages: [],
  } as unknown as SessionHooks["context"]
  await f.context(event)
  await f.context(event)
  expect(f.searches).toEqual([
    {
      scope: { project: "project-a", repository: "/fixture", agent: "fixture" },
      query: "project continuation decisions milestones",
    },
  ])
  expect(event.system).toHaveLength(0)
  expect(f.writes).toHaveLength(0)
})
