import { Message } from "@opencode/ai/effect"

/** Model-specific ceiling. Completion tokens include reasoning; summaries use only a fraction. */
export const summaryBudget = (limit: { context: number; output: number; input?: number }) => {
  const context = limit.context > 0 ? limit.context : 200_000
  const output = Math.max(1, Math.min(limit.output > 0 ? limit.output : 32_000, 32_000, Math.floor(context / 8)))
  return {
    output,
    target: Math.max(1, Math.min(1024, Math.floor(output / 4))),
    input: Math.max(1, Math.min(limit.input && limit.input > 0 ? limit.input : context, context) - output - 4096),
  }
}

/** Bound the summarizer view only; the full event transcript remains durably stored. */
export const boundedTranscript = (messages: readonly Message[], bytes: number, session: string) => {
  const encode = (message: Message) => JSON.stringify(message)
  if (Buffer.byteLength(messages.map(encode).join("\n")) <= bytes) return [...messages]
  const marker = `[Detailed evidence retained in original session ${session}; excerpts below are bounded. Retrieve original message IDs when needed.]`
  // UTF-8 bytes are a conservative token ceiling. Keep IDs/roles, endpoints and both ends of each excerpt.
  const allowance = Math.max(
    0,
    Math.floor((bytes - Buffer.byteLength(marker) - messages.length * 100) / Math.max(1, messages.length)),
  )
  const excerpt = (text: string) => {
    const raw = Buffer.from(text)
    if (raw.length <= allowance) return text
    const half = Math.max(0, Math.floor((allowance - 80) / 2))
    return (
      raw.subarray(0, half).toString() +
      "\n[excerpt; full message retained in session]\n" +
      raw.subarray(raw.length - half).toString()
    )
  }
  const lines = messages.map((message) => `${message.role} ${message.id ?? ""}: ${excerpt(encode(message))}`)
  const raw = Buffer.from(marker + "\n" + lines.join("\n"))
  if (raw.length <= bytes) return [Message.user(raw.toString())]
  // Extremely many messages: retain the beginning and newest evidence. This never changes durable history.
  const half = Math.max(0, Math.floor((bytes - Buffer.byteLength(marker) - 40) / 2))
  return [
    Message.user(
      marker +
        "\n" +
        raw.subarray(0, half).toString() +
        "\n[older excerpts omitted]\n" +
        raw.subarray(raw.length - half).toString(),
    ),
  ]
}
