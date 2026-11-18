export * as GpuController from "./gpu-controller.js"
import { createConnection } from "node:net"
import { mkdir, open, readFile, rename } from "node:fs/promises"
import path from "node:path"
import { createHash, randomUUID } from "node:crypto"
import type { Specialist } from "./specialist.js"

export type Status = { phase: string; owner: string | null; generation: number; uncertain: boolean; primary: string }
export class Client {
  constructor(readonly socket: string, readonly timeoutMs = 600000) {
    if (!path.isAbsolute(socket)) throw Error("Controller requires an explicit Unix socket")
  }
  call<T>(action: "status" | "can-use-qwen" | "begin" | "activate" | "asset-saved" | "restore" | "recover", fields: { job?: string; generation?: number } = {}): Promise<T> {
    const request = JSON.stringify({ action, ...fields }) + "\n"
    return new Promise((resolve, reject) => {
      const socket = createConnection(this.socket)
      let data = ""
      const finish = (error?: Error, value?: T) => { socket.destroy(); error ? reject(error) : resolve(value!) }
      socket.setTimeout(action === "status" ? Math.min(this.timeoutMs, 10000) : this.timeoutMs)
      socket.on("connect", () => socket.write(request))
      socket.on("timeout", () => finish(Error("Controller outcome unknown; no unmanaged fallback")))
      socket.on("error", () => finish(Error("Authoritative controller unavailable")))
      socket.on("data", (chunk) => {
        data += chunk.toString("utf8")
        if (Buffer.byteLength(data) > 65536) return finish(Error("Controller response too large"))
        if (!data.includes("\n")) return
        try {
          const response = JSON.parse(data.slice(0, data.indexOf("\n")))
          if (response.error || !("result" in response)) return finish(Error("Controller rejected: " + String(response.error ?? "invalid response") + ": " + String(response.detail ?? "").slice(0, 512)))
          finish(undefined, response.result)
        } catch { finish(Error("Invalid controller response")) }
      })
      socket.on("end", () => { if (!data.includes("\n")) finish(Error("Controller acknowledgment lost")) })
    })
  }
  status() { return this.call<Status>("status") }
}
function sameIdentity(a: Specialist.ModelIdentity, b: Specialist.ModelIdentity) { return JSON.stringify([a.model,a.modelSha256,a.configurationSha256,a.deploymentUID,a.router,a.projectorSha256]) === JSON.stringify([b.model,b.modelSha256,b.configurationSha256,b.deploymentUID,b.router,b.projectorSha256]) }
export type Snapshot = { identity: Specialist.ModelIdentity; runtimeConfiguration: string }
export class Journal {
  constructor(readonly root: string) {}
  async read(operation: string) { return JSON.parse(await readFile(path.join(this.root, operation + ".json"), "utf8")) }
  async record(operation: string, phase: string, fields: Record<string, unknown> = {}) {
    if (!/^[a-f0-9]{64}$/.test(operation)) throw Error("Invalid native operation identity")
    await mkdir(this.root, { recursive: true, mode: 0o700 })
    const target = path.join(this.root, operation + ".json")
    const prior = await readFile(target, "utf8").then((value) => JSON.parse(value), (error: NodeJS.ErrnoException) => { if (error.code === "ENOENT") return { operation, events: [] }; throw error })
    const { snapshot, ...metadata } = fields
    if (snapshot && prior.snapshot && JSON.stringify(prior.snapshot) !== JSON.stringify(snapshot)) throw Error("Primary checkpoint changed")
    const state = { ...prior, ...(snapshot ? { snapshot } : {}), ...metadata, phase, events: [...prior.events, { phase, at: new Date().toISOString() }].slice(-128) }
    const temporary = target + "." + randomUUID() + ".tmp"
    const file = await open(temporary, "wx", 0o600)
    try { await file.writeFile(JSON.stringify(state)); await file.sync() } finally { await file.close() }
    await rename(temporary, target)
    const directory = await open(this.root, "r")
    try { await directory.sync() } finally { await directory.close() }
  }
}
export class Authority implements Specialist.GpuAuthority {
  readonly kind = "g3h-g3g" as const
  private snapshots = new Map<string, Snapshot>()
  constructor(readonly options: {
    client: Client; journal: Journal; controllerJob: string; primaryDeployment: string; specialistDeploymentUID: string;
    iApprove: boolean; activeJobs: () => Promise<number>; inspectPrimary: () => Promise<Snapshot>; primarySmoke: () => Promise<boolean>
  }) {
    if (!/^[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}$/.test(options.controllerJob)) throw Error("Controller job must be the verified systemd worker identity")
  }
  private async owned(lease: Specialist.Lease) {
    const state = await this.options.client.status()
    if (state.owner !== this.options.controllerJob || state.generation !== lease.generation) throw Error("Stale controller fencing generation or owner")
    return state
  }
  async acquire(operation: string, primary: Specialist.ModelIdentity) {
    if (!this.options.iApprove) throw Error("RISK: stopping the active primary may interrupt inference; explicit --i-approve is required")
    if (await this.options.activeJobs()) throw Error("Admission denied: active incompatible inference or OpenCode jobs")
    const state = await this.options.client.status()
    if (state.phase !== "qwen-ready" || state.owner || state.uncertain || state.primary !== this.options.primaryDeployment) throw Error("Controller admission denied")
    const snapshot = await this.options.inspectPrimary()
    if (!sameIdentity(snapshot.identity, primary)) throw Error("Primary identity drift before checkpoint")
    if (createHash("sha256").update(snapshot.runtimeConfiguration).digest("hex") !== primary.configurationSha256) throw Error("Runtime checkpoint hash mismatch")
    await this.options.journal.record(operation, "PRIMARY_CHECKPOINTING", { snapshot, controllerJob: this.options.controllerJob, baseGeneration: state.generation })
    await this.options.journal.record(operation, "ACQUIRING")
    const result = await this.options.client.call<{ generation: number }>("begin", { job: this.options.controllerJob })
    if (!Number.isSafeInteger(result.generation) || result.generation <= state.generation) throw Error("Invalid fencing acknowledgment")
    this.snapshots.set(operation, snapshot)
    await this.options.journal.record(operation, "ACQUIRED", { generation: result.generation })
    return { job: operation, generation: result.generation }
  }
  async reconcileLease(operation: string) {
    const checkpoint = await this.options.journal.read(operation)
    const state = await this.options.client.status()
    if (checkpoint.operation !== operation || checkpoint.controllerJob !== this.options.controllerJob || state.owner !== this.options.controllerJob || state.generation <= checkpoint.baseGeneration) return undefined
    return { job: operation, generation: state.generation }
  }
  async activate(lease: Specialist.Lease, specialist: Specialist.Descriptor) {
    const state = await this.owned(lease)
    if (state.phase !== "acquiring" || state.uncertain || specialist.model.deploymentUID !== this.options.specialistDeploymentUID) throw Error("Specialist does not match the controller-authorized slot")
    await this.options.journal.record(lease.job, "PRIMARY_STOPPING")
    await this.options.journal.record(lease.job, "SPECIALIST_STARTING")
    try { await this.options.client.call("activate", { job: this.options.controllerJob, generation: lease.generation }) } catch (error) { await this.options.journal.record(lease.job, "RECOVERY_REQUIRED"); throw error }
    const ready = await this.owned(lease)
    if (ready.phase !== "mesh-active" || ready.uncertain) throw Error("Controller specialist readiness unverified")
    await this.options.journal.record(lease.job, "SPECIALIST_READY")
    await this.options.journal.record(lease.job, "SPECIALIST_EXECUTING")
  }
  async restore(lease: Specialist.Lease, _primary: Specialist.ModelIdentity) {
    const state = await this.options.client.status()
    if (state.phase === "qwen-ready" && !state.owner && !state.uncertain && state.generation === lease.generation) return
    await this.owned(lease)
    if (state.uncertain || ["restoring", "recovery-required"].includes(state.phase)) throw Error("RECOVERY_REQUIRED: ambiguous controller mutation requires fenced recovery")
    await this.options.journal.record(lease.job, "SPECIALIST_STOPPING")
    await this.options.journal.record(lease.job, "PRIMARY_RESTORING")
    try { await this.options.client.call("restore", { job: this.options.controllerJob, generation: lease.generation }) } catch (error) { await this.options.journal.record(lease.job, "RECOVERY_REQUIRED"); throw error }
    await this.options.journal.record(lease.job, "PRIMARY_VALIDATING")
  }
  async validatePrimary(lease: Specialist.Lease, primary: Specialist.ModelIdentity) {
    const state = await this.options.client.status()
    if (state.phase !== "qwen-ready" || state.owner || state.uncertain || state.generation !== lease.generation) return false
    const snapshot = await this.options.inspectPrimary()
    if (!sameIdentity(snapshot.identity, primary) || createHash("sha256").update(snapshot.runtimeConfiguration).digest("hex") !== primary.configurationSha256 || !(await this.options.primarySmoke())) return false
    await this.options.journal.record(lease.job, "PRIMARY_READY")
    return true
  }
  async recover(lease: Specialist.Lease, primary: Specialist.ModelIdentity, ownerExited: boolean) {
    if (!ownerExited) throw Error("Controller recovery requires positive owner-death evidence")
    const status = await this.options.client.status()
    if (status.phase === "qwen-ready" && !status.owner && status.generation === lease.generation) return
    await this.owned(lease)
    await this.options.journal.record(lease.job, "RECOVERING")
    // The deployed daemon independently verifies systemd MainPID/start identity and API revision fencing.
    await this.options.client.call("recover", { job: this.options.controllerJob, generation: lease.generation })
    if (!(await this.validatePrimary(lease, primary))) throw Error("RECOVERY_REQUIRED: primary validation failed")
  }
}
