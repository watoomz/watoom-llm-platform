import { expect, test } from "bun:test"
import { hasCustomAgent, resolveAgent } from "./agent"

test("hasCustomAgent detects only explicitly custom agents", () => {
  expect(hasCustomAgent([{ native: true }, { native: false }])).toBe(true)
  expect(hasCustomAgent([{ native: true }, {}])).toBe(false)
})

const agents = [{ name: "plan" }, { name: "build" }, { name: "custom" }]

const rows: { name: string; agents: { name: string }[]; requested?: string; expected: string }[] = [
  { name: "the requested available agent", agents, requested: "custom", expected: "custom" },
  { name: "build without a request", agents, requested: undefined, expected: "build" },
  { name: "build for a missing agent", agents, requested: "missing", expected: "build" },
  {
    name: "the first agent when build is unavailable",
    agents: [{ name: "custom" }],
    requested: "missing",
    expected: "custom",
  },
]

test.each(rows)("resolveAgent uses $name", (row) => {
  expect(resolveAgent(row.agents, row.requested)?.name).toBe(row.expected)
})


test("detects V2 custom agents without a legacy native flag", () => {
  expect(hasCustomAgent([{ name: "build" }, { name: "plan" }])).toBe(false)
  expect(hasCustomAgent([{ name: "build" }, { name: "watoom-workflow" }])).toBe(true)
  expect(hasCustomAgent([{ name: "watoom-builder", native: true }])).toBe(false)
})

test("honors the configured default without overriding an explicit choice", () => {
  expect(resolveAgent(agents, undefined, "custom")?.name).toBe("custom")
  expect(resolveAgent(agents, "plan", "custom")?.name).toBe("plan")
  expect(resolveAgent(agents, undefined, "missing")?.name).toBe("build")
})
