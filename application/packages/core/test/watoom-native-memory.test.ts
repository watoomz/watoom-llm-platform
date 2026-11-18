import { expect, test } from "bun:test"
import { Database } from "bun:sqlite"
import fs from "node:fs/promises"
import path from "node:path"
import { tmpdir } from "node:os"

test("real native event, process death before acknowledgment, reconciliation and project isolation", async () => {
  const root = await fs.mkdtemp(path.join(tmpdir(), "watoom-native-memory-"))
  const records = new Database(path.join(root, "disposable-agentmemory.sqlite"))
  records.run("CREATE TABLE memories(id INTEGER PRIMARY KEY,content TEXT,project TEXT,agent TEXT,latest INTEGER DEFAULT 1)")
  let calls = 0
  let behavior: "hold" | "success" | "fail" = "hold"
  const server = Bun.serve({ hostname: "127.0.0.1", port: 0, async fetch(request) {
    const body = await request.json() as { content?: string; project: string; agentId: string }
    if (new URL(request.url).pathname.endsWith("/remember")) {
      calls++
      if (behavior === "fail") return Response.json({ error: "fixture outage" }, { status: 503 })
      // Models AgentMemory supersession: identical same-project content leaves one latest copy.
      records.query("UPDATE memories SET latest=0 WHERE content=? AND project=?").run(body.content!, body.project)
      const result = records.query("INSERT INTO memories(content,project,agent) VALUES(?,?,?)").run(body.content!, body.project, body.agentId)
      if (behavior === "hold") return new Promise<Response>(() => {})
      return Response.json({ success: true, memory: { id: "fixture-" + result.lastInsertRowid, content: body.content, project: body.project, agentId: body.agentId } })
    }
    return Response.json({ results: (records.query("SELECT id,content FROM memories WHERE latest=1").all() as { id: number; content: string }[]).map((row) => ({ observation: { id: "fixture-" + row.id, narrative: row.content } })) })
  } })
  const children: ReturnType<typeof Bun.spawn>[] = []
  const launch = (db: string, mode: string) => {
    const child = Bun.spawn([process.execPath, path.join(import.meta.dirname, "fixture/watoom-memory-process.ts"), db, mode, root], { env: { ...process.env, AGENTMEMORY_URL: server.url.origin, AGENTMEMORY_SECRET: "", GOMAXPROCS: "2", WATOOM_MEMORY_TEST_PROJECT: path.basename(db) }, stdout: "pipe", stderr: "pipe" })
    children.push(child)
    return child
  }
  const complete = async (child: ReturnType<typeof launch>) => {
    const [code, out, error] = await Promise.all([child.exited, new Response(child.stdout).text(), new Response(child.stderr).text()])
    if (code !== 0) throw Error(error.slice(-3000))
    return JSON.parse(out.trim().split("\n").at(-1)!) as { rows: { state: string; attempts: number }[]; retrieved: number; isolated: number }
  }
  try {
    const database = path.join(root, "native.sqlite")
    const crashed = launch(database, "emit")
    for (let i = 0; i < 800 && calls === 0; i++) await Bun.sleep(25)
    if (calls === 0 && crashed.exitCode !== null) throw Error(await new Response(crashed.stderr).text())
    expect(calls).toBe(1)
    const before = new Database(database, { readonly: true })
    expect(before.query("SELECT state FROM _watoom_outbox").get()).toEqual({ state: "sending" })
    before.close()
    crashed.kill("SIGKILL")
    await crashed.exited
    behavior = "success"
    const recovered = await complete(launch(database, "recover"))
    // Recovery re-sends the identical envelope once (exact-key reconciliation, no hash search).
    expect(recovered.rows).toEqual([{ state: "observed", attempts: 2 }])
    expect(recovered.retrieved).toBe(1)
    expect(recovered.isolated).toBe(0)
    expect(calls).toBe(2)
    expect(records.query("SELECT count(*) AS n FROM memories WHERE latest=1").get()).toEqual({ n: 1 })
    await complete(launch(database, "duplicate"))
    expect(calls).toBe(2)
    const success = await complete(launch(path.join(root, "success.sqlite"), "emit"))
    expect(success.rows[0]?.state).toBe("observed")
    behavior = "fail"
    const offlineDB = path.join(root, "offline.sqlite")
    const failed = await complete(launch(offlineDB, "emit"))
    expect(failed.rows[0]?.state).toBe("uncertain")
    const sent = calls
    const retried = await complete(launch(offlineDB, "recover"))
    // The emitting process already spent the immediate retry; recovery inside the backoff window
    // sends nothing and the row stays unresolved.
    expect(calls).toBe(sent)
    expect(retried.rows[0]).toEqual({ state: "uncertain", attempts: 2 })
  } finally {
    for (const child of children) if (child.exitCode === null) child.kill("SIGKILL")
    await server.stop(true)
    records.close()
    // Disposable fixtures are kept under TMPDIR for evidence, never production memory.
  }
}, 60000)
