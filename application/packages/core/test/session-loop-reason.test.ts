import { describe, expect, test } from "bun:test"
import { SessionLoop } from "../src/session/runner/loop"

const user = { type: "user", text: "flash the board" }
const status = (text: string) => ({
  type: "tool",
  name: "watoom_esp32",
  state: { status: "completed", input: { action: "status", job: "flash-1" }, content: [{ type: "text", text }] },
})
const sleep = { type: "tool", name: "sleep", state: { status: "completed", input: { seconds: 90 }, content: [] } }
const assistant = (...content: unknown[]) => ({ type: "assistant", content })
const reason = (...messages: unknown[]) => SessionLoop.reason(messages as never)
const running = JSON.stringify({ request_id: "abc", status: "RUNNING" })

describe("repeated tool cycle guard", () => {
  test("polls of a live external job separated by sleeps are not a repeated cycle", () => {
    expect(
      reason(user, assistant(status(running)), assistant(sleep), assistant(status(running)), assistant(sleep), assistant(status(running))),
    ).toBeUndefined()
  })

  test("a bash sleep between polls counts the same as the sleep tool", () => {
    const bashSleep = { type: "tool", name: "shell", state: { status: "completed", input: { command: "sleep 60" }, content: [] } }
    expect(
      reason(user, assistant(status(running)), assistant(bashSleep), assistant(status(running)), assistant(bashSleep), assistant(status(running))),
    ).toBeUndefined()
  })

  test("identical live-job polls with no wait still stop", () => {
    expect(reason(user, assistant(status(running)), assistant(status(running)), assistant(status(running)))).toContain(
      "External work is still pending: abc (RUNNING)",
    )
  })

  test("an endless sleep-and-poll loop is bounded", () => {
    const cycle = Array.from({ length: 60 }, () => [assistant(sleep), assistant(status(running))]).flat()
    expect(reason(user, ...cycle)).toContain("External work is still pending")
  })

  test("a non-job tool repeated across sleeps still stops", () => {
    const poll = { type: "tool", name: "echo", state: { status: "completed", input: { text: "same" }, content: [{ type: "text", text: "same" }] } }
    expect(reason(user, assistant(poll), assistant(sleep), assistant(poll), assistant(sleep), assistant(poll))).toContain(
      "Repeated tool cycle",
    )
  })
})
