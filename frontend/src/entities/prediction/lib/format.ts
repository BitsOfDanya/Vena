export function formatProbability(probability: number): string {
  const percent = probability * 100
  return `${percent < 10 ? percent.toFixed(1) : Math.round(percent)}%`
}

export function formatProbabilityDelta(delta: number): string {
  const points = delta * 100
  const sign = points > 0 ? "+" : points < 0 ? "−" : ""
  return `${sign}${Math.abs(points).toFixed(1)} п.п.`
}
