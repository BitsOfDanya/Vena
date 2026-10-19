import { describe, expect, it } from "vitest"

import { horizonPhrase, leadHorizonPhrase, leadTimeLine, timeToFailureLine } from "./dispatcher-copy"

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

describe("timeToFailureLine", () => {
  it("describes the 20–80 % interval in hours and days", () => {
    expect(timeToFailureLine({ q20: 30, q50: 96, q80: 300 })).toBe(
      "Срок до отказа: около 4 сут; с вероятностью 60 % — от 30 ч до 13 сут"
    )
  })

  it("marks the cap as an open end", () => {
    expect(timeToFailureLine({ q20: 80, q50: 320, q80: 720 })).toBe(
      "Срок до отказа: около 13 сут; с вероятностью 60 % — от 3 сут до 30 сут и более"
    )
    expect(timeToFailureLine(null)).toBeNull()
  })
})
