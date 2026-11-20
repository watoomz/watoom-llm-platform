import { describe, expect, test } from "bun:test"
import { Database } from "bun:sqlite"
import fs from "node:fs/promises"
import path from "node:path"
import { tmpdir } from "node:os"
import { Learning } from "../src/watoom/learning"
import { AutoRecall } from "../src/watoom/auto-recall"
import { toolRecords } from "../src/watoom/native-memory"
import { Message } from "@opencode/ai/effect"

const input: Learning.Input = {
  kind: "procedure",
  title: "Restart the game worker timer",
  environment: "homelab",
  problem: "worker stuck",
  solution: "restart the timer",
  commands: ["systemctl restart watoom-game-worker.timer"],
  prerequisites: [],
  expectedResults: [],
  failureConditions: [],
  rollback: "",
  evidence: [{ tool: "shell", contains: "watoom-game-worker.timer" }],
}
const record = (id: string, command: string, exit: number | undefined, status: "completed" | "error" = "completed", time = 1) =>
  ({ sessionID: "ses_a", id, name: "shell", status, input: { command }, exit, time }) satisfies Learning.ToolRecord

describe("verified learning", () => {
  test("success needs a cited call that actually ran a listed command and succeeded", () => {
    const ok = Learning.verify(input, [record("c1", "systemctl restart watoom-game-worker.timer", 0)])
    expect(typeof ok === "object" && ok.status).toBe("verified")
    expect(Learning.verify(input, [record("c1", "systemctl restart watoom-game-worker.timer", 1)])).toContain("LEARN_UNVERIFIED")
    expect(Learning.verify(input, [record("c1", "systemctl restart watoom-game-worker.timer", undefined, "error")])).toContain("LEARN_UNVERIFIED")
    expect(Learning.verify({ ...input, evidence: [{ tool: "shell", contains: "status" }] }, [record("c2", "systemctl status x", 0)])).toContain("ran one of the listed commands")
    expect(Learning.verify(input, [])).toContain("LEARN_EVIDENCE_NOT_FOUND")
  })
  test("recall keeps only knowledge that shares a distinctive query word; a project-only query is an overview", () => {
    const k = (job: string, title: string, solution: string, kind: Learning.Knowledge["kind"] = "decision") =>
      ({ id: job, job, seq: 1, kind, status: "verified", title, environment: "", problem: "", solution, commands: [], rollback: "", validatedAt: "2026-11-21", sourceSession: "ses_a" }) satisfies Learning.Knowledge
    const worker = k("learn:compatibility:worker", "Godot game worker: from_project flag works", "Prefer from_project:true")
    const elite = k("learn:decision:elite", "Elite chance-rolls use a dedicated rng stream", "elite_rng seeded from the injected rng")
    const repo = "/data/ai/projects/games/idle-rpg-strip"
    expect(Learning.relevant([worker, elite], "idle RPG strip milestone achievement toast save", repo)).toEqual([])
    expect(Learning.relevant([worker, elite], "elite monster spawn rng", repo)).toEqual([elite])
    expect(Learning.relevant([worker, elite], "idle-rpg-strip", repo)).toEqual([worker, elite])
    const failure = { ...k("learn:known-failure:x", "Ticket action done is invalid", "use action:status", "known-failure"), problem: "tickets request rejected" }
    const line = Learning.render([failure], 4000)[0]
    expect(line).toContain("Symptom: tickets request rejected Fix: use action:status")
    expect(line).not.toContain("ses_a")
  })
  test("a missing citation names the calls the model could cite instead", () => {
    const miss = Learning.verify(input, [record("c1", "journalctl -u game-worker -n 20", 0)])
    expect(miss).toContain("LEARN_EVIDENCE_NOT_FOUND")
    expect(miss).toContain("journalctl -u game-worker -n 20")
    const none = Learning.verify({ ...input, evidence: [{ tool: "write", contains: "x" }] }, [record("c1", "ls", 0)])
    expect(none).toContain("no write call in this session; cite one of: shell")
  })
  test("commands and evidence with quotes or backslashes match the call exactly as it was typed", () => {
    const command = 'curl -s --max-time 15 -o /dev/null -w "HTTP %{http_code}\\n" -X PUT --data-binary "r15 memory verify" "http://host:18080/up/r15-verify.txt"'
    const quoted = { ...input, commands: [command], evidence: [{ tool: "shell", contains: "r15-verify.txt" }] }
    const ok = Learning.verify(quoted, [record("c1", command, 0)])
    expect(typeof ok === "object" && ok.status).toBe("verified")
    expect(Learning.verify({ ...quoted, evidence: [{ tool: "shell", contains: '-w "HTTP %{http_code}' }] }, [record("c1", command, 0)])).toMatchObject({ status: "verified" })
    expect(Learning.verify(quoted, [record("c1", 'curl -s "http://host:18080/up/other.txt" # r15-verify.txt', 0)])).toContain("ran one of the listed commands")
  })
  test("the latest matching call is the evidence", () => {
    const value = Learning.verify(input, [record("old", "systemctl restart watoom-game-worker.timer", 0, "completed", 1), record("new", "systemctl restart watoom-game-worker.timer", 3, "completed", 2)])
    expect(value).toContain("LEARN_UNVERIFIED")
  })
  test("known failures need a real failure and stay diagnostic", () => {
    const failure = { ...input, kind: "known-failure" as const }
    expect(Learning.verify(failure, [record("c1", "systemctl restart watoom-game-worker.timer", 0)])).toContain("LEARN_FAILURE_EVIDENCE_REQUIRED")
    const diag = Learning.verify(failure, [record("c1", "systemctl restart watoom-game-worker.timer", 5)])
    expect(typeof diag === "object" && diag.status).toBe("diagnostic")
  })
  test("a worker job that ran and FAILED is failure evidence (T-0109)", () => {
    const part = (id: string, metadata: unknown) => ({ type: "tool", id, name: "watoom_game_worker", time: { completed: 5 }, state: { status: "completed", input: { action: "status", operation: "godot-game", job: "verify-4" }, metadata } })
    const row = { session_id: "ses_a", time_created: 1, data: JSON.stringify({ content: [part("w1", { status: "FAILED", worker_result: { status: "FAIL" } }), part("w2", { status: "COMPLETED", worker_result: { status: "PASS" } })] }) }
    const [failedJob, passedJob] = toolRecords(row)
    expect(failedJob.failed).toBe(true)
    expect(passedJob.failed).toBeUndefined()
    const failure = { ...input, kind: "known-failure" as const, commands: [], evidence: [{ tool: "watoom_game_worker", contains: "verify-4" }] }
    const diag = Learning.verify(failure, [failedJob])
    expect(typeof diag === "object" && diag.status).toBe("diagnostic")
    expect(Learning.verify(failure, [passedJob])).toContain("LEARN_FAILURE_EVIDENCE_REQUIRED")
    expect(Learning.verify({ ...input, commands: [], evidence: failure.evidence }, [failedJob])).toContain("LEARN_UNVERIFIED")
  })
  test("bounds, kinds and secrets are rejected", () => {
    expect(Learning.validate(input)).toBeUndefined()
    expect(Learning.validate({ ...input, kind: "magic" as never })).toBe("LEARN_KIND_INVALID")
    expect(Learning.validate({ ...input, evidence: [] })).toContain("LEARN_EVIDENCE_REQUIRED")
    expect(Learning.validate({ ...input, solution: "use ghp_" + "a".repeat(30) })).toContain("LEARN_SENSITIVE_CONTENT")
    expect(Learning.validate({ ...input, solution: "password: hunter22" })).toContain("LEARN_SENSITIVE_CONTENT")
    expect(Learning.validate({ ...input, sourceCommit: "zz" })).toBe("LEARN_COMMIT_INVALID")
  })
  test("the stored record carries the structured format and runtime evidence", () => {
    const verified = Learning.verify(input, [record("c1", "systemctl restart watoom-game-worker.timer", 0)]) as Learning.Verified
    const event = Learning.event({ project: "p", repository: "/r" }, input, verified, { sessionID: "ses_a", seq: 1, recordedBy: "watoom-builder" })
    const body = JSON.parse(event.content)
    expect(event.scope.agent).toBe(Learning.AGENT)
    expect(event.job).toBe("learn:procedure:restart-the-game-worker-timer")
    for (const key of ["kind", "title", "project", "environment", "problem", "solution", "commands", "prerequisites", "expected_results", "validation_evidence", "source_session", "source_commit", "validated_at", "failure_conditions", "rollback", "confidence", "embedding_model"])
      expect(body).toHaveProperty(key)
    expect(body.validation_evidence).toContain("shell c1 succeeded exit 0")
    expect(body.embedding_model).toBe("BAAI/bge-small-en-v1.5")
  })
  test("recall keeps the latest revision, verified first, within budget", () => {
    const k = (job: string, seq: number, status: "verified" | "diagnostic") =>
      ({ id: job + seq, job, seq, kind: "procedure", status, title: job, solution: "s".repeat(50), commands: [], rollback: "", validatedAt: "2026-10-29T00:00:00Z", sourceSession: "ses" }) satisfies Learning.Knowledge
    const current = Learning.current([k("a", 1, "verified"), k("b", 1, "diagnostic"), k("a", 2, "verified"), k("c", 1, "verified")])
    expect(current.map((x) => x.job + x.seq)).toEqual(["a2", "c1", "b1"])
    const lines = Learning.render(current, 400)
    expect(lines.join("\n").length).toBeLessThanOrEqual(400)
    expect(lines[0]).toContain("ref a#2")
  })
})

