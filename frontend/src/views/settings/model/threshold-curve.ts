export type ThresholdLevel = "critical" | "high" | "medium"
export type ThresholdLevels = Record<ThresholdLevel, number>

export type CurvePoint = {
  threshold: number
  probability: number | null
  precision: number | null
  recall: number | null
  channels_per_day: number | null
}

export const LEVELS: ThresholdLevel[] = ["critical", "high", "medium"]

const FALLBACK_STEPS = Array.from({ length: 200 }, (_, index) => (index + 1) / 200)

export function sliderSteps(curve: CurvePoint[]): number[] {
  const steps = curve.map((point) => point.threshold).filter((value) => value > 0 && value <= 1)
  return steps.length ? steps : FALLBACK_STEPS
}

export function nearestIndex(steps: number[], threshold: number): number {
  if (!steps.length) return -1
  let low = 0
  let high = steps.length - 1
  while (low < high) {
    const middle = (low + high) >> 1
    if (steps[middle] < threshold) low = middle + 1
    else high = middle
  }
  if (low > 0 && threshold - steps[low - 1] <= steps[low] - threshold) return low - 1
  return low
}

export function pointAt(curve: CurvePoint[], threshold: number): CurvePoint | null {
  if (!curve.length) return null
  return curve[nearestIndex(curve.map((point) => point.threshold), threshold)] ?? null
}

export function withLevel(levels: ThresholdLevels, level: ThresholdLevel, threshold: number): ThresholdLevels {
  if (level === "critical") return { ...levels, critical: Math.max(threshold, levels.high) }
  if (level === "medium") return { ...levels, medium: Math.min(threshold, levels.high) }
  return { ...levels, high: Math.min(Math.max(threshold, levels.medium), levels.critical) }
}

export function sameLevels(left: ThresholdLevels | null, right: ThresholdLevels | null): boolean {
  if (!left || !right) return left === right
  return LEVELS.every((level) => Math.abs(left[level] - right[level]) < 1e-9)
}
