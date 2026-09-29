import type { AssetStatus, AssetType, EventType, RiskLevel, ScoreType } from "../model/types"

export const RISK_HIGH = 65
export const RISK_MEDIUM = 40
export const RISK_WATCH = 30

export function levelFromScore(score: number): RiskLevel {
  if (score >= RISK_HIGH) return "high"
  if (score >= RISK_MEDIUM) return "medium"
  return "low"
}

export function statusFromScore(score: number): AssetStatus {
  if (score >= RISK_HIGH) return "critical"
  if (score >= RISK_MEDIUM) return "attention"
  return "normal"
}

export function isWatch(score: number) {
  return score >= RISK_WATCH && score < RISK_MEDIUM
}

export const LEVEL_LABEL: Record<RiskLevel, string> = {
  low: "Низкий",
  medium: "Средний",
  high: "Высокий",
}

export const STATUS_LABEL: Record<AssetStatus, string> = {
  normal: "Норма",
  attention: "Внимание",
  critical: "Критично",
  offline: "Офлайн",
}

export const TYPE_LABEL: Record<AssetType, string> = {
  pump: "Насос",
  fan: "Вентилятор",
  smoke: "Дым",
  power: "Питание",
  other: "Датчик",
}

export const TYPE_ORDER: AssetType[] = ["pump", "fan", "smoke", "power", "other"]

export function scoreLabel(type: ScoreType) {
  return type === "calibrated_probability" ? "Оценка вероятности" : "Оценка риска"
}

export function formatScore(score: number, type: ScoreType) {
  return type === "calibrated_probability" ? `${Math.round(score)}%` : `${Math.round(score)}/100`
}

export function formatDelta(delta: number) {
  const rounded = Math.round(delta)
  if (rounded === 0) return "0"
  return rounded > 0 ? `+${rounded}` : `${rounded}`
}

export const EVENT_TYPE_LABEL: Record<EventType, string> = {
  transition: "Переход",
  state_change: "Смена состояния",
  alarm: "Тревога",
  anomaly: "Аномалия",
  failure: "Отказ",
  signal: "Системный сигнал",
}
