import { describe, expect, it } from "vitest"

import { formatShare, liftOverRandom, listPrecision, parseObjectLevel, payback, paybackVerdict } from "./object-level"

const FIXTURE = {
  period: "2026H1",
  unit: "object-day",
  generated_at: "2026-10-01T06:00:00Z",
  models: [
    {
      id: "phase_24h",
      label: "Потеря питания",
      scenario: "power_loss",
      horizon_hours: 24,
      objects_per_day: 18.9,
      base_rate: 0.585,
      avg_precision: 0.78,
      roc_auc: 0.73,
      top_k: { "3": 0.778, "5": 0.752, "10": 0.693 },
      recall_at_precision_0_7: 0.41,
      precision_at_recall_0_5: 0.74,
      curve: [
        { top_k: 1, precision: 0.81, recall: 0.07, alerts_per_day: 1 },
        { top_k: 2, precision: 0.79, recall: 0.13, alerts_per_day: 2 },
      ],
    },
    {
      id: "fan_72h",
      label: null,
      scenario: "ventilation",
      horizon_hours: 72,
      objects_per_day: null,
      base_rate: null,
      avg_precision: null,
      roc_auc: null,
      top_k: { "3": null, "5": 0.4 },
      recall_at_precision_0_7: null,
      precision_at_recall_0_5: null,
      curve: [{ top_k: 3, precision: 0.5, recall: 0.1, alerts_per_day: 3 }],
    },
    { id: "pump_72h", scenario: "flooding" },
  ],
  incidents: {
    fire: { label: "Пожарный инцидент", rule: "дым и тепловой датчик за 30 мин", per_year: { "2019": 123 }, objects: 30 },
  },
}

const DEFAULTS = { cost: 15_000, loss: 300_000, share: 0.4 }

describe("parseObjectLevel", () => {
  const report = parseObjectLevel(FIXTURE)

  it("maps the report and tolerates nulls and missing curves", () => {
    expect(report.period).toBe("2026H1")
    expect(report.models).toHaveLength(3)
    const [phase, fan, pump] = report.models
    expect(phase.objectsPerDay).toBe(18.9)
    expect(phase.recallAtPrecision70).toBe(0.41)
    expect(phase.curve[1]).toEqual({ topK: 2, precision: 0.79, recall: 0.13, alertsPerDay: 2 })
    expect(fan.label).toBe("Отказ вентилятора")
    expect(fan.baseRate).toBeNull()
    expect(pump.curve).toEqual([])
    expect(pump.topK).toEqual({})
  })

  it("rejects a payload without model ids", () => {
    expect(() => parseObjectLevel({ models: [{ scenario: "fire" }] })).toThrow()
  })

  it("reads list precision from top_k and falls back to the curve", () => {
    const [phase, fan, pump] = report.models
    expect(listPrecision(phase, 5)).toBe(0.752)
    expect(listPrecision(fan, 3)).toBe(0.5)
    expect(listPrecision(fan, 10)).toBeNull()
    expect(listPrecision(pump, 5)).toBeNull()
  })

  it("compares top-3 list precision with the event share", () => {
    const [phase, fan] = report.models
    expect(liftOverRandom(phase)).toBeCloseTo(1.33, 2)
    expect(liftOverRandom(fan)).toBeNull()
  })
})

describe("payback", () => {
  it("computes break-even precision and yearly effect for the default prices", () => {
    const result = payback({ size: 5, precision: 0.752, ...DEFAULTS })
    expect(result.breakEven).toBeCloseTo(0.125, 6)
    expect(result.yearlyEffect).toBeCloseTo(365 * (5 * 0.752 * 0.4 * 300_000 - 5 * 15_000), 2)
    expect(result.yearlyEffect).toBeCloseTo(137_313_000, 0)
    expect(paybackVerdict(0.752, result)).toBe(
      "Окупается: точность списка 75,2%, порог 12,5%. Каждая проверка в среднем приносит больше, чем стоит."
    )
  })

  it("turns negative when the list is less precise than the threshold", () => {
    const result = payback({ size: 3, precision: 0.1, ...DEFAULTS })
    expect(result.yearlyEffect).toBeCloseTo(-3_285_000, 0)
    expect(paybackVerdict(0.1, result)).toMatch(/^Не окупается: точность списка 10%, порог 12,5%/)
  })

  it("breaks even exactly at the threshold", () => {
    const result = payback({ size: 10, precision: 0.125, ...DEFAULTS })
    expect(result.yearlyEffect).toBeCloseTo(0, 6)
    expect(paybackVerdict(0.125, result)).toMatch(/^Выходит в ноль/)
  })

  it("handles missing precision, zero loss and unreachable thresholds", () => {
    expect(payback({ size: 5, precision: null, ...DEFAULTS }).yearlyEffect).toBeNull()
    expect(paybackVerdict(null, payback({ size: 5, precision: null, ...DEFAULTS }))).toMatch(/нет точности/)
    const noLoss = payback({ size: 5, precision: 0.7, cost: 15_000, loss: 0, share: 0.4 })
    expect(noLoss.breakEven).toBeNull()
    expect(paybackVerdict(0.7, noLoss)).toMatch(/Укажите ущерб/)
    const expensive = payback({ size: 5, precision: 0.9, cost: 200_000, loss: 300_000, share: 0.4 })
    expect(expensive.breakEven).toBeGreaterThan(1)
    expect(paybackVerdict(0.9, expensive)).toMatch(/даже при безошибочном списке/)
  })

  it("formats shares in Russian notation", () => {
    expect(formatShare(0.752)).toBe("75%")
    expect(formatShare(0.125, 1)).toBe("12,5%")
    expect(formatShare(null)).toBe("—")
  })
})
