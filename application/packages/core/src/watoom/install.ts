export * as ProfileInstall from "./install.js"

import { createHash, randomUUID } from "node:crypto"
import { mkdir, open, readFile, rename, lstat } from "node:fs/promises"
import path from "node:path"
import { applyEdits, modify, parse, type ParseError } from "jsonc-parser"
import { Profiles } from "./profiles.js"

const hash = (value: string) => createHash("sha256").update(value).digest("hex")
const missing = (error: NodeJS.ErrnoException) => { if (error.code === "ENOENT") return "{}\n"; throw error }
async function atomic(file: string, content: string) {
  const temp = file + "." + randomUUID() + ".tmp"
  const handle = await open(temp, "wx", 0o600)
  try { await handle.writeFile(content); await handle.sync() } finally { await handle.close() }
  await rename(temp, file)
}

export async function plan(input: { root: string; profiles: string[]; available: string[]; components?: string[]; disabled?: string[] }) {
  const resolution = Profiles.resolve(input.profiles, input.available, input.components, input.disabled)
  if (resolution.unavailable.some((x) => !x.optional)) throw Error("required profile dependency unavailable")
  const configPath = path.join(path.resolve(input.root), "opencode.jsonc")
  const before = await readFile(configPath, "utf8").catch(missing)
  const errors: ParseError[] = []
  const config: unknown = parse(before, errors, { allowTrailingComma: true })
  if (errors.length || !config || typeof config !== "object" || Array.isArray(config)) throw Error("invalid native configuration")
  const release = path.join(path.resolve(input.root), ".watoom", "profiles", resolution.sha256)
  const agent = { description: "WatooM profile-managed development agent", mode: "primary", permissions: Profiles.permissions(resolution) }
  const skills = "skills" in config ? config.skills : []
  if (!Array.isArray(skills) || skills.some((x) => typeof x !== "string")) throw Error("invalid native skills configuration")
  const managedRoot = path.join(path.resolve(input.root), ".watoom", "profiles") + path.sep
  const updated = [
    { keys: ["agents", "watoom-profile"], value: agent },
    { keys: ["skills"], value: [...skills.filter((x: string) => !x.startsWith(managedRoot)), path.join(release, "skills")] },
  ].reduce((text, edit) => applyEdits(text, modify(text, edit.keys, edit.value, { formattingOptions: { tabSize: 2, insertSpaces: true } })), before)
  return { resolution, configPath, release, before, after: updated.endsWith("\n") ? updated : updated + "\n" }
}

/** The root is the explicit native config scope (project .opencode or user config dir).
 * Immutable release bundles and exact pre-change config snapshots support guarded rollback. */
