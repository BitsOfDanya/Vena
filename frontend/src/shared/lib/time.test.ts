import { describe, expect, it } from "vitest"

import { formatAgo, formatDay, formatDuration } from "./time"

describe("formatAgo", () => {
  it("uses Russian relative units", () => {
    const now = 1_000_000_000
    expect(formatAgo(now - 15_000, now)).toBe("15 с назад")
    expect(formatAgo(now - 5 * 60_000, now)).toBe("5 мин назад")
    expect(formatAgo(now - 3 * 3_600_000, now)).toBe("3 ч назад")
    expect(formatAgo(now - 2 * 86_400_000, now)).toBe("2.0 дн. назад")
  })
})

describe("formatDay", () => {
  it("formats calendar days in Russian", () => {
    const label = formatDay(Date.parse("2026-09-29T12:00:00Z"))
    expect(label).toMatch(/29/)
    expect(label.toLowerCase()).toMatch(/сен/)
    expect(label).not.toMatch(/SEPT|SEP/i)
  })
})

describe("formatDuration", () => {
  it("uses Russian duration units", () => {
    expect(formatDuration(0.5)).toBe("30 мин")
    expect(formatDuration(5)).toBe("5 ч")
    expect(formatDuration(72)).toBe("3.0 дн.")
  })
})
