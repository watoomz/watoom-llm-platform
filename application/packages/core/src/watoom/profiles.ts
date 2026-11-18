export * as Profiles from "./profiles.js"

import { createHash } from "node:crypto"
import manifests from "./profiles.json"

export type Capability = {
  id: string
  tools: string[]
  dependencies: string[]
  permission: "allow" | "ask"
  optional: boolean
}
export type Manifest = { id: string; version: string; extends: string[]; capabilities: string[]; skills: string[] }
export type Resolution = {
  version: 1
  selected: string[]
  components: string[]
  disabled: string[]
  statuses: ReturnType<typeof availability>
  profiles: { id: string; version: string }[]
  capabilities: Capability[]
  skills: string[]
  unavailable: { id: string; dependencies: string[]; optional: boolean }[]
  sha256: string
}
export const catalog = manifests as { profiles: Manifest[]; capabilities: Capability[] }

/** Metadata only. Skill instructions remain in their lazy native SKILL.md packages. */
export function resolve(ids: readonly string[], available: readonly string[], components: readonly string[] = [], disabled: readonly string[] = []): Resolution {
  if (!ids.length || ids.length > 7 || ids.some((id) => !catalog.profiles.some((p) => p.id === id)))
    throw Error("unknown or empty profile selection")
  if ([...components, ...disabled].some((id) => !catalog.capabilities.some((capability) => capability.id === id && capability.optional))) throw Error("Only known optional components can be changed")
  const chosen = new Map<string, Manifest>()
  const visiting = new Set<string>()
  const visit = (id: string) => {
    if (visiting.has(id)) throw Error("profile dependency cycle")
    if (chosen.has(id)) return
    const manifest = catalog.profiles.find((p) => p.id === id)
    if (!manifest) throw Error("unknown profile dependency")
    visiting.add(id)
    manifest.extends.forEach(visit)
    visiting.delete(id)
    chosen.set(id, manifest)
  }
  [...new Set(ids)].sort().forEach(visit)
  const profiles = [...chosen.values()].sort((a, b) => a.id.localeCompare(b.id))
  const capabilities = [...new Set([...profiles.flatMap((p) => p.capabilities), ...components])].sort().map((id) => {
    const capability = catalog.capabilities.find((c) => c.id === id)
    if (!capability) throw Error("unknown profile capability")
    return capability
  }).filter((capability) => !disabled.includes(capability.id))
  const unavailable = capabilities.flatMap((c) => {
    const dependencies = c.dependencies.filter((d) => !available.includes(d)).sort()
    return dependencies.length ? [{ id: c.id, dependencies, optional: c.optional }] : []
  })
  const body = {
    version: 1 as const,
    selected: [...new Set(ids)].sort(),
    components: [...new Set(components)].sort(),
    disabled: [...new Set(disabled)].sort(),
    statuses: availability(available),
    profiles: profiles.map((p) => ({ id: p.id, version: p.version })),
    capabilities: capabilities.filter((c) => !unavailable.some((u) => u.id === c.id)),
    skills: [...new Set(profiles.flatMap((p) => p.skills))].sort(),
    unavailable,
  }
  return { ...body, sha256: createHash("sha256").update(JSON.stringify(body)).digest("hex") }
}

export function permissions(resolution: Resolution) {
  return [
    { action: "*", resource: "*", effect: "deny" as const },
    ...resolution.capabilities.flatMap((c) => c.tools.map((action) => ({ action, resource: "*", effect: c.permission }))),
    { action: "skill", resource: "watoom-*", effect: "allow" as const },
  ]
}

export function availability(available: readonly string[]) {
  return catalog.capabilities.map((capability) => {
    const missing = capability.dependencies.filter((dependency) => !available.includes(dependency))
    const status: "READY" | "REQUIRES_CONFIGURATION" | "UNAVAILABLE" | "EXPERIMENTAL" = ["spar3d", "sf3d", "hunyuan3d"].includes(capability.id) ? "EXPERIMENTAL" : !missing.length ? "READY" : ["specialist-registry", "vision-3d-inspector", "procedural-generators"].includes(capability.id) ? "REQUIRES_CONFIGURATION" : "UNAVAILABLE"
    return { id: capability.id, status, missing }
  })
}
