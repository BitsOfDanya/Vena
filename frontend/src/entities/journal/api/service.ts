import { z } from "zod"

import { apiFetch } from "@/shared/api/http"

import type { JournalEntry, JournalSummary } from "../model/types"

const SCENARIOS = ["flooding", "fire", "power_loss", "ventilation", "equipment"] as const
const DECISIONS = ["awaiting_decision", "crew_dispatched", "no_dispatch", "completed", "cancelled"] as const

const time = z.iso.datetime({ offset: true })
const scenario = z.enum(SCENARIOS).catch("equipment")

const EntrySchema = z.object({
  id: z.string(),
  created_at: time,
  asset_id: z.string(),
  location: z.string().nullable(),
  scenario,
  model_id: z.string().nullable(),
  score: z.number().nullable(),
  horizon_hours: z.number().int().nullable(),
  prediction_time: time.nullable(),
  priority: z.string(),
  status: z.string(),
  decision: z.enum(DECISIONS),
  outcome: z.string().nullable(),
  result_note: z.string(),
  assignee: z.string(),
  completed_at: time.nullable(),
})

const SummarySchema = z.object({
  total: z.number(),
  pending: z.number(),
  in_work: z.number(),
  decided: z.number(),
  by_scenario: z.array(
    z.object({
      scenario,
      forecasts: z.number(),
      decided: z.number(),
      confirmed: z.number(),
      rejected: z.number(),
      confirmation_rate: z.number().nullable(),
    })
  ),
})

const parseTime = (value: string | null) => (value ? Date.parse(value) : null)

export async function getJournal(): Promise<JournalEntry[]> {
  const items = z.array(EntrySchema).parse(await apiFetch<unknown>("/api/v1/journal?limit=2000"))
  return items.map((item) => ({
    id: item.id,
    createdAt: Date.parse(item.created_at),
    assetId: item.asset_id,
    location: item.location,
    scenario: item.scenario,
    modelId: item.model_id,
    score: item.score,
    horizonHours: item.horizon_hours,
    predictionTime: parseTime(item.prediction_time),
    priority: item.priority,
    status: item.status,
    decision: item.decision,
    outcome: item.outcome,
    resultNote: item.result_note,
    assignee: item.assignee,
    completedAt: parseTime(item.completed_at),
  }))
}

export async function getJournalSummary(): Promise<JournalSummary> {
  const item = SummarySchema.parse(await apiFetch<unknown>("/api/v1/journal/summary"))
  return {
    total: item.total,
    pending: item.pending,
    inWork: item.in_work,
    decided: item.decided,
    byScenario: item.by_scenario.map((row) => ({
      scenario: row.scenario,
      forecasts: row.forecasts,
      decided: row.decided,
      confirmed: row.confirmed,
      rejected: row.rejected,
      confirmationRate: row.confirmation_rate,
    })),
  }
}
