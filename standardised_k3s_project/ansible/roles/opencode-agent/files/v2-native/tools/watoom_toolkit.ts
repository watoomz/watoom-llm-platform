// TEMPLATE ONLY — not installed by the host installer. OpenCode custom tools require
// authenticated access to WatooM Toolkit. DO NOT store bearer tokens in project files.
// Use a Kubernetes Secret reference for WATOOM_TOOLKIT_TOKEN only after independently
// approving an explicit canary rollout and reviewing effective agent permissions.
import { tool } from "@opencode-ai/plugin"

const URL = "http://watoom-toolkit.opencode.svc.cluster.local:8879"
async function call(path: string, data?: Record<string, unknown>): Promise<string> {
  const token = process.env.WATOOM_TOOLKIT_TOKEN
  if (!token) return "BLOCKED: WATOOM_TOOLKIT_TOKEN is not configured. No request attempted."
  const r = await fetch(URL + path, {
    method: data ? "POST" : "GET",
    headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
    body: data ? JSON.stringify(data) : undefined,
    signal: AbortSignal.timeout(195000),
  })
  const result = await r.text()
  if (!r.ok) throw new Error(`Toolkit HTTP ${r.status}: ${result.slice(0, 500)}`)
  return result.slice(0, 12000)
}

export const catalog = tool({
  description: "List the authenticated WatooM Toolkit tool profiles. Never manage Kali tools.",
  args: {},
  async execute() { return call("/api/catalog") },
})

export const probe = tool({
  description: "Execute the fixed read-only toolkit tool-availability probe.",
  args: {},
  async execute() { return call("/api/jobs", { task: "probe" }) },
})

export const godotImport = tool({
  description: "Run a bounded headless Godot project import validation within /workspace.",
  args: { path: tool.schema.string().describe("Workspace-relative Godot project directory") },
  async execute(args) { return call("/api/jobs", { task: "godot-import", path: args.path }) },
})

export const blenderRender = tool({
  description: "Render a single Blender frame in isolated toolkit environment. Requires approved source files.",
  args: { path: tool.schema.string().describe("Workspace-relative .blend file"), frame: tool.schema.number().int().min(1).max(100000) },
  async execute(args) { return call("/api/jobs", { task: "blender-render", path: args.path, frame: args.frame }) },
})
