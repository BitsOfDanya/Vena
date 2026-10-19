import { formatCount } from "@/shared/lib/plural"

import type { ReplayState, ReplayStatus, ScenarioItem } from "../api/replay"

export const REPLAY_SPEEDS = [
  { value: 2160, label: "6 ч журнала за 10 с" },
  { value: 8640, label: "сутки за 10 с" },
  { value: 360, label: "1 ч за 10 с" },
] as const

export const REPLAY_STATUS_LABEL: Record<ReplayStatus, string> = {
  idle: "Не запущено",
  preparing: "Подготовка",
  running: "Воспроизводится",
  stopping: "Остановка",
  finished: "Завершено",
  failed: "Ошибка",
}

const STAMP = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/

export function formatDataClock(value: string | null | undefined): string | null {
  const match = value ? STAMP.exec(value) : null
  if (!match || match[4] === undefined) return null
  return `${match[3]}.${match[2]} ${match[4]}:${match[5]}`
}

export function formatJournalDate(value: string | null | undefined): string | null {
  const match = value ? STAMP.exec(value) : null
  return match ? `${match[3]}.${match[2]}.${match[1]}` : null
}

export function journalDay(value: string | null | undefined): string | undefined {
  const match = value ? STAMP.exec(value) : null
  return match ? `${match[1]}-${match[2]}-${match[3]}` : undefined
}

export function dayStart(day: string): string {
  return `${day}T00:00:00`
}

export function replayBadgeText(state: ReplayState | undefined): string | null {
  if (!state || (!state.active && state.live)) return null
  const clock = formatDataClock(state.clock)
  return clock ? `Машина времени · данные на ${clock}` : "Машина времени"
}

export function scenarioOption(item: ScenarioItem): string {
  const lead = item.lead.find((point) => point.hours_before === 6)
  return [
    item.label || item.kind,
    `объект ${item.object}`,
    formatJournalDate(item.start),
    lead ? `за 6 ч до начала объект был ${lead.place}-м из ${lead.objects_ranked}` : null,
  ]
    .filter(Boolean)
    .join(" · ")
}

export function simulationText(simulation: ReplayState["simulation"]): string {
  return `подтверждено ${formatCount(simulation.confirmed)} · отклонено ${formatCount(simulation.dismissed)} · оставлено для ручного решения ${formatCount(simulation.left)}`
}
