export * as SkillReview from "./skill-review.js"
import fs from "node:fs/promises"
import path from "node:path"
import { createHash } from "node:crypto"
import { constants } from "node:fs"
import { SkillFile } from "../config/plugin/skill-file.js"
import { SkillArtifact } from "./skill-artifact.js"

export const digest = (value: string | Buffer) => createHash("sha256").update(value).digest("hex")
export const versionRoot = (root: string, id: string, bundle: string) =>
  path.join(root, ".versions", digest(id), bundle)
export type Row = {
  id: string
  repo: string
  path: string
  sha256: string
  commit_sha: string
  validation: string
  risk?: string
  raw?: string
}
export async function inspect(root: string, row: Row) {
  if (
    !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(row.repo) ||
    !/^[A-Za-z0-9_./-]+$/.test(row.path) ||
    row.path.split("/").some((part) => !part || part === "." || part === "..")
  )
    throw Error("Unsafe source identity")
  if ((await fs.realpath(root)) !== path.resolve(root)) throw Error("Symlink collection root")
  const folder = path.join(root, "github__" + row.repo.replace("/", "__"), row.path)
  let check = root
  for (const part of path.relative(root, folder).split(path.sep)) {
    check = path.join(check, part)
    const stat = await fs.lstat(check)
    if (!stat.isDirectory() || stat.isSymbolicLink()) throw Error("Unsafe source directory")
  }
  const files = new Map<string, Buffer>()
  const budget = { nodes: 0, bytes: 0 }
  const walk = async (directory: string) => {
    for (const name of (await fs.readdir(directory)).sort()) {
      if (++budget.nodes > 128 || !/^[A-Za-z0-9_.-]+$/.test(name) || name === ".git") throw Error("Source tree bounds")
      const file = path.join(directory, name)
      const stat = await fs.lstat(file)
      if (stat.isSymbolicLink()) throw Error("Symlink source file")
      if (stat.isDirectory()) {
        await walk(file)
        continue
      }
      if (!stat.isFile() || stat.size > 1024 * 1024 || (budget.bytes += stat.size) > 8 * 1024 * 1024)
        throw Error("Source size bounds")
      const handle = await fs.open(file, constants.O_RDONLY | constants.O_NOFOLLOW)
      try {
        const before = await handle.stat()
        if (before.ino !== stat.ino || before.dev !== stat.dev) throw Error("Source changed")
        const data = Buffer.alloc(stat.size + 1)
        const read = await handle.read(data, 0, data.length, 0)
        const after = await handle.stat()
        if (read.bytesRead !== stat.size || after.mtimeMs !== before.mtimeMs) throw Error("Source changed")
        files.set(path.relative(folder, file).split(path.sep).join("/"), data.subarray(0, read.bytesRead))
      } finally {
        await handle.close()
      }
    }
  }
  await walk(folder)
  const acquisition = path.join(root, "github__" + row.repo.replace("/", "__"), ".acquisition.json")
  const sourceEvidence = await fs.lstat(acquisition).catch((error) => {
    if (error.code === "ENOENT") return undefined
    throw error
  })
  if (!sourceEvidence && !row.repo.startsWith("owned/")) throw Error("Retained acquisition provenance missing")
  if (sourceEvidence) {
    if (!sourceEvidence.isFile() || sourceEvidence.isSymbolicLink() || sourceEvidence.size > 2 * 1024 * 1024)
      throw Error("Unsafe acquisition evidence")
    const handle = await fs.open(acquisition, constants.O_RDONLY | constants.O_NOFOLLOW)
    const evidence: unknown = await (async () => {
      try {
        const buffer = Buffer.alloc(sourceEvidence.size + 1)
        const read = await handle.read(buffer, 0, buffer.length, 0)
        if (read.bytesRead !== sourceEvidence.size || (await handle.stat()).size !== sourceEvidence.size)
          throw Error("Acquisition evidence changed")
        return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(buffer.subarray(0, read.bytesRead)))
      } finally {
        await handle.close()
      }
    })()
    if (!evidence || typeof evidence !== "object" || Array.isArray(evidence))
      throw Error("Invalid acquisition evidence")
    const source = evidence as { repo?: unknown; commit?: unknown; files?: unknown }
    if (
      source.repo !== row.repo ||
      source.commit !== row.commit_sha ||
      !Array.isArray(source.files) ||
      source.files.length > 50000
    )
      throw Error("Source revision provenance mismatch")
    const hashes = new Map(
      source.files.map((file: unknown) => {
        if (!file || typeof file !== "object" || Array.isArray(file)) throw Error("Invalid acquisition file")
        const item = file as { path?: unknown; sha256?: unknown }
        if (typeof item.path !== "string" || typeof item.sha256 !== "string")
          throw Error("Invalid acquisition file pin")
        return [item.path, item.sha256]
      }),
    )
    for (const [name, data] of files) {
      if (hashes.get(row.path + "/" + name) !== digest(data))
        throw Error("Source companion differs from retained acquisition")
    }
  }
  const text = files.get("SKILL.md")
  if (!text || text.length > 65536 || digest(text) !== row.sha256) throw Error("Missing, oversized or changed SKILL.md")
  const instructions = new TextDecoder("utf-8", { fatal: true }).decode(text)
  const parsed = SkillFile.parse(path.dirname(folder), path.join(folder, "SKILL.md"), instructions)
  if (parsed._tag !== "Parsed") throw Error("Native SKILL.md validation failed")
  const declared: unknown = files.has("watoom-skill.json")
    ? JSON.parse(files.get("watoom-skill.json")!.toString("utf8"))
    : { version: 1, native_tools: [] }
  if (
    !declared ||
    typeof declared !== "object" ||
    Array.isArray(declared) ||
    Object.keys(declared).sort().join("|") !== "native_tools|version"
  )
    throw Error("Invalid dependency manifest")
  const manifest = declared as { version: unknown; native_tools: unknown }
  if (
    manifest.version !== 1 ||
    !Array.isArray(manifest.native_tools) ||
    manifest.native_tools.length > 32 ||
    !manifest.native_tools.every((tool) => typeof tool === "string" && /^[A-Za-z0-9_-]{1,128}$/.test(tool))
  )
    throw Error("Invalid native dependencies")
  const tools = manifest.native_tools as string[]
  if (!files.has("watoom-skill.json")) files.set("watoom-skill.json", Buffer.from(JSON.stringify(declared)))
  const entries = [...files]
    .map(([name, data]) => [name, digest(data)])
    .sort((a, b) => a[0]!.localeCompare(b[0]!, "en"))
  // Use the native verifier's byte ordering, independent of filesystem locale.
  entries.sort((a, b) => (a[0]! < b[0]! ? -1 : a[0]! > b[0]! ? 1 : 0))
  const bundleSha256 = digest(JSON.stringify(entries))
  const executable = [...files.keys()].filter((name) => /\.(sh|py|js|ts|exe|so|dll|wasm|bat|ps1)$/i.test(name))
  // Script companions are reviewed data, never auto-loaded tools. Native modules
  // and binaries still require a separate integration. Runtime commands retain
  // the caller's normal shell/tool permission checks.
  const native = executable.filter((name) => /\.(exe|so|dll|wasm)$/i.test(name))
  const forbidden = [
    [
      /ignore (all |any |previous |prior )*(system|instructions|policy)|override.{0,30}system (prompt|policy)/i,
      "system-policy-override",
    ],
    [
      /(exfiltrat|steal|upload|send).{0,100}(secret|password|credential|api.key|private.key)/is,
      "credential-extraction",
    ],
    [/curl.{0,100}\|\s*(ba)?sh|wget.{0,100}\|\s*(ba)?sh|rm\s+-rf\s+\/(?:\s|$)/is, "unsafe-command"],
  ]
    .filter(([pattern]) => (pattern as RegExp).test(instructions))
    .map(([, label]) => String(label))
  const recordedRisks: unknown = row.risk ? JSON.parse(row.risk) : []
  if (
    !Array.isArray(recordedRisks) ||
    recordedRisks.length > 32 ||
    !recordedRisks.every((value) => typeof value === "string" && value.length <= 128)
  )
    throw Error("Invalid retained risk metadata")
  const risks = [
    ...(recordedRisks as string[]),
    ...(native.length ? ["executable-components-require-separate-integration"] : []),
    ...(executable.length > native.length ? ["bundled-scripts-require-runtime-permission"] : []),
    ...forbidden,
    ...(/\b(sudo|privileged|CAP_SYS_ADMIN|chmod\s+777)\b/i.test(instructions) ? ["elevated-operations"] : []),
  ]
  return {
    instructions,
    tools,
    files,
    bundleSha256,
    risks,
    executable,
    valid: row.validation === "valid" && !forbidden.length && !native.length,
  }
}
export async function stage(root: string, row: Row, review: Awaited<ReturnType<typeof inspect>>) {
  if ((await fs.realpath(root)) !== path.resolve(root)) throw Error("Unsafe artifact root")
  for (const directory of [path.join(root, ".versions"), path.join(root, ".versions", digest(row.id))]) {
    await fs.mkdir(directory, { recursive: true, mode: 0o750 })
    if ((await fs.realpath(directory)) !== directory) throw Error("Symlink artifact directory")
  }
  const target = versionRoot(root, row.id, review.bundleSha256)
  const folder = path.join(target, "github__" + row.repo.replace("/", "__"), row.path)
  const exists = await fs.stat(target).then(
    () => true,
    () => false,
  )
  if (!exists) {
    const temporary = target + ".tmp-" + crypto.randomUUID()
    const destination = path.join(temporary, "github__" + row.repo.replace("/", "__"), row.path)
    await fs.mkdir(destination, { recursive: true, mode: 0o750 })
    for (const [name, data] of review.files) {
      await fs.mkdir(path.dirname(path.join(destination, name)), { recursive: true, mode: 0o750 })
      await fs.writeFile(path.join(destination, name), data, { flag: "wx", mode: 0o640 })
    }
    await fs.rename(temporary, target)
  }
  return folder
}
export function verify(root: string, row: Row, bundle: string, tools: readonly string[]) {
  return SkillArtifact.resolve(
    root,
    { ...row, commit: row.commit_sha, bundleSha256: bundle },
    [{ action: "skill", resource: row.id, effect: "allow" }],
    new Set(tools),
  )
}
