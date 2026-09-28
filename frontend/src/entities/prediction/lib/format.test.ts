import { describe, expect, it } from "vitest"

import { formatProbability, formatProbabilityDelta } from "./format"

describe("probability format", () => {
  it("shows percentages with a decimal below ten percent", () => {
    expect(formatProbability(0.891)).toBe("89%")
    expect(formatProbability(0.0123)).toBe("1.2%")
  })

  it("shows deltas in percentage points", () => {
    expect(formatProbabilityDelta(0.031)).toBe("+3.1 п.п.")
    expect(formatProbabilityDelta(-0.004)).toBe("−0.4 п.п.")
  })
})
