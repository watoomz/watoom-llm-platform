export * as Learning from "./learning.js"
import { createHash } from "node:crypto"
import { type Envelope, type Event, type Scope } from "./contract.js"

/** Learned knowledge is shared by every agent of a project directory, not one role. */
export const AGENT = "watoom-knowledge"
export const EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
export const KINDS = ["procedure", "known-failure", "decision", "compatibility", "convention"] as const
export type Kind = (typeof KINDS)[number]

export type Input = {
  kind: Kind
  title: string
  environment: string
  problem: string
  solution: string
  commands: readonly string[]
  prerequisites: readonly string[]
  expectedResults: readonly string[]
  failureConditions: readonly string[]
  rollback: string
  evidence: readonly { tool: string; contains: string }[]
  sourceCommit?: string
}

/** A tool execution recorded by the session runtime; the only accepted source of evidence. */
export type ToolRecord = {
  sessionID: string
  id: string
  name: string
  status: "completed" | "error"
  input: unknown
  exit?: number
  time: number
}

export type Verified = { status: "verified" | "diagnostic"; evidence: string; validatedAt: string; calls: string[] }

const SECRET =
  /(?:-----BEGIN [A-Z ]*PRIVATE KEY|\bgh[pousr]_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}|\bsk-[A-Za-z0-9_-]{20,}|\bAKIA[0-9A-Z]{16}\b|\bxox[abprs]-[A-Za-z0-9-]{10,}|Bearer\s+[A-Za-z0-9._~+/-]{12,}|(?:password|passwd|api[_-]?key|secret|token)\s*[:=]\s*\S{6,})/i

const text = (value: string, max: number) => typeof value === "string" && value.length <= max && !/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/.test(value)
const list = (value: readonly string[], items: number, max: number) =>
  Array.isArray(value) && value.length <= items && value.every((item) => text(item, max) && item.trim().length > 0)
const squash = (value: string) => value.replace(/\s+/g, " ").trim()

export function validate(input: Input): string | undefined {
  if (!KINDS.includes(input.kind)) return "LEARN_KIND_INVALID"
  if (!text(input.title, 160) || input.title.trim().length < 8) return "LEARN_TITLE_INVALID: 8-160 characters"
  if (!text(input.environment, 300) || !text(input.problem, 1200) || !input.problem.trim()) return "LEARN_PROBLEM_REQUIRED"
  if (!text(input.solution, 2000) || !input.solution.trim()) return "LEARN_SOLUTION_REQUIRED"
  if (!list(input.commands, 12, 400) || !list(input.prerequisites, 8, 300) || !list(input.expectedResults, 8, 300))
    return "LEARN_LIST_BOUNDS: commands<=12x400, prerequisites/expectedResults<=8x300"
  if (!list(input.failureConditions, 8, 300) || !text(input.rollback, 600)) return "LEARN_LIST_BOUNDS"
  if (
    !Array.isArray(input.evidence) ||
    input.evidence.length < 1 ||
    input.evidence.length > 6 ||
    input.evidence.some((item) => !text(item.tool, 64) || !text(item.contains, 200) || item.contains.trim().length < 3)
  )
    return "LEARN_EVIDENCE_REQUIRED: 1-6 {tool, contains} references to tool calls made in this session"
  if (input.sourceCommit !== undefined && !/^[a-f0-9]{7,40}$/.test(input.sourceCommit)) return "LEARN_COMMIT_INVALID"
  if (SECRET.test(JSON.stringify(input))) return "LEARN_SENSITIVE_CONTENT: remove credentials or tokens"
  return
}

/**
 * Evidence comes only from the runtime's own tool records; a model's success claim is never evidence.
 * Each reference selects the latest matching call. Success-type knowledge is verified when a cited call
 * completed (shell exit 0) and, if commands are listed, a cited call actually ran one of them.
 * A known failure is diagnostic: it needs a cited call that actually failed.
 */
export function verify(input: Input, records: readonly ToolRecord[]): Verified | string {
  const cited: ToolRecord[] = []
  for (const reference of input.evidence) {
    const needle = squash(reference.contains)
    const match = records
      .filter((record) => record.name === reference.tool && squash(JSON.stringify(record.input ?? "")).includes(needle))
      .toSorted((a, b) => b.time - a.time)[0]
    if (!match) return "LEARN_EVIDENCE_NOT_FOUND: no " + reference.tool + " call in this session contains " + JSON.stringify(reference.contains)
    cited.push(match)
  }
  const succeeded = (record: ToolRecord) => record.status === "completed" && (record.exit === undefined || record.exit === 0)
  const describe = (record: ToolRecord) =>
    record.name + " " + record.id + " " + (succeeded(record) ? "succeeded" : "failed") + (record.exit === undefined ? "" : " exit " + record.exit) + " at " + new Date(record.time).toISOString()
  const latest = Math.max(...cited.map((record) => record.time))
  if (input.kind === "known-failure") {
    if (!cited.some((record) => !succeeded(record))) return "LEARN_FAILURE_EVIDENCE_REQUIRED: cite a call that actually failed"
    return { status: "diagnostic", evidence: cited.map(describe).join("; "), validatedAt: new Date(latest).toISOString(), calls: cited.map((r) => r.id) }
  }
  const passing = cited.filter(succeeded)
  if (!passing.length) return "LEARN_UNVERIFIED: no cited call succeeded; record it as known-failure or rerun the procedure"
  if (input.commands.length) {
    const ran = passing.some((record) =>
      input.commands.some((command) => squash(JSON.stringify(record.input ?? "")).includes(squash(command).slice(0, 60))),
    )
    if (!ran) return "LEARN_UNVERIFIED: no succeeded cited call ran one of the listed commands"
  }
  return { status: "verified", evidence: cited.map(describe).join("; "), validatedAt: new Date(latest).toISOString(), calls: cited.map((r) => r.id) }
}

