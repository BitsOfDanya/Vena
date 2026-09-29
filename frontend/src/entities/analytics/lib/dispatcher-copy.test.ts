import { describe, expect, it } from "vitest"

import { horizonPhrase, leadHorizonPhrase, leadTimeLine } from "./dispatcher-copy"

describe("horizonPhrase", () => {
  it("formats multi-day and hour horizons in Russian", () => {
    expect(horizonPhrase(72)).toBe("в ближайшие 3 суток")
    expect(horizonPhrase(24)).toBe("в ближайшие сутки")
    expect(horizonPhrase(6)).toBe("в ближайшие 6 ч")
  })

  it("formats sub-hour horizons as minutes", () => {
    expect(horizonPhrase(0.5)).toBe("в ближайшие 30 мин")
  })
})

describe("leadHorizonPhrase", () => {
  it("returns null for missing or non-positive leads", () => {
    expect(leadHorizonPhrase(null)).toBeNull()
    expect(leadHorizonPhrase(0)).toBeNull()
  })

  it("uses minutes below one hour", () => {
    expect(leadHorizonPhrase(0.25, "предупреждает за ~")).toBe("предупреждает за ~ 15 мин")
  })

  it("joins with alert precision in leadTimeLine", () => {
    expect(leadTimeLine(0.5, 0.8)).toBe(
      "80 % тревог высокого уровня подтверждаются, предупреждение в среднем за 30 мин"
    )
  })
})