export async function install(input: { root: string; profiles: string[]; available: string[]; components?: string[]; disabled?: string[]; dryRun?: boolean }) {
  const change = await plan(input)
  if (input.dryRun) return { ...change.resolution, status: "DRY_RUN", configPath: change.configPath }
  await mkdir(path.dirname(change.configPath), { recursive: true })
  const symlink = await lstat(change.configPath).catch((e: NodeJS.ErrnoException) => { if (e.code === "ENOENT") return undefined; throw e })
  if (symlink?.isSymbolicLink()) throw Error("native config symlink cannot be replaced")
  const lock = await open(change.configPath + ".watoom-lock", "wx", 0o600)
  try {
    if (await readFile(change.configPath, "utf8").catch(missing) !== change.before) throw Error("native config changed during installation")
    const currentAgent = parse(change.before)?.agents?.["watoom-profile"]
    if (currentAgent && currentAgent.description !== "WatooM profile-managed development agent") throw Error("managed agent name already owned by user")
    await mkdir(path.join(change.release, "skills"), { recursive: true })
    for (const id of change.resolution.skills) {
      const directory = path.join(change.release, "skills", id)
      await mkdir(directory, { recursive: true })
      const source = builtinSkill(id)
      const target = path.join(directory, "SKILL.md")
      const existing = await readFile(target, "utf8").catch((e: NodeJS.ErrnoException) => { if (e.code === "ENOENT") return undefined; throw e })
      if (existing !== undefined && existing !== source) throw Error("installed built-in skill hash mismatch")
      if (existing === undefined) await atomic(target, source)
    }
    const receipt = { version: 1, resolution: change.resolution, before: change.before, afterSha256: hash(change.after),
      skills: change.resolution.skills.map((id) => ({ id, version: "1.0.0", sha256: hash(builtinSkill(id)), trust: "APPROVED_BUILTIN" })) }
    const manifest = JSON.stringify(change.resolution, null, 2) + "\n"
    const manifestPath = path.join(change.release, "manifest.json")
    const existingManifest = await readFile(manifestPath, "utf8").catch((e: NodeJS.ErrnoException) => { if (e.code === "ENOENT") return undefined; throw e })
    if (existingManifest !== undefined && existingManifest !== manifest) throw Error("profile manifest hash mismatch")
    if (existingManifest === undefined) await atomic(manifestPath, manifest)
    const transaction = randomUUID()
    const history = path.join(path.resolve(input.root), ".watoom", "history")
    await mkdir(history, { recursive: true })
    // Journal is synchronized before the single native config commit. Pending journals are inert.
    await atomic(path.join(history, transaction + ".json"), JSON.stringify(receipt, null, 2) + "\n")
    await atomic(path.join(path.resolve(input.root), ".watoom", "last-profile-transaction.json"), JSON.stringify({ transaction, afterSha256: receipt.afterSha256 }))
    await atomic(change.configPath, change.after)
    return { ...change.resolution, status: "INSTALLED", transaction, configPath: change.configPath }
  } finally {
    await lock.close()
    const { unlink } = await import("node:fs/promises")
    await unlink(change.configPath + ".watoom-lock")
  }
}

export async function rollback(root: string, transaction: string) {
  if (!/^[a-f0-9-]{36}$/.test(transaction)) throw Error("invalid rollback transaction")
  const config = path.join(path.resolve(root), "opencode.jsonc")
  const lock = await open(config + ".watoom-lock", "wx", 0o600)
  try {
    const receipt = JSON.parse(await readFile(path.join(root, ".watoom", "history", transaction + ".json"), "utf8"))
    if (receipt.version !== 1 || typeof receipt.before !== "string" || hash(await readFile(config, "utf8")) !== receipt.afterSha256)
      throw Error("rollback refused: configuration changed after installation")
    await atomic(config, receipt.before)
    return { status: "ROLLED_BACK", transaction }
  } finally {
    await lock.close()
    const { unlink } = await import("node:fs/promises")
    await unlink(config + ".watoom-lock")
  }
}

const guidance: Record<string, string> = {
  "watoom-core": "Use native read, glob, grep and edit tools for project navigation. Respect native permissions and session ownership. Keep exact operational state in native session persistence; semantic outcomes belong in AgentMemory when its configured adapter is available. Never claim an unavailable memory adapter delivered data.",
  "watoom-developer": "Inspect the repository and installed runtime before using shell. Run focused build and test commands with explicit runtime bounds. Preserve unrelated changes. Validate output files and hashes before reporting artifact-producing jobs as successful.",
  "watoom-homelab": "Default infrastructure operations to read-only inspection. Inspect installed kubectl, Helm and Ansible interfaces. Changes require explicit authorization and belong in authoritative IaC. Never alter network, firewall, DNS or GPU ownership incidentally.",
  "watoom-ai-cuda": "Inspect model provenance, GGUF metadata and GPU budget through installed tools. Do not download weights or start models without authorization. G3H/G3G owns GPU transitions. Use registered specialists only; an unavailable backend is not implemented execution.",
  "watoom-game-development": "Discover Godot, Blender and Unreal versions before execution. Work on copies. Use CPU Blender with disabled autoexec. Validate export hashes, finite geometry and actual import receipts; subprocess exit alone does not prove successful artifacts.",
  "watoom-3d-generation": "Use only approved available generator adapters. Record generator version, source revision, parameters, seed, export format, hashes and geometry checks. Preserve purchased source assets. Avian and AI models remain optional until their dependency and approval gates pass.",
  "watoom-full": "Select relevant capabilities on demand. Full enables approved built-in guidance and available dependencies. It grants no approval to indexed community skills and no authority for GPU transitions or production deployment.",
}
// Specialist capabilities that satisfy a profile dependency: the route the agent actually uses for it.
const specialistRoutes: Record<string, string> = { "3d.inspect": "vision-3d-adapter", "3d.generate": "procedural-adapter" }

