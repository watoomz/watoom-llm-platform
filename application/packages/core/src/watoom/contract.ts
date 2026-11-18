import { createHash } from "node:crypto"
export type Scope = { project: string; repository: string; agent: string }
export type Event = {
  scope: Scope
  job: string
  seq: number
  kind: "checkpoint" | "completion" | "compaction"
  content: string
}
export type Envelope = Event & { version: 2; id: string; digest: string }
export type Receipt = { id: string; digest: string; scope: Scope; memoryId: string; durability: "observed" | "durable" }
export function exactKeys(value: unknown, keys: string[]): void {
  if (
    !value ||
    typeof value !== "object" ||
    Array.isArray(value) ||
    Object.getPrototypeOf(value) !== Object.prototype ||
    Object.keys(value).sort().join("|") !== keys.sort().join("|")
  )
    throw Error("unexpected object fields")
  for (const descriptor of Object.values(Object.getOwnPropertyDescriptors(value)))
    if (!("value" in descriptor)) throw Error("accessors not allowed")
}
export function scopeKey(scope: Scope): string {
  exactKeys(scope, ["project", "repository", "agent"])
  for (const value of [scope.project, scope.repository, scope.agent])
    if (typeof value !== "string" || !value || value.length > 256 || /[\x00-\x1f\x7f]/.test(value))
      throw Error("invalid scope")
  return JSON.stringify([scope.project, scope.repository, scope.agent])
}
export function envelope(event: Event): Envelope {
  exactKeys(event, ["scope", "job", "seq", "kind", "content"])
  const scope = scopeKey(event.scope)
  if (
    typeof event.job !== "string" ||
    !event.job ||
    /[\x00-\x1f\x7f]/.test(event.job) ||
    event.job.length > 256 ||
    !Number.isSafeInteger(event.seq) ||
    event.seq < 1 ||
    !["checkpoint", "completion", "compaction"].includes(event.kind)
  )
    throw Error("invalid event")
  if (typeof event.content !== "string" || !event.content || Buffer.byteLength(event.content) > 8192)
    throw Error("invalid content size")
  if (/(?:-----BEGIN .*PRIVATE KEY|Bearer\s+\S+|(?:password|api[_-]?key|secret)\s*[:=]\s*\S+)/i.test(event.content))
    throw Error("sensitive content")
  const hash = (s: string) => createHash("sha256").update(s).digest("hex")
  const id = hash(JSON.stringify([scope, event.job, event.seq, event.kind]))
  const digest = hash(JSON.stringify([id, event.content]))
  return { ...event, scope: { ...event.scope }, version: 2, id, digest }
}
export function matches(e: Envelope, r: Receipt): boolean {
  exactKeys(r, ["id", "digest", "scope", "memoryId", "durability"])
  if (typeof r.memoryId !== "string" || !/^[A-Za-z0-9._:-]{1,512}$/.test(r.memoryId)) return false
  return (
    r.id === e.id &&
    r.digest === e.digest &&
    scopeKey(r.scope) === scopeKey(e.scope) &&
    Boolean(r.memoryId) &&
    ["observed", "durable"].includes(r.durability)
  )
}
export interface MemoryPort {
  /** Only semantic capture; external actions must never enter this outbox. */
  remember(e: Envelope, signal?: AbortSignal): Promise<Receipt>
  reconcile(e: Envelope, signal?: AbortSignal): Promise<Receipt | undefined>
}

export function checkpointJson(input: unknown): string {
  const seen = new Set<object>()
  let nodes = 0
  function check(value: unknown, depth: number): void {
    if (++nodes > 256 || depth > 8) throw Error("checkpoint complexity")
    if (value === null || typeof value === "boolean" || typeof value === "string") return
    if (typeof value === "number" && Number.isFinite(value)) return
    if (
      typeof value !== "object" ||
      !value ||
      (!Array.isArray(value) && Object.getPrototypeOf(value) !== Object.prototype) ||
      seen.has(value)
    )
      throw Error("checkpoint must be plain JSON")
    seen.add(value)
    for (const [key, d] of Object.entries(Object.getOwnPropertyDescriptors(value))) {
      if (key === "length" && Array.isArray(value)) continue
      if (!d.enumerable || !("value" in d) || key === "toJSON") throw Error("checkpoint must be plain data")
      check(d.value, depth + 1)
    }
    if (Object.getOwnPropertySymbols(value).length) throw Error("checkpoint symbols")
    seen.delete(value)
  }
  check(input, 0)
  return JSON.stringify(input)
}
