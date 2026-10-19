import type {
  IncidentKind,
  IncidentRecord,
  ObjectModelMeta,
  ObjectNowcastMeta,
  ObjectRiskScenario,
} from "../model/types"

export const INCIDENT_KIND_LABEL: Record<IncidentKind, string> = {
  power: "Питание",
  flood: "Подтопление",
  fire: "Пожар",
}

export const OBJECT_SCENARIOS: { value: ObjectRiskScenario; label: string }[] = [
  { value: "power_loss", label: "Питание" },
  { value: "flooding", label: "Подтопление" },
  { value: "fire", label: "Пожар" },
]

export function formatPercent(value: number | null | undefined) {
  if (value == null) return "—"
  return `${Math.round(value * 100)} %`
}

export function qualityCaption(meta: Pick<ObjectModelMeta, "precisionTop3" | "baseRate">, period: string) {
  if (meta.precisionTop3 == null) return null
  const base = meta.baseRate != null ? ` при доле объектов с событием ${formatPercent(meta.baseRate)}` : ""
  return `Точность топ-3 на ${period} — ${formatPercent(meta.precisionTop3)}${base}`
}

export function nowcastCaption(nowcast: ObjectNowcastMeta | null, period: string) {
  if (!nowcast || nowcast.shareTop3 == null) return null
  const random = nowcast.objects ? ` при ${formatPercent(3 / nowcast.objects)} для случайного порядка` : ""
  return `За ${nowcast.horizonHours} ч до начала подтопления станция была в топ-3 в ${formatPercent(nowcast.shareTop3)} случаев на ${period}${random}`
}

export function incidentFlags(record: Pick<IncidentRecord, "temperatureConfirmed" | "maxMinutes">) {
  const flags: string[] = []
  if (record.temperatureConfirmed) flags.push("рост температуры")
  if (record.maxMinutes != null && record.maxMinutes > 30) flags.push("дольше 30 мин")
  return flags
}

export function daysSinceText(days: number | null) {
  if (days == null) return "—"
  const rounded = Math.max(0, Math.round(days))
  return rounded === 0 ? "сегодня" : String(rounded)
}
