import { describe, expect, it } from "vitest"

import type { JournalEntry } from "@/entities/journal"

import { exportJournalCsv, filterJournal } from "./journal"

const base: JournalEntry = {
  id: "A-1",
  createdAt: Date.parse("2026-09-28T10:00:00Z"),
  assetId: "179172",
  location: "Объект 16 · 2.1.1",
  scenario: "power_loss",
  modelId: "phase_24h",
  score: 0.96,
  horizonHours: 24,
  predictionTime: Date.parse("2026-06-30T23:59:06Z"),
  priority: "high",
  status: "dismissed",
  decision: "no_dispatch",
  outcome: "false_or_irrelevant_signal",
  resultNote: "=Ложное срабатывание",
  assignee: "Дежурный инженер",
  completedAt: null,
}

describe("forecast journal", () => {
  it("filters by scenario, decision and free text", () => {
    const rows = [base, { ...base, id: "A-2", scenario: "fire" as const, decision: "crew_dispatched" as const, location: "Объект 9" }]
    expect(filterJournal(rows, { query: "", scenario: "fire", decision: "all" }).map((row) => row.id)).toEqual(["A-2"])
    expect(filterJournal(rows, { query: "объект 16", scenario: "all", decision: "all" }).map((row) => row.id)).toEqual(["A-1"])
    expect(filterJournal(rows, { query: "", scenario: "all", decision: "crew_dispatched" })).toHaveLength(1)
  })

  it("exports feedback rows without executable spreadsheet formulas", () => {
    const csv = exportJournalCsv([base])
    expect(csv.startsWith("﻿")).toBe(true)
    expect(csv).toContain('"\'=Ложное срабатывание"')
    expect(csv).toContain('"0.9600"')
  })
})