/** Dependency names that are satisfied in this deployment, from three sources:
 * executables on PATH; the configured watoom_specialists (any entry is the specialist adapter, and its capabilities
 * map through specialistRoutes); and routes the server cannot observe itself (external workers, backend generators),
 * declared by the deployment in <root>/watoom-routes.json as {"routes": [...]}. Only known dependency names count. */
export async function available(root?: string) {
  const which = (await import("which")).default
  const names = ["kubectl", "nvidia-smi", "godot", "blender", "unreal-editor"]
  const results = await Promise.all(names.map(async (name) => await which(name, { nothrow: true }) ? name : undefined))
  const found = new Set(results.filter((name): name is string => name !== undefined))
  if (root) {
    const read = async (name: string) => parse(await readFile(path.join(root, name), "utf8").catch(missing)) as Record<string, unknown> | undefined
    for (const name of ["opencode.json", "opencode.jsonc"]) {
      const entries = ((await read(name))?.watoom_specialists as { entries?: unknown } | undefined)?.entries
      if (!Array.isArray(entries)) continue
      for (const entry of entries) {
        const capabilities = (entry as { descriptor?: { capabilities?: unknown } })?.descriptor?.capabilities
        if (!Array.isArray(capabilities)) continue
        found.add("specialist-adapter")
        for (const capability of capabilities) if (typeof capability === "string" && specialistRoutes[capability]) found.add(specialistRoutes[capability])
      }
    }
    const declared = (await read("watoom-routes.json"))?.routes
    const known = new Set(Profiles.catalog.capabilities.flatMap((capability) => capability.dependencies))
    if (Array.isArray(declared)) for (const route of declared) if (typeof route === "string" && known.has(route)) found.add(route)
  }
  return [...found].sort()
}
export async function selection(root: string) {
  const text = await readFile(path.join(root, "opencode.jsonc"), "utf8").catch(missing)
  const config = parse(text)
  const managed = path.join(path.resolve(root), ".watoom", "profiles") + path.sep
  const directory = config?.skills?.find((p: unknown) => typeof p === "string" && p.startsWith(managed))
  if (!directory) return { selected: [] as string[], components: [] as string[], disabled: [] as string[], transaction: "" }
  const manifest = JSON.parse(await readFile(path.join(directory, "..", "manifest.json"), "utf8"))
  const { sha256, ...body } = manifest
  if (hash(JSON.stringify(body)) !== sha256) throw Error("installed profile manifest integrity failure")
  const latest = await readFile(path.join(root, ".watoom", "last-profile-transaction.json"), "utf8").then((value) => JSON.parse(value), () => undefined)
  return { selected: (body.selected ?? body.profiles.map((p: { id: string }) => p.id)) as string[], components: (body.components ?? []) as string[], disabled: (body.disabled ?? []) as string[], transaction: latest?.afterSha256 === hash(text) ? String(latest.transaction) : "" }
}
export function builtinSkill(id: string) {
  if (!guidance[id]) throw Error("unknown built-in skill")
  return `---\nname: ${id}\ndescription: ${id.replaceAll("-", " ")} profile guidance, loaded on demand\n---\n\n${guidance[id]}\n`
}

export async function current(root: string): Promise<string[]> { return (await selection(root)).selected }
export async function exportConfiguration(root: string) {
  const { transaction, ...selectionState } = await selection(root)
  return { version: 1, ...selectionState }
}
