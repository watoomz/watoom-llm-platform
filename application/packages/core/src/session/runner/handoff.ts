export * as SessionHandoff from "./handoff.js"

import { Message } from "@opencode/ai/effect"
import { SessionMessage } from "../message.js"

export const PROMPT =
  "The previous stop-only reply did not provide a task handoff. Tools are disabled for this recovery. Using only the existing conversation and checkpoint, report the last verified result, what remains incomplete, the exact blocker or pending job IDs, and one concrete next action. Distinguish a saved checkpoint from completed work. Do not rerun tools or jobs, invent results, or reply only with a termination acknowledgement."

export const missing = (messages: ReadonlyArray<SessionMessage.Info>, recovery = false) => {
  const boundary = messages.findLastIndex((message) => message.type === "user")
  const user = messages[boundary]
  if (
    user?.type === "user" &&
    /^(?:please\s+)?(?:stop|pause|cancel|abort|terminate)(?:\s+(?:the|this|task|job|work|session|now|it))*[.!]?$/i.test(
      user.text.trim(),
    )
  )
    return false
  const index = messages.findLastIndex((message) => message.type === "assistant")
  if (index <= boundary) return false
  const last = messages[index]
  if (last?.type !== "assistant" || last.finish !== "stop" || last.error) return false
  const text = last.content
    .flatMap((part) => (part.type === "text" ? [part.text] : []))
    .join("")
    .trim()
  const stub = /^(?:terminating|terminated|stopping|exiting)[.!]?$/i.test(text)
  const tools = last.content.some((part) => part.type === "tool")
  if (recovery) return tools || !text || stub
  if (tools || !stub) return false
  return messages
    .slice(0, index)
    .some(
      (message) =>
        message.type === "compaction" ||
        (message.type === "assistant" && message.content.some((part) => part.type === "tool")),
    )
}

/** Preserve checkpoint facts as explicitly historical data when model recovery fails. */
export const failure = (messages: ReadonlyArray<SessionMessage.Info>) => {
  const checkpoint = messages.findLast((message) => message.type === "compaction" && message.status === "completed")
  const sections =
    checkpoint?.type === "compaction"
      ? checkpoint.summary.split(/(?=^## )/m).filter((section) => /^## (?:Work State|Next Move)\s*$/m.test(section))
      : []
  const excerpt = sections.map((section) => section.trim().slice(0, 2800)).join("\n\n")
  const latest = messages.findLast((message) => message.type === "user")
  return {
    type: "session.handoff-missing",
    message:
      "The model stopped without a useful handoff after one text-only recovery. Existing work and checkpoints are retained; no jobs were replayed." +
      (latest?.type === "user" ? "\n\nLatest user request (not completed): " + latest.text.slice(0, 1000) : "") +
      (excerpt
        ? "\n\nLast recorded checkpoint handoff (historical; not revalidated by this recovery):\n\n" + excerpt
        : " Resume with a request for the verified result, remaining work and exact blocker."),
  }
}

export const recoveryMessages = (messages: ReadonlyArray<Message>) =>
  messages.filter(
    (message) =>
      message.role !== "assistant" ||
      message.content.some((part) => part.type !== "text") ||
      !/^(?:terminating|terminated|stopping|exiting)[.!]?$/i.test(
        message.content
          .flatMap((part) => (part.type === "text" ? [part.text] : []))
          .join("")
          .trim(),
      ),
  )
