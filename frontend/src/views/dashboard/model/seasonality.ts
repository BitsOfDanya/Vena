import type { SeasonalityRow } from "@/entities/analytics"

export function seasonalIndex(row: SeasonalityRow): number[] {
  const mean = row.months.reduce((sum, value) => sum + value, 0) / row.months.length
  return row.months.map((value) => (mean > 0 ? value / mean : 0))
}

export function cellShade(index: number): number {
  const clamped = Math.min(Math.max(index, 0.5), 1.5)
  return Math.round(6 + ((clamped - 0.5) / 1.0) * 76)
}
