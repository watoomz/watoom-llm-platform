export * as OwnershipStatus from "./ownership-status.js"
import fs from "node:fs/promises"
export type Snapshot = {
  available: boolean
  stale: boolean
  sampledAt: number | null
  phase: string | null
  owner: string | null
  generation: number | null
  uncertain: boolean | null
  activeRequests: number | null
  primary: string | null
}
export async function read(file: string | undefined): Promise<Snapshot> {
  const unavailable: Snapshot = {
    available: false,
    stale: true,
    sampledAt: null,
    phase: null,
    owner: null,
    generation: null,
    uncertain: null,
    activeRequests: null,
    primary: null,
  }
  if (!file) return unavailable
  try {
    const stat = await fs.lstat(file)
    if (!stat.isFile() || stat.isSymbolicLink() || stat.uid !== 0 || (stat.mode & 0o022) !== 0 || stat.size > 8192)
      return unavailable
    const value = JSON.parse(await fs.readFile(file, "utf8"))
    if (
      value.schema !== "watoom.gpu-observation.v1" ||
      !Number.isSafeInteger(value.sampledAt) ||
      value.sampledAt > Date.now() + 5000 ||
      !Number.isSafeInteger(value.generation) ||
      value.generation < 0 ||
      typeof value.phase !== "string" ||
      typeof value.uncertain !== "boolean" ||
      (value.owner !== null && typeof value.owner !== "string")
    )
      return unavailable
    return {
      available: true,
      stale: Date.now() - value.sampledAt > 15000,
      sampledAt: value.sampledAt,
      phase: value.phase,
      owner: value.owner,
      generation: value.generation,
      uncertain: value.uncertain,
      activeRequests: Number.isSafeInteger(value.activeRequests) ? value.activeRequests : null,
      primary: typeof value.primary === "string" ? value.primary : null,
    }
  } catch {
    return unavailable
  }
}
