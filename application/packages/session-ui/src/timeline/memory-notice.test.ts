import { test, expect } from "bun:test"
import type { SessionMessageInfo } from "@opencode/client/promise"
import { Timeline } from "./projection"
import { timelineNoticeRequired, timelinePresets } from "./detail"
test("explicit memory receipts and provenance stay visible in every timeline preset", () => {
  const message: SessionMessageInfo = {id:"memory-fixture",type:"synthetic",text:"verified receipt and provenance",
    description:"/recall",metadata:{source:"agentmemory-command",command:"recall"},time:{created:0}}
  expect(timelineNoticeRequired(message)).toBe(true)
  for(const preset of timelinePresets) {
    const result=Timeline.constructSessionMessageRows([message],false,{type:"idle"},undefined,false,false,undefined,preset.value)
    expect(result.rows.some(row=>row._tag==="Notice" && row.messageID===message.id)).toBe(true)
    expect(result.rows.some(row=>row._tag==="AssistantPart")).toBe(false)
  }
})
