import { afterEach, expect, test } from "bun:test"
import plugin from "./fixture/toolkit-native"
const originalFetch = globalThis.fetch
const originalToken = process.env.WATOOM_TOOLKIT_TOKEN
let requests: Array<{ url: string; init?: RequestInit }> = []
afterEach(() => {
  globalThis.fetch = originalFetch
  if (originalToken === undefined) delete process.env.WATOOM_TOOLKIT_TOKEN
  else process.env.WATOOM_TOOLKIT_TOKEN = originalToken
  requests = []
})
async function fixture() {
  const tools: any[] = []
  let disposed = false
  const cleanup = await plugin.setup({
    tool: {
      transform: async (fn: any) => {
        fn({ add: (tool: any) => tools.push(tool) })
        return {
          dispose: async () => {
            disposed = true
          },
        }
      },
    },
  } as any)
  globalThis.fetch = (async (url: any, init: any) => {
    requests.push({ url: String(url), init })
    return new Response(JSON.stringify(receipt(init?.body ? JSON.parse(String(init.body)).task : "probe")))
  }) as any
  process.env.WATOOM_TOOLKIT_TOKEN = "NONSECRET_TEST_MARKER"
  return { tools, cleanup, disposed: () => disposed }
}
const context = (agent: string) => ({
  agent,
  sessionID: "ses_owned",
  messageID: "msg_owned",
  id: "call_owned",
  signal: new AbortController().signal,
})
test("native registration exposes exactly four fixed tools and disposes", async () => {
  const f = await fixture()
  expect(f.tools.map((t) => t.name)).toEqual([
    "watoom_toolkit_catalog",
    "watoom_toolkit_probe",
    "watoom_toolkit_godotImport",
    "watoom_toolkit_blenderRender",
  ])
  expect(f.tools.every((t) => t.options.codemode === false && t.options.permission === t.name)).toBe(true)
  await f.cleanup()
  expect(f.disposed()).toBe(true)
})
test("leaf rejects all unauthorized execution before network independently of registry filtering", async () => {
  const { tools } = await fixture()
  for (const agent of [
    "watoom-workflow",
    "watoom-investigator",
    "watoom-reviewer",
    "watoom-kali",
    "build",
    "title",
    "summary",
    "compaction",
    "unknown",
  ]) {
    for (const tool of tools) {
      if (
        tool.name.endsWith("catalog") &&
        ["watoom-workflow", "watoom-investigator", "watoom-reviewer"].includes(agent)
      )
        continue
      await expect(tool.execute({ path: "owned/project", frame: 1 }, context(agent))).rejects.toThrow("denied")
    }
  }
  expect(requests).toHaveLength(0)
})
test("builder fixed job preserves machine receipt and sends only approved schema", async () => {
  const { tools } = await fixture()
  const result = await tools[2].execute({ path: "owned/project" }, context("watoom-builder"))
  expect(result.output.id).toBe("abcdef0123456789")
  expect(JSON.parse(result.content)).toEqual(result.output)
  expect(JSON.parse(String(requests[0].init?.body))).toEqual({ task: "godot-import", path: "owned/project" })
  expect(requests[0].init?.redirect).toBe("error")
})
test("missing credentials fail without request or successful BLOCKED text", async () => {
  const { tools } = await fixture()
  delete process.env.WATOOM_TOOLKIT_TOKEN
  await expect(tools[0].execute({}, context("watoom-builder"))).rejects.toThrow("unavailable")
  expect(requests).toHaveLength(0)
})
test("invalid paths and frames fail before network", async () => {
  const { tools } = await fixture()
  for (const path of ["../escape", "/absolute", "owned/../escape", "", "owned\\escape"])
    await expect(tools[2].execute({ path }, context("watoom-builder"))).rejects.toThrow("Invalid")
  for (const frame of [0, 100001, 1.5])
    await expect(tools[3].execute({ path: "owned/file.blend", frame }, context("watoom-builder"))).rejects.toThrow(
      "Invalid",
    )
  expect(requests).toHaveLength(0)
})
test("HTTP errors do not export server response content", async () => {
  const { tools } = await fixture()
  globalThis.fetch = (async () => new Response("NONSECRET_PRIVATE_RESPONSE", { status: 403 })) as any
  await expect(tools[0].execute({}, context("watoom-builder"))).rejects.toThrow("Toolkit HTTP 403")
})
test("invalid JSON and oversized evidence never become successful receipts", async () => {
  const { tools } = await fixture()
  globalThis.fetch = (async () => new Response("invalid-json")) as any
  await expect(tools[0].execute({}, context("watoom-builder"))).rejects.toThrow()
  globalThis.fetch = (async () => new Response("x".repeat(524289))) as any
  await expect(tools[0].execute({}, context("watoom-builder"))).rejects.toThrow("evidence limit")
})

function receipt(task: string) {
  const artifacts =
    task === "godot-import"
      ? [
          ".godot/editor/filesystem_cache10",
          ".godot/global_script_class_cache.cfg",
          ".godot/editor/project_metadata.cfg",
        ].map((path) => ({ root: "workspace", path: "owned/project/" + path, bytes: 8, sha256: "a".repeat(64) }))
      : []
  return {
    id: "abcdef0123456789",
    task,
    status: "PASS",
    exit_code: 0,
    verification: { status: "PASS" },
    contract: {
      id: task === "godot-import" ? "godot-import/4.7.2-cache10/v1" : "process-exit/v1",
      available: true,
      outputs: artifacts.map(({ root, path }) => ({ root, path })),
    },
    artifacts,
  }
}
test("task override and extra input cannot cross the leaf boundary", async () => {
  const { tools } = await fixture()
  for (const input of [
    { path: "owned/project", task: "ansible-syntax" },
    { path: "owned/project", timeout: 180 },
    { path: "owned/project", command: "owned" },
  ])
    await expect(tools[2].execute(input, context("watoom-builder"))).rejects.toThrow("Invalid Toolkit input field")
  expect(requests).toHaveLength(0)
})
test("failed, legacy, unsupported and malformed artifact receipts never complete", async () => {
  const { tools } = await fixture()
  for (const bad of [
    { status: "PASS", exit_code: 0 },
    { ...receipt("godot-import"), status: "FAIL" },
    { ...receipt("godot-import"), exit_code: 1 },
    { ...receipt("godot-import"), artifacts: [] },
    { ...receipt("godot-import"), verification: { status: "FAIL" } },
    { ...receipt("godot-import"), contract: { id: "unsupported", available: true, outputs: [] } },
    {
      ...receipt("godot-import"),
      artifacts: [{ root: "workspace", path: "../escape", bytes: 1, sha256: "a".repeat(64) }],
    },
  ]) {
    globalThis.fetch = Object.assign(async () => new Response(JSON.stringify(bad)), {
      preconnect: originalFetch.preconnect,
    })
    await expect(tools[2].execute({ path: "owned/project" }, context("watoom-builder"))).rejects.toThrow()
  }
})
