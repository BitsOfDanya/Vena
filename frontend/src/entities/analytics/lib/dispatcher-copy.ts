
const SCENARIO_TITLE: Record<string, string> = {
  flooding: "Отказ насоса / подтопление",
  ventilation: "Отказ вентилятора",
  fire: "Пожар / дым",
  power_loss: "Потеря питания",
  equipment: "Отказ оборудования",
}

const HELD_OUT_PERIOD: Record<string, string> = {
  "2026H1": "январе–июне 2026",
  "2025-2026H1": "2025 — июне 2026",
}

export function scenarioTitle(scenario: string) {
  return SCENARIO_TITLE[scenario] ?? scenario
}

export function horizonPhrase(hours: number) {
  if (hours >= 72) return "в ближайшие 3 суток"
  if (hours >= 24) return "в ближайшие сутки"
  if (hours >= 1) return `в ближайшие ${Math.round(hours)} ч`
  return `в ближайшие ${Math.max(1, Math.round(hours * 60))} мин`
}

export function modelWhatPredicts(model: { target: string | null; sensor: string | null; scenario: string; horizonHours: number }) {
  if (model.target) return model.target
  const base = scenarioTitle(model.scenario)
  return `${base}: ${horizonPhrase(model.horizonHours)}`
}

export function heldOutPeriodPhrase(period: string | null | undefined) {
  if (!period) return "проверочном периоде"
  return HELD_OUT_PERIOD[period] ?? period
}

export function topKTrustLine(precisionTop5: number | null | undefined, horizonHours: number) {
  if (precisionTop5 == null) return null
  const ofFive = Math.round(precisionTop5 * 5)
  const term = horizonHours >= 72 ? "за 3 суток" : horizonHours >= 24 ? "за сутки" : `за ${horizonHours} ч`
  return `Из 5 каналов с наибольшим риском в сутки ${ofFive} отказывают ${term}`
}

export function dailyTopKLines(dailyTopK: Record<string, number> | null | undefined, horizonHours: number) {
  if (!dailyTopK) return []
  const term = horizonHours >= 72 ? "за 3 суток" : horizonHours >= 24 ? "за сутки" : `за ${horizonHours} ч`
  return (["5", "10", "20"] as const)
    .filter((key) => dailyTopK[key] != null)
    .map((key) => {
      const rate = dailyTopK[key]!
      const ofK = Math.round(rate * Number(key))
      return `Из ${key} с наибольшим риском в сутки ${ofK} отказывают ${term} (${Math.round(rate * 100)} %)`
    })
}

export function calibrationLine(ece: number | null | undefined) {
  if (ece == null) return null
  if (ece <= 0.05) {
    return "Когда модель пишет 30 %, событие случается примерно в 30 случаях из 100"
  }
  return `Калибровка: средняя ошибка вероятности ${(ece * 100).toFixed(1)} п.п.`
}

export function leadTimeLine(medianHours: number | null | undefined, alertPrecision: number | null | undefined) {
  const parts: string[] = []
  if (alertPrecision != null) {
    parts.push(`${Math.round(alertPrecision * 100)} % тревог высокого уровня подтверждаются`)
  }
  const lead = leadHorizonPhrase(medianHours)
  if (lead) parts.push(lead)
  return parts.length ? parts.join(", ") : null
}

export function leadHorizonPhrase(medianHours: number | null | undefined, prefix = "предупреждение в среднем за") {
  if (medianHours == null || medianHours <= 0) return null
  if (medianHours < 1) {
    return `${prefix} ${Math.max(1, Math.round(medianHours * 60))} мин`
  }
  return `${prefix} ${Math.round(medianHours)} ч`
}

export function verifiedLine(period: string | null | undefined) {
  return `Проверено на ${heldOutPeriodPhrase(period)}, модель их не видела`
}
