import { test, expect } from "bun:test"
import fs from "node:fs/promises"
import os from "node:os"
import path from "node:path"
test("native corrections and consolidation preserve lineage, exclude obsolete facts and survive exact retry", async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "native-knowledge-"))
  const records: { id: string; content: string; project: string; agentId: string }[] = []
  const server = Bun.serve({
    hostname: "127.0.0.1",
    port: 0,
    async fetch(request) {
      const body = (await request.json()) as { content: string; project: string; agentId: string; query?: string }
      if (new URL(request.url).pathname.endsWith("/remember")) {
        const memory = { id: "fixture-" + records.length, ...body }
        records.push(memory)
        return Response.json({ success: true, memory })
      }
      const found = records.filter(
        (x) =>
          x.project === body.project && x.agentId === body.agentId && (!body.query || x.content.includes(body.query)),
      )
      return Response.json({ results: found.map((x) => ({ observation: { id: x.id, narrative: x.content } })) })
    },
  })
  try {
    const child = Bun.spawn(
      [
        process.execPath,
        path.join(import.meta.dirname, "fixture/watoom-memory-process.ts"),
        path.join(directory, "native.sqlite"),
        "knowledge",
        directory,
      ],
      {
        env: { ...process.env, AGENTMEMORY_URL: server.url.origin, AGENTMEMORY_SECRET: "", GOMAXPROCS: "2" },
        stdout: "pipe",
        stderr: "pipe",
      },
    )
    const [code, out, error] = await Promise.all([
      child.exited,
      new Response(child.stdout).text(),
      new Response(child.stderr).text(),
    ])
    if (code) throw Error(error.slice(-4000))
    const result = JSON.parse(out.trim().split("\n").at(-1)!)
    expect(result.corrected.state).toBe("observed")
    expect(result.duplicate.id).toBe(result.corrected.id)
    expect(result.conflict).toBe("Failure")
    expect(result.isolated).toBe("Failure")
    expect(result.before.some((x: { id: string }) => x.id === result.a.id)).toBe(false)
    expect(result.before.some((x: { id: string }) => x.id === result.corrected.id)).toBe(true)
    expect(result.merged.some((x: { id: string }) => x.id === result.consolidated.id)).toBe(true)
    expect(result.after).toHaveLength(0)
    expect(records).toHaveLength(5)
    expect(result.status.outbox.uncertain).toBe(0)
    expect(result.status.outbox.lastObserved).toBeGreaterThan(0)
  } finally {
    await server.stop(true)
  }
}, 60000)

test("mandatory memory refuses missing configuration before session execution", async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "native-mandatory-"))
  const env: Record<string, string | undefined> = { ...process.env, WATOOM_MEMORY_REQUIRED: "true", GOMAXPROCS: "2" }
  delete env.AGENTMEMORY_URL
  const child = Bun.spawn(
    [
      process.execPath,
      path.join(import.meta.dirname, "fixture/watoom-memory-process.ts"),
      path.join(directory, "native.sqlite"),
      "emit",
      directory,
    ],
    { env, stdout: "pipe", stderr: "pipe" },
  )
  const [code, error] = await Promise.all([child.exited, new Response(child.stderr).text()])
  expect(code).not.toBe(0)
  expect(error).toContain("Mandatory AgentMemory endpoint is missing")
}, 30000)
test("uncertain correction keeps a durable checkpoint and never returns a known obsolete fact", async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "native-knowledge-outage-"))
  const records: { id: string; content: string; project: string; agentId: string }[] = []
  const server = Bun.serve({
    hostname: "127.0.0.1",
    port: 0,
    async fetch(request) {
      const body = (await request.json()) as { content: string; project: string; agentId: string; query?: string }
      if (new URL(request.url).pathname.endsWith("/remember")) {
        if (records.length === 2) return Response.json({ error: "fixture outage" }, { status: 503 })
        const memory = { id: "fixture-" + records.length, ...body }
        records.push(memory)
        return Response.json({ success: true, memory })
      }
      return Response.json({
        results: records
          .filter((x) => !body.query || x.content.includes(body.query))
          .map((x) => ({ observation: { id: x.id, narrative: x.content } })),
      })
    },
  })
  try {
    const child = Bun.spawn(
      [
        process.execPath,
        path.join(import.meta.dirname, "fixture/watoom-memory-process.ts"),
        path.join(directory, "native.sqlite"),
        "knowledge-outage",
        directory,
      ],
      {
        env: { ...process.env, AGENTMEMORY_URL: server.url.origin, WATOOM_MEMORY_REQUIRED: "true", GOMAXPROCS: "2" },
        stdout: "pipe",
        stderr: "pipe",
      },
    )
    const [code, out, error] = await Promise.all([
      child.exited,
      new Response(child.stdout).text(),
      new Response(child.stderr).text(),
    ])
    if (code) throw Error(error.slice(-3000))
    const result = JSON.parse(out.trim().split("\n").at(-1)!)
    expect(result.corrected.state).toBe("uncertain")
    expect(result.found).toHaveLength(0)
    expect(result.status.required).toBe(true)
    expect(result.status.outbox.uncertain).toBe(1)
    expect(result.status.warnings).toContain("delivery-uncertain")
  } finally {
    await server.stop(true)
  }
}, 30000)
