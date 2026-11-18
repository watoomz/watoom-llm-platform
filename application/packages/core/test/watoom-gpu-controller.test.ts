import { expect, test } from "bun:test"
import fs from "node:fs/promises"
import path from "node:path"
import { createHash } from "node:crypto"
import { GpuController } from "@opencode/core/watoom/gpu-controller"
import type { Specialist } from "@opencode/core/watoom/specialist"
const hash = (text: string) => createHash("sha256").update(text).digest("hex")

test("actual G3H/G3G Unix contract enforces admission, epochs, restart and exact idempotent restoration", async () => {
  const root = await fs.mkdtemp("/tmp/watoom-g3g-")
  const socket = path.join(root, "controller.sock")
  const source = process.env.WATOOM_GPU_CONTROLLER_SOURCE ?? "/data/ai/helper-scripts/gpu-controller"
  let server = Bun.spawn(["python3", "-B", path.join(import.meta.dirname, "fixture/g3g-socket.py"), root, socket, source], { stdout: "pipe", stderr: "pipe" })
  const ready = async () => { const reader = server.stdout.getReader(); const line = await reader.read(); reader.releaseLock(); if (!new TextDecoder().decode(line.value).includes("READY")) throw Error(await new Response(server.stderr).text()) }
  await ready()
  const client = new GpuController.Client(socket, 3000)
  const inspectPrimary = async () => {
    const api = JSON.parse(await fs.readFile(path.join(root, "api.json"), "utf8"))
    const runtimeConfiguration = JSON.stringify(api.qwen.spec)
    return { runtimeConfiguration, identity: { model: "fixture-primary", modelSha256: "a".repeat(64), configurationSha256: hash(runtimeConfiguration), deploymentUID: "qwen-uid", router: "fixture-router" } }
  }
  let active = 0
  const options = { client, journal: new GpuController.Journal(path.join(root, "native-proof")), controllerJob: "20261016T000000Z-12345678", primaryDeployment: "qwen", specialistDeploymentUID: "mesh-uid", iApprove: true, activeJobs: async () => active, inspectPrimary, primarySmoke: async () => true }
  const authority = new GpuController.Authority(options)
  const snapshot = await inspectPrimary()
  const descriptor: Specialist.Descriptor = { id: "fixture-specialist", capabilities: ["geometry.generate"], backend: "fixture", model: { ...snapshot.identity, model: "fixture-specialist", deploymentUID: "mesh-uid" }, execution: "exclusive-gpu", inputSchema: "fixture", outputSchema: "fixture", timeoutMs: 3000, maxInputBytes: 1000, resources: { cpuCores: 1, ramMiB: 128, gpuMiB: 1024, diskMiB: 64 }, requiredSkills: [], requiredTools: [], cancellation: "cooperative-abort", recovery: "positive-receipt-only", restoration: "exact-primary-identity", sourceCommit: "a".repeat(40), evidence: "fixture" }
  try {
    await expect(new GpuController.Authority({ ...options, iApprove: false }).acquire("1".repeat(64), snapshot.identity)).rejects.toThrow("--i-approve")
    active = 1
    await expect(authority.acquire("1".repeat(64), snapshot.identity)).rejects.toThrow("active")
    active = 0
    await expect(authority.acquire("1".repeat(64), { ...snapshot.identity, configurationSha256: "f".repeat(64) })).rejects.toThrow("drift")
    const lease = await authority.acquire("c".repeat(64), snapshot.identity)
    expect(lease.generation).toBe(1)
    await expect(authority.acquire("d".repeat(64), snapshot.identity)).rejects.toThrow("admission")
    await expect(authority.activate({ ...lease, generation: 2 }, descriptor)).rejects.toThrow("Stale")
    await authority.activate(lease, descriptor)
    expect((await client.status()).phase).toBe("mesh-active")
    await authority.restore(lease, snapshot.identity)
    expect(await authority.validatePrimary(lease, snapshot.identity)).toBe(true)
    const before = await fs.readFile(path.join(root, "api.json"), "utf8")
    await authority.restore(lease, snapshot.identity)
    expect(await fs.readFile(path.join(root, "api.json"), "utf8")).toBe(before)
    await expect(authority.recover(lease, snapshot.identity, false)).rejects.toThrow("owner-death")
    server.kill("SIGTERM"); await server.exited
    server = Bun.spawn(["python3", "-B", path.join(import.meta.dirname, "fixture/g3g-socket.py"), root, socket, source], { stdout: "pipe", stderr: "pipe" })
    await ready()
    expect((await client.status()).generation).toBe(1)
    expect((await client.status()).phase).toBe("qwen-ready")
    expect(await authority.validatePrimary(lease, snapshot.identity)).toBe(true)
    const journal = await options.journal.read(lease.job)
    expect(journal.snapshot).toEqual(snapshot)
    expect(journal.phase).toBe("PRIMARY_READY")
  } finally { server.kill("SIGTERM"); await server.exited }
}, 30000)
