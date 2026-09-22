const ZONE = "Europe/Moscow"

const clock = new Intl.DateTimeFormat("en-GB", {
  timeZone: ZONE,
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
})

const clockSeconds = new Intl.DateTimeFormat("en-GB", {
  timeZone: ZONE,
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
})

const day = new Intl.DateTimeFormat("en-GB", {
  timeZone: ZONE,
  day: "2-digit",
  month: "short",
})

const fullDay = new Intl.DateTimeFormat("en-GB", {
  timeZone: ZONE,
  day: "2-digit",
  month: "short",
  year: "numeric",
})

const dateTimeLocal = new Intl.DateTimeFormat("sv-SE", {
  timeZone: ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
})

export const HOUR = 3_600_000
export const MINUTE = 60_000

export function formatClock(timestamp: number) {
  return clock.format(timestamp)
}

export function formatClockSeconds(timestamp: number) {
  return clockSeconds.format(timestamp)
}

export function formatDay(timestamp: number) {
  return day.format(timestamp).toUpperCase()
}

export function formatFullDay(timestamp: number) {
  return fullDay.format(timestamp).toUpperCase()
}

export function formatDateTime(timestamp: number) {
  return `${formatDay(timestamp)} ${formatClock(timestamp)}`
}

export function toDateTimeLocal(timestamp: number) {
  return dateTimeLocal.format(timestamp).replace(" ", "T")
}

export function fromDateTimeLocal(value: string) {
  const [datePart, timePart] = value.split("T")
  const [year, month, dayOfMonth] = datePart.split("-").map(Number)
  const [hour, minute] = timePart.split(":").map(Number)
  return Date.UTC(year, month - 1, dayOfMonth, hour - 3, minute)
}

export function formatAgo(from: number, to: number) {
  const seconds = Math.max(0, Math.round((to - from) / 1000))
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`
  if (seconds < 86_400) return `${Math.round(seconds / 3600)}h ago`
  return `${(seconds / 86_400).toFixed(1)}d ago`
}

export function formatDuration(hours: number) {
  if (hours < 1) return `${Math.round(hours * 60)} min`
  if (hours < 48) return `${Math.round(hours)} h`
  return `${(hours / 24).toFixed(1)} d`
}
