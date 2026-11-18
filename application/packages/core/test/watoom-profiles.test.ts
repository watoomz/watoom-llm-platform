import { expect, test } from "bun:test"
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"
import { Profiles } from "@opencode/core/watoom/profiles"
import { ProfileInstall } from "@opencode/core/watoom/install"
import { Schema } from "effect"
import { Config } from "@opencode/schema/config"

test("all seven profiles resolve deterministically with optional dependencies absent", () => {
  expect(Profiles.catalog.profiles).toHaveLength(7)
  for (const profile of Profiles.catalog.profiles) {
    const resolution = Profiles.resolve([profile.id], [])
    expect(resolution.capabilities.some((c) => c.id === "native-core")).toBe(true)
    expect(resolution.unavailable.every((c) => c.optional)).toBe(true)
  }
  expect(Profiles.resolve(["full", "minimal"], [])).toEqual(Profiles.resolve(["minimal", "full"], []))
  expect(Profiles.resolve(["minimal"], []).capabilities.some((c) => c.id.includes("gpu"))).toBe(false)
  expect(Profiles.resolve(["homelab"], ["kubectl"]).capabilities.find((c) => c.id === "homelab-inspection")?.permission).toBe("ask")
  expect(() => Profiles.resolve(["community"], [])).toThrow()
})
test("native install, profile change and guarded rollback preserve JSONC and user settings", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "watoom-profile-"))
  try {
    const configPath = path.join(root, "opencode.jsonc")
    const original = '// user comment\n{"username":"retained", "skills": ["/custom"], "agents":{"own":{"description":"user"}}}\n'
    await writeFile(configPath, original)
    const dry = await ProfileInstall.install({ root, profiles: ["full"], available: [], dryRun: true })
    expect(dry.status).toBe("DRY_RUN")
    expect(await readFile(configPath, "utf8")).toBe(original)
    const first = await ProfileInstall.install({ root, profiles: ["developer"], available: [] })
    expect(first.status).toBe("INSTALLED")
    const { parse } = await import("jsonc-parser")
    const installed = await readFile(configPath, "utf8")
    expect(installed).toContain("// user comment")
    const config = Schema.decodeUnknownSync(Config.Info)(parse(installed))
    expect(config.username).toBe("retained")
    expect(config.skills?.[0]).toBe("/custom")
    expect(config.agents?.own.description).toBe("user")
    expect(config.agents?.["watoom-profile"].permissions?.find((p) => p.action === "shell")?.effect).toBe("ask")
    const second = await ProfileInstall.install({ root, profiles: ["minimal"], available: [] })
    if (!("transaction" in second)) throw Error("missing installation transaction")
    expect(parse(await readFile(configPath, "utf8")).skills).toHaveLength(2)
    await ProfileInstall.rollback(root, second.transaction)
    expect(await readFile(configPath, "utf8")).toBe(installed)
    if (!("transaction" in first)) throw Error("missing installation transaction")
    await writeFile(configPath, installed + "// later user edit\n")
    await expect(ProfileInstall.rollback(root, first.transaction)).rejects.toThrow("configuration changed")
    await writeFile(configPath, installed)
    await ProfileInstall.rollback(root, first.transaction)
    expect(await readFile(configPath, "utf8")).toBe(original)
  } finally { await rm(root, { recursive: true, force: true }) }
})

test("optional component preview, apply, export, reload and rollback share deterministic state", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "watoom-components-"))
  try {
    const original = '// preserved comment\n{"username":"retained"}\n'
    await writeFile(path.join(root, "opencode.jsonc"), original)
    const input = { root, profiles: ["minimal"], components: ["blender"], disabled: ["godot"], available: ["blender"] }
    const preview = await ProfileInstall.install({ ...input, dryRun: true })
    expect(preview.components).toEqual(["blender"])
    expect(preview.capabilities.some((capability) => capability.id === "blender")).toBe(true)
    expect(await readFile(path.join(root, "opencode.jsonc"), "utf8")).toBe(original)
    const applied = await ProfileInstall.install(input)
    if (!("transaction" in applied)) throw Error("missing apply transaction")
    const persisted = await ProfileInstall.selection(root)
    expect(persisted.components).toEqual(["blender"])
    expect(persisted.disabled).toEqual(["godot"])
    expect(persisted.transaction).toBe(applied.transaction!)
    const exported = await ProfileInstall.exportConfiguration(root)
    expect(exported).toEqual({ version: 1, selected: ["minimal"], components: ["blender"], disabled: ["godot"] })
    expect(await ProfileInstall.exportConfiguration(root)).toEqual(exported)
    const changed = await ProfileInstall.install({ root, profiles: ["minimal"], components: [], disabled: [], available: [] })
    if (!("transaction" in changed)) throw Error("missing change transaction")
    expect((await ProfileInstall.selection(root)).components).toEqual([])
    await ProfileInstall.rollback(root, changed.transaction!)
    expect((await ProfileInstall.selection(root)).components).toEqual(["blender"])
    const beforeFailure = await readFile(path.join(root, "opencode.jsonc"), "utf8")
    await expect(ProfileInstall.install({ ...input, disabled: ["native-core"] })).rejects.toThrow("optional")
    expect(await readFile(path.join(root, "opencode.jsonc"), "utf8")).toBe(beforeFailure)
    expect(Profiles.catalog.capabilities.some((capability) => capability.id === "meshy")).toBe(false)
    expect(Profiles.availability([]).find((capability) => capability.id === "spar3d")?.status).toBe("EXPERIMENTAL")
    expect(Profiles.availability([]).find((capability) => capability.id === "procedural-generators")?.status).toBe("REQUIRES_CONFIGURATION")
  } finally { await rm(root, { recursive: true, force: true }) }
})

test("availability counts configured specialists and declared routes, not only PATH", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "watoom-routes-"))
  try {
    await writeFile(path.join(root, "opencode.json"), JSON.stringify({ watoom_specialists: { entries: [{ descriptor: { id: "local-toolkit", capabilities: ["3d.inspect", "3d.generate"] } }] } }))
    await writeFile(path.join(root, "watoom-routes.json"), JSON.stringify({ routes: ["unreal-editor", "avian-approved-compatible-runtime", "not-a-dependency"] }))
    const found = await ProfileInstall.available(root)
    for (const name of ["specialist-adapter", "vision-3d-adapter", "procedural-adapter", "unreal-editor", "avian-approved-compatible-runtime"]) expect(found).toContain(name)
    expect(found).not.toContain("not-a-dependency")
    const statuses = Profiles.availability(found)
    for (const id of ["specialist-registry", "vision-3d-inspector", "procedural-generators", "unreal", "avian"]) expect(statuses.find((s) => s.id === id)?.status).toBe("READY")
    expect(statuses.find((s) => s.id === "spar3d")?.status).toBe("EXPERIMENTAL")
    expect(await ProfileInstall.available(path.join(root, "missing"))).not.toContain("specialist-adapter")
  } finally { await rm(root, { recursive: true, force: true }) }
})
