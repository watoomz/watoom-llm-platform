export * as SpecialistBackends from "./specialist-backends.js"
import { readFile, realpath, lstat } from "node:fs/promises"
import path from "node:path"
import { createHash } from "node:crypto"
import { Specialist } from "./specialist.js"
import { localCatalog, validateReceipt } from "./toolkit-3d.js"
import * as Creative from "./creative-contract.js"
import type { SpecialistConfig } from "@opencode/schema/specialists"
export function localURL(value: string) {
  const url = new URL(value)
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.hash || url.search || !(url.hostname === "localhost" || url.hostname === "127.0.0.1" || url.hostname === "[::1]" || /^10\./.test(url.hostname) || /^192\.168\./.test(url.hostname) || /^172\.(1[6-9]|2[0-9]|3[01])\./.test(url.hostname) || url.hostname.endsWith(".svc.cluster.local"))) throw Error("Only explicitly configured local/self-hosted specialist endpoints are allowed")
  return url
}
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw Error("Specialist object required")
  return value as Record<string, unknown>
}
export function backend(entry: SpecialistConfig.Entry): Specialist.Backend & { discover: () => Promise<unknown> } {
  const url = localURL(entry.url)
  if (!path.isAbsolute(entry.artifactRoot)) throw Error("Explicit local artifact root required")
  if (entry.tokenEnv && !/^[A-Z][A-Z0-9_]{1,127}$/.test(entry.tokenEnv)) throw Error("Invalid protected credential reference")
  const credential = entry.tokenEnv ? process.env[entry.tokenEnv] : undefined
  const request = async (route: string, payload?: unknown, signal?: AbortSignal) => {
    if (entry.tokenEnv && !credential) throw Error("Specialist requires configuration")
    const response = await fetch(new URL(route, url), { method: payload === undefined ? "GET" : "POST", headers: { "content-type": "application/json", ...(credential ? { authorization: "Bearer " + credential } : {}) }, body: payload === undefined ? undefined : JSON.stringify(payload), signal, redirect: "error" })
    if (!response.ok) throw Error("Local specialist HTTP " + response.status)
    const data = await response.text()
    if (Buffer.byteLength(data) > 1048576) throw Error("Specialist response exceeds limit")
    return JSON.parse(data)
  }
  return {
    async discover() {
      const value = await request(entry.backend === "toolkit-3d" ? "/api/catalog" : "/capabilities", undefined, AbortSignal.timeout(3000))
      if (entry.backend === "toolkit-3d") return localCatalog(value)
      if (object(value).contract !== "watoom-specialist/v1") throw Error("Unverified local specialist contract")
      return value
    },
    validateInput(input, capability) {
      const payload = object(input)
      if (entry.backend !== "toolkit-3d") return
      if (Creative.operations[capability ?? ""]) return Creative.validate(payload, capability!)
      const task = ({ "3d.generate": "3d-generate", "3d.inspect": "3d-inspect", "3d.repair": "3d-repair" } as Record<string, string>)[capability ?? ""]
      if (!task || payload.task !== task) throw Error("Capability and typed Toolkit task mismatch")
      if (task === "3d-generate" && !["asset-assistant.avian", "asset-assistant.quadruped", "asset-assistant.human", "watoom.tree", "watoom.terrain", "watoom.building", "watoom.rock"].includes(String(payload.generator))) throw Error("Unregistered local generator")
      if (Object.keys(payload).some((key) => !["task", "generator", "parameters", "seed", "style", "path", "timeout"].includes(key))) throw Error("Unsupported Toolkit input")
      if ("path" in payload && (typeof payload.path !== "string" || payload.path.startsWith("/") || payload.path.includes("\\") || payload.path.split("/").some((part) => !part || part === "." || part === ".."))) throw Error("Unsafe Toolkit input path")
    },
    async execute(operationID, payload, signal) {
      const input = object(payload)
      const creative = ["asset-index", "asset-search", "3d-creative"].includes(String(input.task))
      const value = await request(entry.backend === "toolkit-3d" ? "/api/jobs" : "/execute", entry.backend === "toolkit-3d" ? (creative ? { ...input, operation_id: operationID } : payload) : { contract: "watoom-specialist/v1", operationID, input: payload }, signal).catch(async (error) => {
        if (entry.backend === "toolkit-3d" && signal.aborted && String(input.task).startsWith("3d-")) {
          await request("/api/jobs/cancel", { operation_id: operationID }, AbortSignal.timeout(5000)).catch(() => undefined)
        }
        throw error
      })
      if (entry.backend !== "toolkit-3d") {
        const result = object(value)
        if (result.contract !== "watoom-specialist/v1" || result.operationID !== operationID) throw Error("Specialist operation receipt mismatch")
        // The native dispatcher validates the complete outcome before persistence.
        return object(result.outcome) as unknown as Specialist.Outcome
      }
      const receipt = validateReceipt(value, String(input.task), creative ? { contract: "watoom-creative/v1", expected: Creative.outputs(input) } : undefined)
      if (creative && receipt.operation_id !== operationID) throw Error("Creative native operation receipt mismatch")
      const published = object(receipt.published)
      // Full receipt and manifest preserve every view/hash. Keep the native
      // dispatcher's bounded result while retaining animation frames and maps.
      const files = (published.files as { path: string; sha256: string; bytes: number }[]).filter(file => !creative || !["front.png","back.png","left.png","right.png","top.png"].includes(file.path))
      const result = input.task === "asset-search" || input.task === "asset-index" ? object(receipt.result) : undefined
      const compact = result && Array.isArray(result.results) ? { results: result.results.map(value => { const row=object(value); return { id:row.id,path:row.path,format:row.format } }) } : result
      return { summary: "Verified local Toolkit " + input.task + " job " + receipt.id + (input.task === "asset-search" || input.task === "asset-index" ? " result " + JSON.stringify(compact).slice(0, 1700) : ""), artifacts: files.map((file) => ({ reference: "artifact:" + published.path + "/" + file.path, sha256: file.sha256, bytes: file.bytes })) }
    },
    async verifyArtifacts(outcome) {
      const root = await realpath(entry.artifactRoot)
      for (const artifact of outcome.artifacts) {
        if (!artifact.reference.startsWith("artifact:")) return false
        const file = path.resolve(root, artifact.reference.slice(9))
        if (!file.startsWith(root + path.sep) || await realpath(file) !== file) return false
        const stat = await lstat(file)
        if (!stat.isFile() || stat.isSymbolicLink() || stat.size !== artifact.bytes || stat.size < 1 || stat.size > 67108864) return false
        if (createHash("sha256").update(await readFile(file)).digest("hex") !== artifact.sha256) return false
      }
      return outcome.artifacts.length > 0
    },
  }
}
export function registry(entries: readonly SpecialistConfig.Entry[]) {
  const registry = new Specialist.Registry()
  const discoveries: { id: string; discover: () => Promise<unknown> }[] = []
  for (const entry of entries) {
    const driver = backend(entry)
    registry.register(entry.descriptor as unknown as Specialist.Descriptor, driver)
    discoveries.push({ id: (entry.descriptor as unknown as Specialist.Descriptor).id, discover: driver.discover })
  }
  return { registry, discoveries }
}
