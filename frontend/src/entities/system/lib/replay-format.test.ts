import { describe, expect, it } from "vitest"

import type { ReplayState, ScenarioItem } from "../api/replay"
import { dayStart, formatDataClock, formatJournalDate, journalDay, replayBadgeText, scenarioOption, simulationText } from "./replay-format"

const idle: ReplayState = {
  state: "idle",
  mode: null,
  active: false,
  live: true,
  start: null,
  end: null,
  clock: null,
  speed: null,
  sent_events: 0,
  batches: 0,
  started_at: null,
  finished_at: null,
  detail: "",
  simulate_dispatcher: false,
  simulation: { confirmed: 0, dismissed: 0, left: 0 },
  scenario: null,
  ml_history_end: null,
  ml_clock: null,
  journal_from: "2019-02-11T09:58:25",
  journal_to: "2026-06-30T23:59:52",
}

describe("replay clock", () => {
  it("keeps the journal wall time without timezone shifts", () => {
    expect(formatDataClock("2026-06-02T06:00:00")).toBe("02.06 06:00")
    expect(formatDataClock("2026-06-02T23:59:59.123")).toBe("02.06 23:59")
    expect(formatDataClock("2026-06-02")).toBeNull()
    expect(formatDataClock(null)).toBeNull()
    expect(formatJournalDate("2026-06-30T23:19:26")).toBe("30.06.2026")
    expect(journalDay("2026-06-30T23:19:26")).toBe("2026-06-30")
    expect(journalDay(null)).toBeUndefined()
    expect(dayStart("2026-06-01")).toBe("2026-06-01T00:00:00")
  })

  it("shows the badge only while the replay owns the data", () => {
    expect(replayBadgeText(undefined)).toBeNull()
    expect(replayBadgeText(idle)).toBeNull()
    expect(replayBadgeText({ ...idle, state: "running", active: true, live: false, clock: "2026-06-03T12:00:00" })).toBe(
      "Машина времени · данные на 03.06 12:00"
    )
    expect(replayBadgeText({ ...idle, state: "finished", live: false, clock: "2026-06-08T00:00:00" })).toBe(
      "Машина времени · данные на 08.06 00:00"
    )
    expect(replayBadgeText({ ...idle, state: "preparing", active: true, live: false })).toBe("Машина времени")
    expect(replayBadgeText({ ...idle, state: "finished", mode: "scenario", clock: "2026-07-02T23:40:00" })).toBeNull()
  })
})

describe("scenario option", () => {
  const item: ScenarioItem = {
    id: "flood-5675-20260630",
    kind: "flood",
    label: "Подтопление",
    object: "5675",
    start: "2026-06-30T23:19:26",
    end: "2026-06-30T23:40:00",
    channels: 2,
    rule: "",
    before_hours: 24,
    after_hours: 2,
    lead: [
      { hours_before: 24, place: 6, objects_ranked: 18 },
      { hours_before: 6, place: 3, objects_ranked: 18 },
    ],
  }

  it("names the object, the date and the place six hours before", () => {
    expect(scenarioOption(item)).toBe("Подтопление · объект 5675 · 30.06.2026 · за 6 ч до начала объект был 3-м из 18")
    expect(scenarioOption({ ...item, label: "", lead: [] })).toBe("flood · объект 5675 · 30.06.2026")
  })

  it("summarises simulated decisions", () => {
    expect(simulationText({ confirmed: 12, dismissed: 1500, left: 3 })).toBe(
      `подтверждено 12 · отклонено ${new Intl.NumberFormat("ru-RU").format(1500)} · оставлено для ручного решения 3`
    )
  })
})