export const slug = (title: string) =>
  squash(title).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80) || "untitled"

export function job(input: Pick<Input, "kind" | "title">) {
  return "learn:" + input.kind + ":" + slug(input.title)
}

/** Identity of the knowledge itself; re-learning the same content with fresh evidence is a duplicate. */
export function fingerprint(input: Input) {
  return createHash("sha256")
    .update(JSON.stringify([input.kind, slug(input.title), squash(input.problem), squash(input.solution), input.commands.map(squash)]))
    .digest("hex")
}

export function event(
  scope: Pick<Scope, "project" | "repository">,
  input: Input,
  verified: Verified,
  context: { sessionID: string; seq: number; recordedBy: string },
): Event {
  const content = JSON.stringify({
    schema: "watoom.knowledge.v2",
    kind: input.kind,
    status: verified.status,
    title: squash(input.title),
    project: scope.project,
    environment: input.environment,
    problem: input.problem,
    solution: input.solution,
    commands: input.commands,
    prerequisites: input.prerequisites,
    expected_results: input.expectedResults,
    validation_evidence: verified.evidence,
    evidence_calls: verified.calls,
    source_session: context.sessionID,
    source_commit: input.sourceCommit ?? "",
    validated_at: verified.validatedAt,
    failure_conditions: input.failureConditions,
    rollback: input.rollback,
    confidence: verified.status === "verified" ? "verified-by-execution" : "diagnostic",
    fingerprint: fingerprint(input),
    recorded_by: context.recordedBy,
    embedding_model: EMBEDDING_MODEL,
  })
  if (Buffer.byteLength(content) > 8192) throw Error("LEARN_TOO_LARGE: shorten solution, commands or evidence")
  return { scope: { ...scope, agent: AGENT }, job: job(input), seq: context.seq, kind: "checkpoint", content }
}

export type Knowledge = {
  id: string
  job: string
  seq: number
  kind: Kind
  status: "verified" | "diagnostic"
  title: string
  solution: string
  commands: string[]
  rollback: string
  validatedAt: string
  sourceSession: string
}

export function read(value: Envelope): Knowledge | undefined {
  if (!value.job.startsWith("learn:") || value.scope.agent !== AGENT) return
  try {
    const parsed = JSON.parse(value.content)
    if (parsed?.schema !== "watoom.knowledge.v2" || !KINDS.includes(parsed.kind)) return
    return {
      id: value.id,
      job: value.job,
      seq: value.seq,
      kind: parsed.kind,
      status: parsed.status === "verified" ? "verified" : "diagnostic",
      title: String(parsed.title),
      solution: String(parsed.solution),
      commands: Array.isArray(parsed.commands) ? parsed.commands.map(String) : [],
      rollback: String(parsed.rollback ?? ""),
      validatedAt: String(parsed.validated_at ?? ""),
      sourceSession: String(parsed.source_session ?? ""),
    }
  } catch {
    return
  }
}

/** Latest revision per knowledge job, verified first, in retrieval order. */
export function current(values: readonly Knowledge[]) {
  const latest = new Map<string, Knowledge>()
  for (const value of values) {
    const prior = latest.get(value.job)
    if (!prior || value.seq > prior.seq) latest.set(value.job, value)
  }
  const order = values.map((value) => value.job).filter((value, index, all) => all.indexOf(value) === index)
  const ranked = order.map((key) => latest.get(key)!)
  return [...ranked.filter((value) => value.status === "verified"), ...ranked.filter((value) => value.status !== "verified")]
}

/** Short provenance-bearing summaries within a character budget (about 4 characters per token). */
export function render(values: readonly Knowledge[], budget: number) {
  const lines: string[] = []
  let used = 0
  for (const value of values) {
    const command = value.commands[0] ? " Command: " + squash(value.commands[0]).slice(0, 160) + "." : ""
    const line =
      "- [" + value.kind + (value.status === "verified" ? ", verified " : ", diagnostic ") + value.validatedAt.slice(0, 10) + "] " +
      squash(value.title) + ": " + squash(value.solution).slice(0, 360) + command +
      " (ref " + value.job + "#" + value.seq + ", session " + value.sourceSession + ")"
    if (used + line.length > budget) break
    lines.push(line)
    used += line.length
  }
  return lines
}
