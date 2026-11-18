export * as AutoRecall from "./auto-recall.js"
import { createHash } from "node:crypto"
import type { Message } from "@opencode/ai/effect"

/** About 500 tokens of knowledge per request at most. */
export const BUDGET = 2000

/** Commands that deploy, change infrastructure or recover state: recall before repeating them. */
const verb = (tool: string, verbs: string) => "\\b" + tool + "\\b[^|;&\\n]{0,80}?\\s(?:" + verbs + ")\\b"
const RISKY = new RegExp(
  [
    "\\bansible-playbook\\b",
    "\\bterraform\\s+apply\\b",
    verb("kubectl", "apply|patch|rollout|delete|scale|set|replace|create"),
    verb("helm", "install|upgrade|rollback"),
    verb("systemctl", "restart|start|stop|enable|disable"),
    verb("(?:docker|podman)", "build|push|run"),
    verb("git", "push|merge|rebase"),
  ].join("|"),
)
const WORKERS = new Set(["watoom_game_worker", "watoom_asset_capture", "watoom_rig_game_job"])

export type Trigger = { key: string; query: string; reason: "task" | "command" | "failure" }

const hash = (value: string) => createHash("sha256").update(value).digest("hex").slice(0, 24)
const squash = (value: string) => value.replace(/\s+/g, " ").trim()
const flat = (value: unknown): string => {
  if (typeof value === "string") return value
  try {
    return JSON.stringify(value) ?? ""
  } catch {
    return ""
  }
}

/**
 * Decide from the request alone whether this step warrants one targeted recall.
 * Only a new user turn, a risky command just issued, or a failed tool result qualify; the
 * caller keys the result so each trigger searches once, never per step.
 */
export function trigger(messages: readonly Message[]): Trigger | undefined {
  const last = messages.at(-1)
  if (!last) return
  if (last.role === "user") {
    const text = squash(last.content.flatMap((part) => (part.type === "text" ? [part.text] : [])).join(" "))
    if (text.length < 12) return
    return { key: "u:" + hash(text), query: text.slice(0, 600), reason: "task" }
  }
  if (last.role !== "tool") return
  const calls = new Map<string, { name: string; input: unknown }>()
  for (const message of messages.slice(-4))
    if (message.role === "assistant")
      for (const part of message.content) if (part.type === "tool-call") calls.set(part.id, { name: part.name, input: part.input })
  for (const part of last.content) {
    if (part.type !== "tool-result") continue
    const exit = part.metadata?.exit
    if (part.result.type === "error" || (typeof exit === "number" && exit !== 0)) {
      const detail = squash(flat(part.result.value)).slice(0, 300)
      return { key: "f:" + part.id, query: (part.name + " failed: " + detail).slice(0, 600), reason: "failure" }
    }
  }
  for (const part of last.content) {
    if (part.type !== "tool-result") continue
    const call = calls.get(part.id)
    if (!call) continue
    const input = call.input as { command?: unknown; action?: unknown; operation?: unknown; job?: unknown } | undefined
    if (call.name === "shell" && typeof input?.command === "string" && RISKY.test(input.command))
      return { key: "t:" + part.id, query: squash(input.command).slice(0, 600), reason: "command" }
    if (WORKERS.has(call.name) && input?.action === "request")
      return { key: "t:" + part.id, query: (call.name + " " + flat(input.operation) + " " + flat(input.job)).slice(0, 600), reason: "command" }
  }
  return
}

export function note(reason: Trigger["reason"], lines: readonly string[]) {
  if (!lines.length) return
  const why = reason === "task" ? "this task" : reason === "command" ? "the command just run" : "the failure just seen"
  return (
    "Relevant learned knowledge for " + why + " (automatic recall; verify it applies before reuse, cite the ref when you use it):\n" +
    lines.join("\n")
  )
}

/** Per-session last trigger and note, bounded. */
export function cache(limit = 256) {
  const map = new Map<string, { key: string; note?: string }>()
  return {
    get: (sessionID: string) => map.get(sessionID),
    set: (sessionID: string, value: { key: string; note?: string }) => {
      map.delete(sessionID)
      map.set(sessionID, value)
      if (map.size > limit) map.delete(map.keys().next().value!)
    },
  }
}