describe("automatic recall triggers", () => {
  const call = (id: string, name: string, input: unknown) => Message.assistant([{ type: "tool-call", id, name, input }])
  const result = (id: string, name: string, value: unknown, type: "json" | "error" = "json", metadata?: Record<string, unknown>) =>
    Message.make({ role: "tool", content: [{ type: "tool-result", id, name, result: { type, value }, metadata }] })
  test("new user turns trigger once per distinct text; short nudges do not", () => {
    const a = AutoRecall.trigger([Message.user("Deploy the BGE embeddings service to llama-cpp")])
    expect(a?.reason).toBe("task")
    expect(AutoRecall.trigger([Message.user("Deploy the BGE embeddings service to llama-cpp")])?.key).toBe(a?.key)
    expect(AutoRecall.trigger([Message.user("continue")])).toBeUndefined()
  })
  test("risky commands and worker requests trigger; reads do not", () => {
    expect(AutoRecall.trigger([call("t1", "shell", { command: "kubectl -n x rollout restart deploy/y" }), result("t1", "shell", "ok")])?.reason).toBe("command")
    expect(AutoRecall.trigger([call("t2", "shell", { command: "kubectl get pods" }), result("t2", "shell", "ok")])).toBeUndefined()
    expect(AutoRecall.trigger([call("t3", "watoom_game_worker", { action: "request", operation: "capture-scene", job: "v6" }), result("t3", "watoom_game_worker", "QUEUED")])?.reason).toBe("command")
    expect(AutoRecall.trigger([call("t4", "read", { path: "a" }), result("t4", "read", "x")])).toBeUndefined()
  })
  test("failed tools trigger recovery recall with the error text", () => {
    const failed = AutoRecall.trigger([call("f1", "shell", { command: "make" }), result("f1", "shell", "boom", "json", { exit: 2 })])
    expect(failed?.reason).toBe("failure")
    expect(AutoRecall.trigger([call("f2", "watoom_game_worker", {}), result("f2", "watoom_game_worker", "CAPTURE_MANIFEST_INVALID", "error")])?.query).toContain("CAPTURE_MANIFEST_INVALID")
  })
  test("notes are empty without knowledge and the cache is bounded", () => {
    expect(AutoRecall.note("task", [])).toBeUndefined()
    expect(AutoRecall.note("failure", ["- x"])).toContain("failure just seen")
    const cache = AutoRecall.cache(2)
    cache.set("a", { key: "1" });cache.set("b", { key: "2" });cache.set("c", { key: "3" })
    expect(cache.get("a")).toBeUndefined()
    expect(cache.get("c")?.key).toBe("3")
  })
})

