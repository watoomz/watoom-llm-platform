import type { Context, Plugin } from "@opencode/plugin/promise/plugin"
const endpoint = "http://watoom-toolkit.opencode.svc.cluster.local:8879"
const discovery = new Set(["watoom-builder", "watoom-workflow", "watoom-investigator", "watoom-reviewer"])
const empty = { type: "object", properties: {}, additionalProperties: false } as const
const path = { type: "string", minLength: 1, maxLength: 400 } as const
const definitions = [
  { name: "generators", input: empty, description: "Discover deployed 3D generators, actual availability and typed parameter bounds." },
  { name: "generate3d", input: { type: "object", properties: {
      generator: { type: "string", enum: ["asset-assistant.avian", "asset-assistant.quadruped", "asset-assistant.human", "watoom.tree", "watoom.terrain", "watoom.building", "watoom.rock"] },
      parameters: { type: "object", additionalProperties: { type: "number" } }, seed: { type: "integer", minimum: 0, maximum: 2147483647 }, style: { type: "string", enum: ["default", "magpie", "wombat"] },
    }, required: ["generator"], additionalProperties: false }, description: "Generate an approved CPU procedural asset in a disposable worker. Returns editable Blender, verified GLB, geometry checks, six renders and checksums. Avian provides Idle/Flight; quadruped provides Idle/Walk. No paid or GPU tasks." },
  { name: "inspect3d", input: { type: "object", properties: { path }, required: ["path"], additionalProperties: false }, description: "Inspect a workspace GLB or packed Blender asset on a copy in an isolated worker; render six views, validate and reimport its export." },
  { name: "repair3d", input: { type: "object", properties: { path }, required: ["path"], additionalProperties: false }, description: "Repair duplicate vertices, degenerate edges and normals on a copy, preserving the original and before/after geometry reports." },
  { name: "jobs3d", input: empty, description: "Read recent durable Toolkit outcomes; missing outcomes are uncertain and must not be replayed blindly." },
  { name: "cancel3d", input: { type: "object", properties: { id: { type: "string", pattern: "^[a-f0-9]{16}$" } }, required: ["id"], additionalProperties: false }, description: "Cancel an active isolated 3D job and remove its worker." },
] as const
function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw Error("Invalid Toolkit 3D response")
  return value as Record<string, unknown>
}
/** Release policy: expose verified local engines only, including when the preserved Toolkit baseline advertises legacy providers. */
export function localCatalog(value: unknown) {
  const catalog = record(value)
  if (!Array.isArray(catalog.generators)) throw Error("Toolkit generator registry missing")
  const generators = catalog.generators.filter((value) => {
    const generator = record(value)
    return generator.id !== "meshy" && (generator.backend === "blender-cpu" || generator.backend === "generic-specialist")
  })
  return { profiles: catalog.profiles, installed: catalog.installed, generators, capabilities: catalog.capabilities }
}
export function validateReceipt(value: unknown, task: string) {
  const receipt = record(value)
  if (receipt.status !== "PASS" || receipt.task !== task || receipt.exit_code !== 0 || typeof receipt.id !== "string" || !/^[a-f0-9]{16}$/.test(receipt.id)) throw Error("Toolkit 3D job failed or is unverified")
  if (record(receipt.verification).status !== "PASS" || record(receipt.contract).id !== "watoom-3d/v1" || record(receipt.contract).available !== true) throw Error("Toolkit 3D output contract missing")
  const expected = ["asset.blend", "asset.glb", "manifest.json", "validation.json", "front.png", "back.png", "left.png", "right.png", "top.png", "perspective.png", ...(task === "3d-repair" ? ["before-validation.json"] : [])].sort()
  if (!Array.isArray(receipt.artifacts) || receipt.artifacts.length !== expected.length) throw Error("Required 3D artifact missing")
  const artifacts = receipt.artifacts.map(record)
  const seen = new Set<string>()
  for (const value of receipt.artifacts) {
    const artifact = record(value)
    if (artifact.root !== "state" || typeof artifact.path !== "string" || !artifact.path.startsWith("jobs/" + receipt.id + "/worker/artifacts/") || artifact.path.includes("..") || typeof artifact.sha256 !== "string" || !/^[a-f0-9]{64}$/.test(artifact.sha256) || typeof artifact.bytes !== "number" || !Number.isSafeInteger(artifact.bytes) || artifact.bytes < 1 || artifact.bytes > 67108864) throw Error("Invalid 3D artifact evidence")
    const name = artifact.path.slice(("jobs/" + receipt.id + "/worker/artifacts/").length)
    if (!expected.includes(name) || seen.has(name)) throw Error("Unexpected or duplicate 3D artifact")
    seen.add(name)
  }
  const published = record(receipt.published)
  if (published.root !== "assets" || published.path !== "generated/watoom-toolkit-3d/v1/" + receipt.id || !Array.isArray(published.files) || published.files.length !== expected.length) throw Error("3D publication unverified")
  const publishedNames = new Set<string>()
  for (const item of published.files) {
    const file = record(item)
    if (typeof file.path !== "string" || publishedNames.has(file.path)) throw Error("Duplicate published artifact")
    publishedNames.add(file.path)
    const original = artifacts.find((artifact) => artifact.path === "jobs/" + receipt.id + "/worker/artifacts/" + file.path)
    if (!original || original.sha256 !== file.sha256 || original.bytes !== file.bytes) throw Error("3D published artifact mismatch")
  }
  const outputs = record(receipt.contract).outputs
  if (!Array.isArray(outputs) || outputs.length !== expected.length || new Set(outputs.map((item) => { const output = record(item); return String(output.root) + ":" + output.path })).size !== expected.length || outputs.some((item) => { const output = record(item); return !artifacts.some((artifact) => artifact.root === output.root && artifact.path === output.path) })) throw Error("3D contract output set mismatch")
  return receipt
}
export default {
  id: "watoom.toolkit.3d",
  async setup(ctx: Pick<Context, "tool">) {
    const registration = await ctx.tool.transform((editor) => {
      for (const definition of definitions) editor.add({
        name: "watoom_toolkit_" + definition.name,
        options: { codemode: false, permission: "watoom_toolkit_" + definition.name },
        description: definition.description, input: definition.input, output: {},
        async execute(input, context) {
          const readOnly = definition.name === "generators" || definition.name === "jobs3d"
          if (readOnly ? !discovery.has(context.agent) : context.agent !== "watoom-builder") throw Error("3D Toolkit execution denied for this agent")
          const args = record(input)
          const allowed = definition.name === "generate3d" ? ["generator", "parameters", "seed", "style"] : definition.name === "inspect3d" || definition.name === "repair3d" ? ["path"] : definition.name === "cancel3d" ? ["id"] : []
          if (Object.keys(args).some((key) => !allowed.includes(key))) throw Error("Unexpected 3D input field")
          if ("path" in args && (typeof args.path !== "string" || args.path.startsWith("/") || args.path.includes("\\") || args.path.length > 400 || args.path.split("/").some((part) => !part || part === "." || part === ".."))) throw Error("Invalid workspace-relative asset path")
          const token = process.env.WATOOM_TOOLKIT_TOKEN
          if (!token) throw Error("Toolkit credential unavailable")
          const task = definition.name === "generate3d" ? "3d-generate" : definition.name === "inspect3d" ? "3d-inspect" : "3d-repair"
          const body = readOnly ? undefined : definition.name === "cancel3d" ? args : { task, ...args }
          const route = definition.name === "generators" ? "/api/catalog" : definition.name === "cancel3d" ? "/api/jobs/cancel" : "/api/jobs"
          const response = await fetch(endpoint + route, { method: body ? "POST" : "GET", headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined, redirect: "error", signal: AbortSignal.any([context.signal, AbortSignal.timeout(210000)]) })
          if (!response.ok) throw Error("Toolkit 3D HTTP " + response.status)
          const reader = response.body?.getReader()
          if (!reader) throw Error("Toolkit response missing")
          const chunks: Uint8Array[] = []
          let bytes = 0
          try { for (;;) { const next = await reader.read(); if (next.done) break; bytes += next.value.length; if (bytes > 524288) throw Error("Toolkit response too large"); chunks.push(next.value) } }
          finally { await reader.cancel(); reader.releaseLock() }
          const value = JSON.parse(Buffer.concat(chunks).toString("utf8"))
          if (definition.name === "generators") {
            const catalog = localCatalog(value)
            return { output: catalog, content: JSON.stringify({ generators: catalog.generators, capabilities: catalog.capabilities }) }
          }
          if (!readOnly && definition.name !== "cancel3d") {
            const receipt = validateReceipt(value, task)
            return { output: receipt, content: JSON.stringify({ id: receipt.id, status: receipt.status, published: receipt.published, verification: receipt.verification }) }
          }
          return { output: value, content: JSON.stringify(value) }
        },
      })
    })
    return () => registration.dispose()
  },
} satisfies Plugin
