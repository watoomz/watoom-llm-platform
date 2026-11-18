import { expect, test } from "bun:test"
import { Effect, Fiber } from "effect"
import { MeshHandover } from "../src/watoom/mesh-handover"
import type { Tool } from "@opencode/schema/tool"
import { envelope, type Event } from "../src/watoom/contract"

function fixture(state = "observed") {
  const phases: string[] = []
  const rows = new Map<string, string>()
  const events: Event[] = []
  const memory = { enabled: true, remember: (event: Event) => Effect.try({
    try: () => {
      const value = envelope(event)
      const prior = rows.get(value.id)
      if (prior && prior !== value.digest) throw Error("conflicting checkpoint")
      rows.set(value.id, value.digest)
      events.push(event)
      phases.push(JSON.parse(event.content).phase)
      return { id: value.id, state }
    }, catch: (error) => error as Error,
  }) }
  const input = { server: "watoom-llama-mesh", tool: "generate", args: { request_id: "owned_gpu_fixture", prompt: "A cube" },
    sessionID: "ses_gpu_fixture", memory, scope: Effect.succeed({ project: "p", repository: "/fixture", agent: "fixture" }) }
  const receipt = { job_id: "20261017T000000Z-12345678", manifest: { result: "PASS", PRIMARY_QWEN_RESTORED: "yes",
    primary_health: { ready: "yes", inference: "PASS", model: "swift-qwen38-coder" }, glb_sha256: "a".repeat(64) } }
  const execute = Effect.sync(() => {
    phases.push("EXECUTE")
    return { output: receipt,
      content: [{ type: "text", text: JSON.stringify(receipt) }] } satisfies Tool.Result
  })
  return { input, execute, phases, events, receipt, rows }
}
test("GPU side effect follows durable checkpoint and completion follows validated restoration", async () => {
  const f = fixture()
  await Effect.runPromise(MeshHandover.run(f.input, f.execute))
  expect(f.phases).toEqual(["GPU_HANDOVER_PENDING", "EXECUTE", "PRIMARY_RESTORED"])
  expect(f.events.map((e) => e.seq)).toEqual([1, 2])
  expect(f.events.every((e) => e.scope.repository === "/fixture")).toBe(true)
  expect(f.events.map((e) => e.content).join("")).not.toContain("A cube")
})
test("disabled, unverified local durability and asynchronous submission cannot mutate GPU", async () => {
  for (const change of ["disabled", "unknown", "submit", "no-id"]) {
    const f = fixture(change === "unknown" ? "unknown" : "observed")
    if (change === "disabled") f.input.memory.enabled = false
    if (change === "submit") f.input.tool = "submit"
    if (change === "no-id") f.input.args.request_id = ""
    await expect(Effect.runPromise(MeshHandover.run(f.input, f.execute))).rejects.toThrow()
    expect(f.phases).not.toContain("EXECUTE")
  }
})
test("remote memory outage retains local checkpoint/outbox before GPU work", async () => {
  const f = fixture("uncertain")
  await Effect.runPromise(MeshHandover.run(f.input, f.execute))
  expect(f.phases).toEqual(["GPU_HANDOVER_PENDING", "EXECUTE", "PRIMARY_RESTORED"])
})
test("unverified restoration is not reported successful and a stable retry remains reconcilable", async () => {
  const f = fixture()
  f.receipt.manifest.PRIMARY_QWEN_RESTORED = "no"
  await expect(Effect.runPromise(MeshHandover.run(f.input, f.execute))).rejects.toThrow()
  expect(f.phases).toContain("GPU_OUTCOME_UNCERTAIN")
  f.receipt.manifest.PRIMARY_QWEN_RESTORED = "yes"
  await Effect.runPromise(MeshHandover.run(f.input, f.execute))
  expect(f.phases.at(-1)).toBe("PRIMARY_RESTORED")
  expect(f.rows.size).toBe(3)
})
test("changed arguments under the same request identity fail before replaying the side effect", async () => {
  const f = fixture()
  await Effect.runPromise(MeshHandover.run(f.input, f.execute))
  f.input.args.prompt = "A different object"
  await expect(Effect.runPromise(MeshHandover.run(f.input, f.execute))).rejects.toThrow("conflicting checkpoint")
  expect(f.phases.filter((e) => e === "EXECUTE")).toHaveLength(1)
})
test("interruption retains the original interruption and records an uncertain checkpoint", async () => {
  const f = fixture()
  const fiber = Effect.runFork(MeshHandover.run(f.input, Effect.never))
  await Bun.sleep(10)
  await Effect.runPromise(Fiber.interrupt(fiber))
  const exit = await Effect.runPromise(Fiber.await(fiber))
  expect(exit._tag).toBe("Failure")
  expect(f.phases).toContain("GPU_OUTCOME_UNCERTAIN")
})
