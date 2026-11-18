// Retention for AgentMemory: delete aged automatic event telemetry, nothing else.
//
// Why: watoom-code records every session event ("session.step.ended", "session.tool.called", ...) as a
// kind=checkpoint memory. That is ~10k entries a day; the originals live in the app's own SQLite outbox. On
// 2026-11-16 the store held 56,810 memories (97% of them these events, 107 MB in one file); listing it never
// finished inside the engine's 180 s limit, so the search index could not be built and every save queued
// behind two full scans (minutes each). Keeping the store small keeps save/search at tens of milliseconds.
//
// What is deleted: a memory whose envelope has kind "checkpoint", a job shaped ses_<id>[:child]:evt_<id> and an
// inner event starting "session.", older than RETENTION_HOURS. Explicit /remember saves (job explicit:...),
// knowledge revisions, specialist intents, learn:/milestone: records, completions and compactions are kept.
//
// Cost: a delete rewrites the memories collection, so it is O(store size). That is why this runs hourly with a
// short retention (the store stays a few MB) instead of daily with a long one.
//
// Env: AGENTMEMORY_URL, AGENTMEMORY_SECRET, RETENTION_HOURS (default 12; the CronJob sets 6), MAX_DELETES (default 3000),
//      TIME_BUDGET_S (default 1500), DRY_RUN=1 to only count.
const base = process.env.AGENTMEMORY_URL || "http://agentmemory.watoom-code.svc.cluster.local:3111"
const secret = process.env.AGENTMEMORY_SECRET || ""
const hours = Number(process.env.RETENTION_HOURS || 12)
const maxDeletes = Number(process.env.MAX_DELETES || 3000)
const budgetMs = Number(process.env.TIME_BUDGET_S || 1500) * 1000
const dry = process.env.DRY_RUN === "1"
const headers = { "Content-Type": "application/json", ...(secret ? { Authorization: "Bearer " + secret } : {}) }
const JOB = /^ses_[A-Za-z0-9]+(:child)?:evt_[A-Za-z0-9]+$/

function telemetry(memory) {
  try {
    const envelope = JSON.parse(memory.content)
    if (envelope.kind !== "checkpoint" || !JOB.test(envelope.job || "")) return false
    const inner = JSON.parse(envelope.content)
    return typeof inner.event === "string" && inner.event.startsWith("session.")
  } catch {
    return false
  }
}

async function main() {
  if (!Number.isFinite(hours) || hours < 1) throw new Error("RETENTION_HOURS must be >= 1")
  const started = Date.now()
  const response = await fetch(base + "/agentmemory/memories?latest=true", { headers, signal: AbortSignal.timeout(120000) })
  if (!response.ok) throw new Error("list failed: HTTP " + response.status)
  const { memories } = await response.json()
  const cutoff = Date.now() - hours * 3600 * 1000
  const doomed = memories
    .filter((memory) => telemetry(memory) && Date.parse(memory.createdAt) < cutoff)
    .sort((a, b) => Date.parse(a.createdAt) - Date.parse(b.createdAt))
  console.log(JSON.stringify({ total: memories.length, eligible: doomed.length, hours, dry }))
  if (dry) return
  let deleted = 0
  let failures = 0
  for (const memory of doomed.slice(0, maxDeletes)) {
    if (Date.now() - started > budgetMs) break
    try {
      const result = await fetch(base + "/agentmemory/forget", {
        method: "POST",
        headers,
        body: JSON.stringify({ memoryId: memory.id }),
        signal: AbortSignal.timeout(60000),
      })
      if (!result.ok) throw new Error("HTTP " + result.status)
      deleted++
      failures = 0
    } catch (error) {
      if (++failures >= 3) throw new Error("stopping after 3 consecutive failures: " + error.message)
    }
  }
  console.log(JSON.stringify({ deleted, remaining: doomed.length - deleted, seconds: Math.round((Date.now() - started) / 1000) }))
}
main().catch((error) => {
  console.error("prune failed:", error.message)
  process.exit(1)
})
