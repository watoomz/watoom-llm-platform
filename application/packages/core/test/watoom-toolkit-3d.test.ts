import { localCatalog } from "@opencode/core/watoom/toolkit-3d"
import { test, expect } from "bun:test"
import plugin, { validateReceipt } from "@opencode/core/watoom/toolkit-3d"

function receipt(task = "3d-generate") {
  const id = "a".repeat(16)
  const names = ["asset.blend", "asset.glb", "manifest.json", "validation.json", "front.png", "back.png", "left.png", "right.png", "top.png", "perspective.png", ...(task === "3d-repair" ? ["before-validation.json"] : [])]
  const artifacts = names.map((name) => ({ root: "state", path: "jobs/" + id + "/worker/artifacts/" + name, sha256: "b".repeat(64), bytes: 100 }))
  return { id, task, status: "PASS", exit_code: 0, artifacts, verification: { status: "PASS" }, contract: { id: "watoom-3d/v1", available: true, outputs: artifacts.map((a) => ({ root: a.root, path: a.path })) }, published: { root: "assets", path: "generated/watoom-toolkit-3d/v1/" + id, files: names.map((name) => ({ path: name, bytes: 100, sha256: "b".repeat(64) })) } }
}
test("native 3D consumer requires complete verified artifacts and publication", () => {
  expect(validateReceipt(receipt(), "3d-generate").status).toBe("PASS")
  expect(validateReceipt(receipt("3d-repair"), "3d-repair").status).toBe("PASS")
  for (const mutate of [
    (r: ReturnType<typeof receipt>) => { r.artifacts.pop() },
    (r: ReturnType<typeof receipt>) => { r.artifacts[0].path = "jobs/../credential" },
    (r: ReturnType<typeof receipt>) => { r.published.files[0].sha256 = "c".repeat(64) },
    (r: ReturnType<typeof receipt>) => { r.published.files[1] = r.published.files[0] },
    (r: ReturnType<typeof receipt>) => { r.verification.status = "FAIL" },
    (r: ReturnType<typeof receipt>) => { r.contract.outputs[1] = r.contract.outputs[0] },
  ]) {
    const value = receipt(); mutate(value)
    expect(() => validateReceipt(value, "3d-generate")).toThrow()
  }
})
test("3D native leaf rejects unauthorized roles independently of tool visibility", async () => {
  const tools: any[] = []
  await plugin.setup({ tool: { transform: async (fn: any) => { fn({ add: (tool: any) => tools.push(tool) }); return { dispose: async () => {} } } } } as any)
  expect(tools).toHaveLength(6)
  const generate = tools.find((tool) => tool.name === "watoom_toolkit_generate3d")
  for (const agent of ["build", "watoom-workflow", "watoom-investigator", "watoom-reviewer", "untrusted"]) await expect(generate.execute({ generator: "watoom.tree" }, { agent })).rejects.toThrow("denied")
})

test("local-only catalog never exposes hosted paid providers", () => {
  const result = localCatalog({ generators: [{ id: "meshy", backend: "hosted" }, { id: "other-paid", backend: "hosted" }, { id: "asset-assistant.avian", backend: "blender-cpu" }, { id: "llama-mesh", backend: "generic-specialist" }] })
  expect(result.generators.map((value) => (value as { id: string }).id)).toEqual(["asset-assistant.avian", "llama-mesh"])
})
