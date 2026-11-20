export * as SessionLoop from "./loop.js"

import { SessionMessage } from "../message.js"

const canonical = (value: unknown): string => {
  if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]"
  if (value !== null && typeof value === "object")
    return (
      "{" +
      Object.entries(value)
        .toSorted(([a], [b]) => a.localeCompare(b))
        .map(([key, item]) => JSON.stringify(key) + ":" + canonical(item))
        .join(",") +
      "}"
    )
  return JSON.stringify(value) ?? "undefined"
}

// Native tools that return a durable request_id for work that keeps running after the call returns.
const EXTERNAL_JOB_TOOLS = ["watoom_game_worker", "watoom_asset_capture", "watoom_rig_game_job", "watoom_esp32"]
const EXTERNAL_JOB_LIVE_STATUSES = ["QUEUED", "RUNNING", "WAITING_FOR_HEADROOM", "PAUSED"]
// A deliberate sleep/wait between two polls is elapsed time, not a repeat. Bounded so an endless
// sleep-and-poll loop with unchanged results still stops.
const MAX_WAITS_BETWEEN_POLLS = 24

const liveExternalJob = (content: ReadonlyArray<{ type: string; text?: string }> | undefined) =>
  (content ?? []).some((item) => {
    if (item.type !== "text" || typeof item.text !== "string") return false
    try {
      const value: unknown = JSON.parse(item.text)
      return (
        value !== null &&
        typeof value === "object" &&
        "request_id" in value &&
        typeof value.request_id === "string" &&
        "status" in value &&
        typeof value.status === "string" &&
        EXTERNAL_JOB_LIVE_STATUSES.includes(value.status)
      )
    } catch {
      return false
    }
  })

/** Uses the existing durable transcript, so restart cannot reset a stalled cycle.
 * A fresh user or external synthetic input resets the boundary; changing results constitute progress.
 * Live asynchronous jobs are a progress barrier, not a reason to cancel work.
 */
export const reason = (messages: ReadonlyArray<SessionMessage.Info>) => {
  const boundary = messages.findLastIndex(
    (message) =>
      message.type === "user" ||
      (message.type === "synthetic" &&
        message.text.trim().length > 0 &&
        message.metadata?.source !== "handoff-recovery"),
  )
  const pending = new Map<string, { id: string; status: string }>()
  let waits = 0
  const calls = messages.slice(boundary + 1).flatMap((message) =>
    message.type === "assistant"
      ? message.content.flatMap((part) => {
          if (part.type !== "tool" || (part.state.status !== "completed" && part.state.status !== "error")) return []
          // A wait is neither progress nor a repeat: it is skipped so it never counts toward, or breaks, a cycle.
          // It is remembered so that polls of a live external job on either side of it are not identical.
          if (part.name === "wait" || part.name === "sleep") {
            waits += 1
            return []
          }
          if (
            part.name === "shell" &&
            typeof part.state.input.command === "string" &&
            /^\s*sleep\s+\d+(?:\.\d+)?\s*;?\s*$/.test(part.state.input.command)
          ) {
            waits += 1
            return []
          }
          const running = part.state.content?.some((item) => {
            if (item.type !== "text") return false
            try {
              const value: unknown = JSON.parse(item.text)
              return (
                value !== null &&
                typeof value === "object" &&
                "job_id" in value &&
                "status" in value &&
                (value.status === "running" || value.status === "starting")
              )
            } catch {
              return false
            }
          })
          if (running) return [null]
          // A Code Mode script that invoked no tool gathered no evidence, whatever its text
          // returned; otherwise each reworded no-op script looks like a new attempt.
          const toolCalls = part.state.metadata?.toolCalls
          const signature =
            part.name === "execute" && Array.isArray(toolCalls) && toolCalls.length === 0
              ? canonical({ name: part.name, toolCalls: 0 })
              : canonical({
                  name: part.name,
                  input: part.state.input,
                  status: part.state.status,
                  result: part.state.status === "error" ? part.state.error : part.state.content,
                  ...(EXTERNAL_JOB_TOOLS.includes(part.name) && liveExternalJob(part.state.content)
                    ? { waitsBefore: Math.min(waits, MAX_WAITS_BETWEEN_POLLS) }
                    : {}),
                })
          if (EXTERNAL_JOB_TOOLS.includes(part.name)) {
            for (const item of part.state.content ?? []) {
              if (item.type !== "text") continue
              let value: unknown
              try {
                value = JSON.parse(item.text)
              } catch {
                continue
              }
              if (
                value !== null &&
                typeof value === "object" &&
                "request_id" in value &&
                typeof value.request_id === "string" &&
                "status" in value &&
                typeof value.status === "string" &&
                EXTERNAL_JOB_LIVE_STATUSES.includes(value.status)
              )
                pending.set(signature, { id: value.request_id, status: value.status })
            }
          }
          return [signature]
        })
      : [],
  )
  const recent = calls.slice(calls.lastIndexOf(null) + 1).slice(-12)
  for (const period of [1, 2, 3]) {
    const tail = recent.slice(-period * 3)
    if (tail.length !== period * 3 || !tail.every((value, index) => value === tail[index % period])) continue
    if (tail.every((value) => value !== null && pending.has(value))) {
      const jobs = [
        ...new Set(
          tail
            .flatMap((value) => (value === null ? [] : [pending.get(value)!]))
            .map((job) => job.id + " (" + job.status + ")"),
        ),
      ]
      return (
        "External work is still pending: " +
        jobs.join(", ") +
        ". This is not an execution failure. " +
        "Stop repeated polling; retain these exact request IDs and wait for the existing completion notification. " +
        "Do not cancel, duplicate, or restart the jobs. Report any independent work already completed and the dependent next step."
      )
    }
    return (
      "Repeated tool cycle produced no new evidence across three attempts. Tools are disabled for this turn. " +
      "Report the last verified result, any outstanding job IDs, and the exact blocker or changed hypothesis needed. " +
      "Do not claim completion or restart existing work. Continue only after new user input."
    )
  }
}
