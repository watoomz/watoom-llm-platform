export * as Knowledge from "./knowledge.js"
import { envelope, scopeKey, type Scope, type Envelope } from "./contract.js"
export type Change = {
  requestID: string
  action: "correct" | "supersede" | "consolidate" | "withdraw"
  targets: readonly string[]
  summary: string
  reason: string
}
export function prepare(scope: Scope, input: Change, sources: Envelope[]) {
  scopeKey(scope)
  if (
    !/^[A-Za-z0-9_-]{1,80}$/.test(input.requestID) ||
    !["correct", "supersede", "consolidate", "withdraw"].includes(input.action) ||
    !Array.isArray(input.targets) ||
    input.targets.length < 1 ||
    input.targets.length > 16 ||
    input.targets.some((id) => !/^[a-f0-9]{64}$/.test(id)) ||
    new Set(input.targets).size !== input.targets.length ||
    (input.action === "consolidate" && input.targets.length < 2) ||
    typeof input.summary !== "string" ||
    Buffer.byteLength(input.summary) > 5500 ||
    (input.action !== "withdraw" && !input.summary.trim()) ||
    typeof input.reason !== "string" ||
    !input.reason.trim() ||
    Buffer.byteLength(input.reason) > 512
  )
    throw Error("Invalid scoped memory change")
  if (
    sources.length !== input.targets.length ||
    input.targets.some(
      (id) => !sources.some((source) => source.id === id && scopeKey(source.scope) === scopeKey(scope)),
    )
  )
    throw Error("Unknown or cross-scope memory source")
  return envelope({
    scope,
    job: "knowledge:" + input.requestID,
    seq: 1,
    kind: "checkpoint",
    content: JSON.stringify({
      schema: "watoom.knowledge.v1",
      action: input.action,
      targets: [...input.targets].sort(),
      summary: input.summary,
      reason: input.reason,
    }),
  })
}
export function change(value: Envelope): Omit<Change, "requestID"> | undefined {
  if (!value.job.startsWith("knowledge:")) return
  try {
    const parsed = JSON.parse(value.content)
    if (
      parsed.schema !== "watoom.knowledge.v1" ||
      !["correct", "supersede", "consolidate", "withdraw"].includes(parsed.action) ||
      !Array.isArray(parsed.targets) ||
      parsed.targets.some((id: unknown) => typeof id !== "string" || !/^[a-f0-9]{64}$/.test(id))
    )
      return
    return parsed
  } catch {
    return
  }
}
export function active(values: Envelope[], revisions: Envelope[]) {
  const hidden = new Set(revisions.flatMap((value) => change(value)?.targets ?? []))
  return values.filter((value) => !hidden.has(value.id) && change(value)?.action !== "withdraw")
}
