import { describe, expect, test } from "bun:test"
import { milestone } from "../src/tool/plugin/watoom-memory"

describe("watoom_memory_recall memories", () => {
  test("keeps recorded milestones as one compact line and drops lifecycle events", () => {
    const recorded = {
      job: "milestone:t0113-tests",
      content: JSON.stringify({ schema: "watoom.milestone.v1", requestID: "t0113-tests", kind: "milestone", summary: "Milestone tests pass", sourceRefs: ["godot-game-out/t0113-test-2/result.json"], nextAction: "close T-0113", confidence: "VERIFIED" }),
    }
    expect(milestone(recorded)).toBe("[milestone, VERIFIED] Milestone tests pass | next: close T-0113 | refs: godot-game-out/t0113-test-2/result.json")
    expect(milestone({ job: "ses_x:evt_y", content: JSON.stringify({ event: "session.step.ended", references: [] }) })).toBeUndefined()
    expect(milestone({ job: "milestone:bad", content: "{not json" })).toBeUndefined()
  })
})
