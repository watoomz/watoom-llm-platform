import { describe, expect, test } from "bun:test"
import { Schema } from "effect"
import { SessionLoop } from "../src/session/runner/loop"
import { SessionMessage } from "../src/session/message"

const decode = Schema.decodeUnknownSync(SessionMessage.Info)
const tool = (name = "execute", input: Record<string, string> = { code: "probe()" }, result = "unchanged") =>
  decode({
    id: "msg_test",
    sessionID: "ses_test",
    type: "assistant",
    time: { created: 1 },
    agent: "watoom-workflow",
    model: { providerID: "test", id: "test" },
    content: [
      {
        type: "tool",
        id: "call_test",
        name,
        time: { created: 1 },
        state: { status: "completed", input, content: [{ type: "text", text: result }] },
      },
    ],
  })
describe("durable no-progress loop boundary", () => {
  test("stops identical results after three calls, not two", () => {
    expect(SessionLoop.reason([tool(), tool()])).toBeUndefined()
    expect(SessionLoop.reason([tool(), tool(), tool()])).toContain("three attempts")
  })
  test("detects alternating cycles and ignores sleeps", () => {
    const a = tool("execute", { code: "a()" })
    const b = tool("execute", { code: "b()" })
    const sleep = tool("shell", { command: "sleep 60" })
    expect(SessionLoop.reason([a, sleep, b, a, sleep, b, a, sleep, b])).toBeDefined()
  })
  test("reworded Code Mode scripts that call no tool are no progress", () => {
    const noop = (code: string, result: string) =>
      decode({
        id: "msg_test",
        sessionID: "ses_test",
        type: "assistant",
        time: { created: 1 },
        agent: "watoom-workflow",
        model: { providerID: "test", id: "test" },
        content: [
          {
            type: "tool",
            id: "call_test",
            name: "execute",
            time: { created: 1 },
            state: { status: "completed", input: { code }, content: [{ type: "text", text: result }], metadata: { toolCalls: [] } },
          },
        ],
      })
    expect(SessionLoop.reason([noop("return 'ok'", "ok"), noop("// direct\nreturn 'calling now'", "calling now")])).toBeUndefined()
    expect(
      SessionLoop.reason([noop("return 'ok'", "ok"), noop("return 'done'", "done"), noop("return 'final'", "final")]),
    ).toContain("three attempts")
    const real = tool("execute", { code: "await tools.read({path:'a'})" }, "file a")
    expect(SessionLoop.reason([noop("return 'ok'", "ok"), real, noop("return 'x'", "x")])).toBeUndefined()
  })
  test("wait calls neither count toward nor break a cycle", () => {
    const wait = tool("wait", { seconds: "30" }, "Waited 30s.")
    const nap = tool("sleep", { seconds: "30" }, "Waited 30s.")
    expect(SessionLoop.reason([nap, nap, nap, nap, nap, nap])).toBeUndefined()
    expect(SessionLoop.reason([wait, wait, wait, wait, wait, wait])).toBeUndefined()
    expect(SessionLoop.reason([tool(), wait, tool(), wait, tool()])).toBeDefined()
  })
  test("changed results and changed arguments allow work", () => {
    expect(SessionLoop.reason([tool(), tool(), tool("execute", { code: "probe()" }, "new evidence")])).toBeUndefined()
    expect(SessionLoop.reason([tool(), tool(), tool("execute", { code: "repair()" })])).toBeUndefined()
  })
  test("running jobs are not false loop failures", () => {
    const poll = tool("execute", { code: "status()" }, JSON.stringify({ job_id: "owned", status: "running" }))
    expect(SessionLoop.reason([poll, poll, poll, poll])).toBeUndefined()
    expect(SessionLoop.reason([tool(), tool(), poll, tool()])).toBeUndefined()
  })
  test("new user input resets the boundary", () => {
    const user = decode({
      id: "msg_user",
      sessionID: "ses_test",
      type: "user",
      time: { created: 1 },
      text: "Try the repaired route",
    })
    expect(SessionLoop.reason([tool(), tool(), user, tool()])).toBeUndefined()
  })
  test("serialized restart history retains protection", () => {
    const saved = JSON.parse(
      JSON.stringify([tool(), tool(), tool()].map((value) => Schema.encodeSync(SessionMessage.Info)(value))),
    ).map(decode)
    expect(SessionLoop.reason(saved)).toBeDefined()
  })
  test("external synthetic evidence releases an old loop without resetting future protection", () => {
    const evidence = decode({
      id: "msg_evidence",
      sessionID: "ses_test",
      type: "synthetic",
      time: { created: 2 },
      text: "Existing regression finished: 159/160; inspect origin height",
      metadata: { source: "operator-blocker-audit" },
    })
    expect(SessionLoop.reason([tool(), tool(), tool(), evidence])).toBeUndefined()
    expect(SessionLoop.reason([tool(), tool(), tool(), evidence, tool(), tool()])).toBeUndefined()
    expect(SessionLoop.reason([tool(), tool(), tool(), evidence, tool(), tool(), tool()])).toContain("three attempts")
  })
  test("internal handoff notices cannot erase the same stalled cycle", () => {
    const notice = decode({
      id: "msg_notice",
      sessionID: "ses_test",
      type: "synthetic",
      time: { created: 2 },
      text: "Historical handoff",
      metadata: { source: "handoff-recovery" },
    })
    expect(SessionLoop.reason([tool(), tool(), tool(), notice])).toContain("three attempts")
  })
  test("queued native jobs report waiting and recover on a durable completion", () => {
    for (const name of ["watoom_game_worker", "watoom_asset_capture", "watoom_rig_game_job"]) {
      const poll = tool(
        name,
        { action: "status", job: "owned" },
        JSON.stringify({ request_id: "owned-request", status: "QUEUED" }),
      )
      expect(SessionLoop.reason([poll, poll])).toBeUndefined()
      expect(SessionLoop.reason([poll, poll, poll])).toContain("not an execution failure")
      expect(SessionLoop.reason([poll, poll, poll])).toContain("owned-request (QUEUED)")
      const completion = decode({
        id: "msg_completion",
        sessionID: "ses_test",
        type: "synthetic",
        time: { created: 2 },
        text: "Read the completed receipt",
        metadata: { source: "rig-stage-completion" },
      })
      const restored = JSON.parse(
        JSON.stringify([poll, poll, poll, completion].map((value) => Schema.encodeSync(SessionMessage.Info)(value))),
      ).map(decode)
      expect(SessionLoop.reason(restored)).toBeUndefined()
    }
  })
})
