import type { PredictionScenario } from "@/entities/prediction"

export type JournalDecision = "awaiting_decision" | "crew_dispatched" | "no_dispatch" | "completed" | "cancelled"

export type JournalEntry = {
  id: string
  createdAt: number
  assetId: string
  location: string | null
  scenario: PredictionScenario
  modelId: string | null
  score: number | null
  horizonHours: number | null
  predictionTime: number | null
  priority: string
  status: string
  decision: JournalDecision
  outcome: string | null
  resultNote: string
  assignee: string
  completedAt: number | null
}

export type ScenarioFeedback = {
  scenario: PredictionScenario
  forecasts: number
  decided: number
  confirmed: number
  rejected: number
  confirmationRate: number | null
}

export type JournalSummary = {
  total: number
  pending: number
  inWork: number
  decided: number
  byScenario: ScenarioFeedback[]
}

export const DECISION_LABEL: Record<JournalDecision, string> = {
  awaiting_decision: "Ожидает решения",
  crew_dispatched: "Выезд бригады",
  no_dispatch: "Без выезда",
  completed: "Отработано",
  cancelled: "Отменено",
}

export const JOURNAL_OUTCOME_LABEL: Record<string, string> = {
  confirmed_issue: "Инцидент подтверждён",
  maintenance_performed: "Выполнено ТО",
  no_issue_found: "Норма, проблем нет",
  monitoring_required: "Мониторинг",
  false_or_irrelevant_signal: "Ложное срабатывание",
  other: "Другое",
}
