import type { Context, Plugin } from "@opencode/plugin/promise/plugin"

const discovery = new Set(["watoom-builder", "watoom-workflow", "watoom-investigator", "watoom-reviewer"])
const endpoint = "http://watoom-toolkit.opencode.svc.cluster.local:8879"
const empty = { type: "object", properties: {}, additionalProperties: false } as const
const path = { type: "string", minLength: 1, maxLength: 2048 } as const
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
            const args = input as { path?: string; frame?: number }
            if (definition.name === "godotImport" || definition.name === "blenderRender") {
              if (
                typeof args.path !== "string" ||
                !args.path ||
                args.path.length > 2048 ||
                args.path.startsWith("/") ||
                args.path.includes("\\") ||
                args.path.split("/").some((x) => x === ".." || x === ".")
              )
                throw new Error("Invalid workspace-relative Toolkit path")
              if (
                definition.name === "blenderRender" &&
                (!Number.isInteger(args.frame) || args.frame! < 1 || args.frame! > 100000)
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
                  : { task: definition.name === "godotImport" ? "godot-import" : "blender-render", ...args }
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
            const output = JSON.parse(text)
            return { output, content: JSON.stringify(output) }
          },
        })
      }
    })
    return () => registration.dispose()
  },
} satisfies Plugin
