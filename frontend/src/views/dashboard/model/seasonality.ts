import type { SeasonalityRow } from "@/entities/analytics"

/** Month rate relative to the scenario's own mean month: 1 is an ordinary month. */
export function seasonalIndex(row: SeasonalityRow): number[] {
  const mean = row.months.reduce((sum, value) => sum + value, 0) / row.months.length
  return row.months.map((value) => (mean > 0 ? value / mean : 0))
}

/** Share of the accent colour mixed into the cell: 0.5× and below is lightest, 1.5× and above darkest. */
export function cellShade(index: number): number {
  const clamped = Math.min(Math.max(index, 0.5), 1.5)
  return Math.round(6 + ((clamped - 0.5) / 1.0) * 76)
}
