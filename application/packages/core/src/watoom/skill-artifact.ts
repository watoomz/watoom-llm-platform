export * as SkillArtifact from "./skill-artifact.js"

/** Read-only, on-demand artifact verification. Reuses native SkillFile; never registers globally. */
import fs from "node:fs/promises"
import { constants } from "node:fs"
import path from "node:path"
import { createHash } from "node:crypto"
import { Effect } from "effect"
import { SkillFile } from "../config/plugin/skill-file.js"
import { Permission } from "../permission.js"
import { Skill } from "../skill.js"

export type Reference = { id: string; repo: string; path: string; sha256: string; commit: string; bundleSha256: string }
export function resolve(
  root: string,
  reference: Reference,
  permissions: Permission.Ruleset,
  capabilities: ReadonlySet<string> = new Set(),
) {
  return Effect.tryPromise(async () => {
    if (Permission.evaluate("skill", reference.id, permissions).effect !== "allow")
      throw Error("skill permission denied or approval required")
    if (
      !/^[a-f0-9]{64}$/.test(reference.sha256) ||
      !/^[a-f0-9]{64}$/.test(reference.bundleSha256) ||
      !/^[a-f0-9]{40}$/.test(reference.commit)
    )
      throw Error("invalid pinned artifact identity")
    if (
      !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(reference.repo) ||
      !/^[A-Za-z0-9_./-]+$/.test(reference.path) ||
      reference.path.split("/").some((p) => !p || p === "." || p === "..")
    )
      throw Error("invalid artifact path")
    const version = path.join(
      root,
      ".versions",
      createHash("sha256").update(reference.id).digest("hex"),
      reference.bundleSha256,
    )
    const versionExists = await fs.lstat(version).then(
      () => true,
      (error) => {
        if (error.code === "ENOENT") return false
        throw error
      },
    )
    const vault = path.resolve(versionExists ? version : root)
    if ((await fs.realpath(vault)) !== vault) throw Error("symlink artifact root")
    const base = path.join(vault, "github__" + reference.repo.replace("/", "__"))
    if ((await fs.lstat(base)).isSymbolicLink()) throw Error("symlink source")
    if (
      await fs.lstat(path.join(base, ".acquisition.json")).then(
        () => true,
        (e) => {
          if (e.code === "ENOENT") return false
          throw e
        },
      )
    )
      throw Error("unreviewed acquired source requires promotion")
    const folder = path.join(base, reference.path)
    let directory = base
    for (const part of reference.path.split("/")) {
      directory = path.join(directory, part)
      const stat = await fs.lstat(directory)
      if (stat.isSymbolicLink() || !stat.isDirectory()) throw Error("unsafe artifact directory")
    }
    if ((await fs.realpath(folder)) !== folder) throw Error("artifact path changed")
    const entries: [string, string][] = []
    const contents = new Map<string, Buffer>()
    const pending = [folder]
    const total = { bytes: 0, nodes: 0 }
    while (pending.length) {
      const directory = pending.pop()!
      for (const name of await fs.readdir(directory)) {
        if (++total.nodes > 128 || !/^[A-Za-z0-9_.-]+$/.test(name) || name === ".git" || name === "__pycache__")
          throw Error("artifact tree bounds or hidden cache")
        const file = path.join(directory, name)
        const stat = await fs.lstat(file)
        if (stat.isSymbolicLink()) throw Error("symlink companion file")
        if (stat.isDirectory()) {
          pending.push(file)
          continue
        }
        if (!stat.isFile() || stat.size > 1024 * 1024 || (total.bytes += stat.size) > 8 * 1024 * 1024)
          throw Error("artifact file bounds")
        const handle = await fs.open(file, constants.O_RDONLY | constants.O_NOFOLLOW)
        const data = await (async () => {
          try {
            const before = await handle.stat()
            if (!before.isFile() || before.size !== stat.size) throw Error("artifact changed before read")
            const buffer = Buffer.alloc(stat.size + 1)
            const read = await handle.read(buffer, 0, buffer.length, 0)
            const after = await handle.stat()
            if (read.bytesRead !== stat.size || before.mtimeMs !== after.mtimeMs || before.size !== after.size)
              throw Error("artifact changed while reading")
            return buffer.subarray(0, read.bytesRead)
          } finally {
            await handle.close()
          }
        })()
        const relative = path.relative(folder, file).split(path.sep).join("/")
        entries.push([relative, createHash("sha256").update(data).digest("hex")])
        contents.set(relative, data)
      }
    }
    entries.sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0))
    if (createHash("sha256").update(JSON.stringify(entries)).digest("hex") !== reference.bundleSha256)
      throw Error("approved companion bundle changed")
    const markdown = contents.get("SKILL.md")
    if (
      !markdown ||
      markdown.length > 64 * 1024 ||
      createHash("sha256").update(markdown).digest("hex") !== reference.sha256
    )
      throw Error("skill content changed or missing")
    const manifest = contents.get("watoom-skill.json")
    if (!manifest || manifest.length > 8192) throw Error("reviewed dependency manifest missing or oversized")
    const dependencies: unknown = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(manifest))
    if (
      !dependencies ||
      typeof dependencies !== "object" ||
      Array.isArray(dependencies) ||
      Object.keys(dependencies).sort().join("|") !== "native_tools|version"
    )
      throw Error("invalid dependency manifest")
    const declared = dependencies as { version: unknown; native_tools: unknown }
    if (
      declared.version !== 1 ||
      !Array.isArray(declared.native_tools) ||
      declared.native_tools.length > 32 ||
      !declared.native_tools.every((tool) => typeof tool === "string" && /^[A-Za-z0-9_-]{1,128}$/.test(tool))
    )
      throw Error("invalid dependency manifest")
    for (const tool of declared.native_tools)
      if (!capabilities.has(tool)) throw Error("required native tool unavailable or denied: " + tool)
    const parsed = SkillFile.parse(
      path.dirname(folder),
      path.join(folder, "SKILL.md"),
      new TextDecoder("utf-8", { fatal: true }).decode(markdown),
    )
    if (parsed._tag !== "Parsed") throw Error("native skill metadata invalid")
    return {
      ...parsed.skill,
      id: Skill.ID.make(reference.id),
      autoinvoke: false,
      verifiedFiles: entries.filter(([file]) => file !== "SKILL.md").map(([file]) => path.join(folder, file)),
    } satisfies Skill.VerifiedInfo
  })
}
