export function formatProbability(probability: number): string {
  const percent = probability <= 1 ? probability * 100 : probability
  return `${percent < 10 ? percent.toFixed(1) : Math.round(percent)}%`
}

export function formatProbabilityDelta(delta: number): string {
  const points = Math.abs(delta) <= 1 ? delta * 100 : delta
  const sign = points > 0 ? "+" : points < 0 ? "−" : ""
  return `${sign}${Math.abs(points).toFixed(1)} п.п.`
}
