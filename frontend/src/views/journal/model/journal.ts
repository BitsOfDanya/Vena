import type { JournalDecision, JournalEntry } from "@/entities/journal"
import type { PredictionScenario } from "@/entities/prediction"

export type JournalFilter = {
  query: string
  scenario: PredictionScenario | "all"
  decision: JournalDecision | "all"
}

export function filterJournal(rows: JournalEntry[], filter: JournalFilter): JournalEntry[] {
  const query = filter.query.trim().toLowerCase()
  return rows.filter(
    (row) =>
      (filter.scenario === "all" || row.scenario === filter.scenario) &&
      (filter.decision === "all" || row.decision === filter.decision) &&
      (!query ||
        [row.id, row.assetId, row.location ?? "", row.modelId ?? "", row.resultNote, row.assignee]
          .join(" ")
          .toLowerCase()
          .includes(query))
  )
}

function cell(value: unknown): string {
  const text = value === null || value === undefined ? "" : String(value)
  const safe = /^[\s]*[=+@-]/u.test(text) ? "'" + text : text
  return `"${safe.replaceAll('"', '""')}"`
}

export function exportJournalCsv(rows: JournalEntry[]): string {
  const header = [
    "Action",
    "Created (UTC)",
    "Asset",
    "Location",
    "Scenario",
    "Model",
    "Score",
    "Horizon (h)",
    "Prediction time (UTC)",
    "Status",
    "Decision",
    "Outcome",
    "Note",
    "Assignee",
    "Closed (UTC)",
  ]
  const iso = (value: number | null) => (value === null ? "" : new Date(value).toISOString())
  const lines = rows.map((row) =>
    [
      row.id,
      iso(row.createdAt),
      row.assetId,
      row.location,
      row.scenario,
      row.modelId,
      row.score === null ? "" : row.score.toFixed(4),
      row.horizonHours,
      iso(row.predictionTime),
      row.status,
      row.decision,
      row.outcome,
      row.resultNote,
      row.assignee,
      iso(row.completedAt),
    ]
      .map(cell)
      .join(";")
  )
  return "﻿" + [header.map(cell).join(";"), ...lines].join("\r\n")
}
