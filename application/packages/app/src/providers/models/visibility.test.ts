import { describe, expect, test } from "bun:test"
import { isModelVisible } from "./visibility"

describe("model visibility", () => {
  test("keeps configured models with unknown release metadata visible", () => {
    for (const released of [undefined, NaN, 0]) expect(isModelVisible(undefined, false, released)).toBe(true)
  })
  test("preserves explicit user visibility choices", () => {
    expect(isModelVisible("hide", true, 0)).toBe(false)
    expect(isModelVisible("show", false, 1)).toBe(true)
  })
  test("retains catalog recency filtering for known releases", () => {
    expect(isModelVisible(undefined, false, 1)).toBe(false)
    expect(isModelVisible(undefined, true, 1)).toBe(true)
  })
})