test("learning through the native memory service: verification, dedup, revision, recall and isolation", async () => {
  const root = await fs.mkdtemp(path.join(tmpdir(), "watoom-learning-"))
  const records = new Database(":memory:")
  records.run("CREATE TABLE memories(id INTEGER PRIMARY KEY,content TEXT,project TEXT,agent TEXT,latest INTEGER DEFAULT 1)")
  let up = true
  const server = Bun.serve({ hostname: "127.0.0.1", port: 0, async fetch(request) {
    if (!up) return Response.json({ error: "down" }, { status: 503 })
    const body = await request.json() as { content?: string; project: string; agentId: string }
    if (new URL(request.url).pathname.endsWith("/remember")) {
      records.query("UPDATE memories SET latest=0 WHERE content=? AND project=?").run(body.content!, body.project)
      const result = records.query("INSERT INTO memories(content,project,agent) VALUES(?,?,?)").run(body.content!, body.project, body.agentId)
      return Response.json({ success: true, memory: { id: "fixture-" + result.lastInsertRowid, content: body.content, project: body.project, agentId: body.agentId } })
    }
    const rows = records.query("SELECT id,content FROM memories WHERE latest=1 AND project=? AND agent=? ORDER BY id DESC").all(body.project, body.agentId) as { id: number; content: string }[]
    return Response.json({ results: rows.map((row) => ({ observation: { id: "fixture-" + row.id, narrative: row.content } })) })
  } })
  const run = async (mode: string) => {
    const child = Bun.spawn([process.execPath, path.join(import.meta.dirname, "fixture/watoom-memory-process.ts"), path.join(root, "learning.sqlite"), mode, root],
      { env: { ...process.env, AGENTMEMORY_URL: server.url.origin, AGENTMEMORY_SECRET: "", GOMAXPROCS: "2", WATOOM_MEMORY_TEST_PROJECT: "learning-project" }, stdout: "pipe", stderr: "pipe" })
    const [code, out, error] = await Promise.all([child.exited, new Response(child.stdout).text(), new Response(child.stderr).text()])
    if (code) throw Error(error.slice(-3000))
    return JSON.parse(out.trim().split("\n").at(-1)!)
  }
  try {
    const r = await run("learning")
    expect(r.verified).toMatchObject({ ok: true, value: { status: "verified", duplicate: false, state: "observed" } })
    expect(r.duplicate).toMatchObject({ ok: true, value: { duplicate: true, id: r.verified.value.id } })
    expect(r.revised).toMatchObject({ ok: true, value: { status: "verified", duplicate: false } })
    expect(r.revised.value.id).not.toBe(r.verified.value.id)
    expect(r.failedOnly.ok).toBe(false)
    expect(r.failedOnly.error).toContain("LEARN_UNVERIFIED")
    expect(r.wrongCommand.error).toContain("ran one of the listed commands")
    expect(r.missing.error).toContain("LEARN_EVIDENCE_NOT_FOUND")
    expect(r.knownFailure).toMatchObject({ ok: true, value: { status: "diagnostic" } })
    expect(r.secret.ok).toBe(false)
    expect(r.knowledgeRows).toEqual([
      { job: "learn:known-failure:bge-playbook-wait-all-flag-fails", seq: 1, state: "observed" },
      { job: "learn:procedure:deploy-bge-embeddings-service", seq: 1, state: "observed" },
      { job: "learn:procedure:deploy-bge-embeddings-service", seq: 2, state: "observed" },
    ])
    expect(r.recalled[0]).toContain("[procedure, verified")
    expect(r.recalled[0]).toContain("Service and NetworkPolicy apply first")
    expect(r.recalled[0]).toContain("ref learn:procedure:deploy-bge-embeddings-service#2")
    expect(r.recalled.some((line: string) => line.includes("#1 "))).toBe(false)
    expect(r.recalled.at(-1)).toContain("[known-failure, diagnostic")
    expect(r.otherProject).toEqual([])
    up = false
    expect((await run("learning-offline")).recalled).toEqual([])
  } finally {
    await server.stop(true)
    records.close()
  }
}, 60000)
