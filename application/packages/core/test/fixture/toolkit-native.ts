import type { Context, Plugin } from "@opencode/plugin/promise/plugin"

const discovery = new Set(["watoom-builder", "watoom-workflow", "watoom-investigator", "watoom-reviewer"])
const endpoint = "http://watoom-toolkit.opencode.svc.cluster.local:8879"
const empty = { type: "object", properties: {}, additionalProperties: false } as const
const path = { type: "string", minLength: 1, maxLength: 400 } as const
const definitions = [
  {
    name: "catalog",
    input: empty,
    description: "Read the authenticated Toolkit capability catalog; no job execution.",
  },
  { name: "probe", input: empty, description: "Run the fixed Toolkit availability probe; builder only." },
  {
    name: "godotImport",
    input: { type: "object", properties: { path }, required: ["path"], additionalProperties: false },
    description: "Validate an approved workspace Godot project through the fixed import job; builder only.",
  },
  {
    name: "blenderRender",
    input: {
      type: "object",
      properties: { path, frame: { type: "integer", minimum: 1, maximum: 100000 } },
      required: ["path", "frame"],
      additionalProperties: false,
    },
    description: "Render one approved workspace Blender frame through the fixed job; builder only.",
  },
] as const

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid Toolkit receipt")
  return value as Record<string, unknown>
}

function validateReceipt(value: unknown, task: string, requested: { path?: unknown; frame?: unknown }) {
  const receipt = record(value)
  if (typeof receipt.id !== "string" || !/^[a-f0-9]{16}$/.test(receipt.id) || receipt.task !== task)
    throw new Error("Invalid Toolkit receipt identity")
  if (receipt.status !== "PASS") throw new Error("Toolkit job did not pass")
  if (receipt.exit_code !== 0) throw new Error("Toolkit process and receipt disagree")
  const verification = record(receipt.verification)
  const contract = record(receipt.contract)
  const expected =
    task === "godot-import"
      ? "godot-import/4.7.2-cache10/v1"
      : task === "blender-render"
        ? "blender-render/png/v1"
        : "process-exit/v1"
  if (verification.status !== "PASS" || contract.available !== true || contract.id !== expected)
    throw new Error("Toolkit output contract is unverified or unsupported")
  const count = task === "godot-import" ? 3 : task === "blender-render" ? 1 : 0
  const artifacts = receipt.artifacts ?? []
  if (
    !Array.isArray(artifacts) ||
    artifacts.length !== count ||
    !Array.isArray(contract.outputs) ||
    contract.outputs.length !== count
  )
    throw new Error("Toolkit required artifact evidence missing")
  const expectedPaths =
    task === "godot-import"
      ? [
          ".godot/editor/filesystem_cache10",
          ".godot/global_script_class_cache.cfg",
          ".godot/editor/project_metadata.cfg",
        ].map((name) => ({ root: "workspace", path: String(requested.path) + "/" + name }))
      : task === "blender-render"
        ? [
            {
              root: "state",
              path: "jobs/" + receipt.id + "/render_" + String(requested.frame).padStart(4, "0") + ".png",
            },
          ]
        : []
  const paths = new Set<string>()
  for (let index = 0; index < artifacts.length; index++) {
    const artifact = record(artifacts[index])
    const output = record(contract.outputs[index])
    if (
      (artifact.root !== "workspace" && artifact.root !== "state") ||
      typeof artifact.path !== "string" ||
      !artifact.path ||
      artifact.path.length > 1024 ||
      artifact.path.startsWith("/") ||
      artifact.path.includes("\\") ||
      artifact.path.split("/").some((part) => !part || part === "." || part === "..") ||
      typeof artifact.sha256 !== "string" ||
      !/^[a-f0-9]{64}$/.test(artifact.sha256) ||
      typeof artifact.bytes !== "number" ||
      !Number.isSafeInteger(artifact.bytes) ||
      artifact.bytes < 1 ||
      artifact.bytes > 33554432 ||
      artifact.root !== output.root ||
      artifact.path !== output.path ||
      artifact.path !== expectedPaths[index]?.path ||
      artifact.root !== expectedPaths[index]?.root
    )
      throw new Error("Invalid Toolkit artifact evidence")
    const identity = artifact.root + ":" + artifact.path
    if (paths.has(identity)) throw new Error("Duplicate Toolkit artifact evidence")
    paths.add(identity)
  }
}

export default {
  id: "watoom.toolkit.native",
  async setup(ctx: Pick<Context, "tool">) {
    const registration = await ctx.tool.transform((editor) => {
      for (const definition of definitions) {
        const action = "watoom_toolkit_" + definition.name
        editor.add({
          name: action,
          options: { codemode: false, permission: action },
          description: definition.description,
          input: definition.input,
          output: {},
          async execute(input, context) {
            // Leaf authorization is required: registry filtering alone does not authorize execution.
            if (definition.name === "catalog" ? !discovery.has(context.agent) : context.agent !== "watoom-builder")
              throw new Error("Toolkit execution denied for this agent")
            const args = record(input)
            const allowed =
              definition.name === "godotImport"
                ? ["path"]
                : definition.name === "blenderRender"
                  ? ["path", "frame"]
                  : []
            if (Object.keys(args).some((key) => !allowed.includes(key))) throw new Error("Invalid Toolkit input field")
            if (definition.name === "godotImport" || definition.name === "blenderRender") {
              if (
                typeof args.path !== "string" ||
                !args.path ||
                args.path.length > 400 ||
                args.path.startsWith("/") ||
                args.path.includes("\\") ||
                args.path.split("/").some((x) => !x || x === ".." || x === ".")
              )
                throw new Error("Invalid workspace-relative Toolkit path")
              if (
                definition.name === "blenderRender" &&
                (!Number.isInteger(args.frame) ||
                  typeof args.frame !== "number" ||
                  args.frame < 1 ||
                  args.frame > 100000)
              )
                throw new Error("Invalid Toolkit frame")
            }
            const token = process.env.WATOOM_TOOLKIT_TOKEN
            if (!token) throw new Error("Toolkit credential unavailable; no request attempted")
            const data =
              definition.name === "catalog"
                ? undefined
                : definition.name === "probe"
                  ? { task: "probe" }
                  : definition.name === "godotImport"
                    ? { task: "godot-import", path: args.path }
                    : { task: "blender-render", path: args.path, frame: args.frame }
            const response = await fetch(endpoint + (data ? "/api/jobs" : "/api/catalog"), {
              method: data ? "POST" : "GET",
              headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
              body: data ? JSON.stringify(data) : undefined,
              signal: AbortSignal.any([context.signal, AbortSignal.timeout(195000)]),
              redirect: "error",
            })
            if (!response.ok) throw new Error("Toolkit HTTP " + response.status)
            const reader = response.body?.getReader()
            if (!reader) throw new Error("Toolkit response body missing")
            let text = "",
              bytes = 0
            const decoder = new TextDecoder()
            try {
              for (;;) {
                const part = await reader.read()
                if (part.done) break
                bytes += part.value.byteLength
                if (bytes > 524288) throw new Error("Toolkit response exceeds evidence limit; result unverified")
                text += decoder.decode(part.value, { stream: true })
              }
              text += decoder.decode()
            } finally {
              await reader.cancel()
              reader.releaseLock()
            }
            const output: unknown = JSON.parse(text)
            if (data) validateReceipt(output, data.task, args)
            return { output, content: JSON.stringify(output) }
          },
        })
      }
    })
    return () => registration.dispose()
  },
} satisfies Plugin
