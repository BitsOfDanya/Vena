import { describe, expect, it } from "vitest"

import { cellShade, seasonalIndex } from "./seasonality"

describe("seasonality", () => {
  it("indexes each month to the scenario mean", () => {
    const index = seasonalIndex({ scenario: "flooding", months: [2, 2, 2, 2, 2, 2, 4, 4, 4, 4, 4, 4] })
    expect(index[0]).toBeCloseTo(2 / 3)
    expect(index[11]).toBeCloseTo(4 / 3)
  })

  it("keeps the shade inside the readable range", () => {
    expect(cellShade(0)).toBe(6)
    expect(cellShade(1)).toBe(44)
    expect(cellShade(9)).toBe(82)
  })
})
