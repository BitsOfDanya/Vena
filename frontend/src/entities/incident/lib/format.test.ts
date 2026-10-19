import { describe, expect, it } from "vitest"

import { parseIncidentRegistry, parseObjectRisks } from "../api/service"
import { daysSinceText, incidentFlags, nowcastCaption, qualityCaption } from "./format"

describe("incident formatting", () => {
  it("builds the quality caption from object model meta", () => {
    expect(qualityCaption({ precisionTop3: 0.74, baseRate: 0.54 }, "январе–июне 2026")).toBe(
      "Точность топ-3 на январе–июне 2026 — 74 % при доле объектов с событием 54 %",
    )
    expect(qualityCaption({ precisionTop3: 0.5, baseRate: null }, "проверке")).toBe("Точность топ-3 на проверке — 50 %")
    expect(qualityCaption({ precisionTop3: null, baseRate: 0.5 }, "проверке")).toBeNull()
  })

  it("describes the short flood list against random order", () => {
    const nowcast = {
      modelId: "object_flood_6h",
      horizonHours: 6,
      period: "2026H1",
      shareTop3: 0.65,
      ruleShareTop3: 0.51,
      objects: 18,
    }
    expect(nowcastCaption(nowcast, "январе–июне 2026")).toBe(
      "За 6 ч до начала подтопления станция была в топ-3 в 65 % случаев на январе–июне 2026 при 17 % для случайного порядка",
    )
    expect(nowcastCaption(null, "проверке")).toBeNull()
  })

  it("flags temperature growth and long floods", () => {
    expect(incidentFlags({ temperatureConfirmed: true, maxMinutes: 45 })).toEqual(["рост температуры", "дольше 30 мин"])
    expect(incidentFlags({ temperatureConfirmed: null, maxMinutes: 30 })).toEqual([])
  })

  it("formats days since the last incident", () => {
    expect(daysSinceText(0.2)).toBe("сегодня")
    expect(daysSinceText(3)).toBe("3")
    expect(daysSinceText(null)).toBe("—")
  })
})

describe("incident payload parsing", () => {
  it("maps the registry and drops records without a start", () => {
    const registry = parseIncidentRegistry({
      available: true,
      detail: "",
      journal_end: "2026-06-30",
      restricted: true,
      kinds: [
        {
          kind: "fire",
          label: "Пожарный инцидент",
          rule: "Дым",
          total: 3,
          objects: 1,
          per_year: [{ year: "2025", count: 3 }],
          top_objects: [{ object_id: "5122", object_name: "Объект 5122", count: 3 }],
          temperature_confirmed: 1,
        },
      ],
      recent: [
        {
          kind: "fire",
          label: "Пожарный инцидент",
          object_id: "5122",
          object_name: "Объект 5122",
          start: "2026-06-29T14:03:11+03:00",
          max_minutes: null,
        },
        {
          kind: "fire",
          label: "Пожарный инцидент",
          object_id: "5122",
          object_name: "Объект 5122",
          start: "не дата",
        },
      ],
    })
    expect(registry.restricted).toBe(true)
    expect(registry.kinds[0].topObjects[0]).toEqual({
      objectId: "5122",
      objectName: "Объект 5122",
      count: 3,
    })
    expect(registry.recent).toHaveLength(1)
    expect(registry.recent[0].start).toBe(Date.parse("2026-06-29T11:03:11Z"))
  })

  it("maps the morning object list with empty defaults", () => {
    const list = parseObjectRisks({
      available: true,
      items: [
        {
          object_id: "5122",
          object_name: "ДУ объект Альфа",
          scenario: "power_loss",
          model_id: "object_power_24h",
          model_label: "Отключение питания объекта",
          probability: 0.73,
          rank: 1,
          history: { events_7d: 3, events_30d: 12, days_since: 2 },
        },
      ],
    })
    expect(list.detail).toBe("")
    expect(list.models).toEqual([])
    expect(list.items[0].history).toEqual({
      events1d: null,
      events7d: 3,
      events30d: 12,
      events90d: null,
      daysSince: 2,
    })
    expect(list.items[0].probability6h).toBeNull()
    const flood = parseObjectRisks({
      available: true,
      models: [
        {
          model_id: "object_flood_24h",
          label: "Подтопление",
          scenario: "flooding",
          nowcast: { model_id: "object_flood_6h", horizon_hours: 6, share_top3: 0.65, objects: 18 },
        },
      ],
      items: [
        {
          object_id: "3388",
          object_name: "Станция",
          scenario: "flooding",
          model_id: "object_flood_24h",
          model_label: "Подтопление",
          probability: 0.45,
          rank: 1,
          probability_6h: 0.21,
        },
      ],
    })
    expect(flood.items[0].probability6h).toBe(0.21)
    expect(flood.models[0].nowcast).toMatchObject({ horizonHours: 6, shareTop3: 0.65, objects: 18, period: null })
    expect(
      parseObjectRisks({
        available: false,
        detail: "Утренний список объектов ещё не рассчитан",
      }).items,
    ).toEqual([])
  })
})
