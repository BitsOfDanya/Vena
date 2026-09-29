import type { AssetStatus, ForecastHorizon, RiskLevel, ScoreType } from "../model/types"

export type OverlayPrediction = {
  id: string
  assetId: string
  modelId: string
  horizonHours: number | null
  score: number
  scoreType: ScoreType
  riskLevel: "critical" | "attention" | "observe" | "normal"
  scoreDelta: number | null
  lastEventAt: number | null
}

export function statusFromPredictionLevel(level: OverlayPrediction["riskLevel"]): AssetStatus {
  if (level === "critical") return "critical"
  if (level === "attention" || level === "observe") return "attention"
  return "normal"
}

export function riskLevelFromPrediction(level: OverlayPrediction["riskLevel"]): RiskLevel {
  if (level === "critical" || level === "attention") return "high"
  if (level === "observe") return "medium"
  return "low"
}

export function displayScoreFromPrediction(prediction: OverlayPrediction): number {
  const raw = prediction.score
  if (prediction.scoreType === "calibrated_probability") {
    return Math.round(Math.min(100, Math.max(0, raw <= 1 ? raw * 100 : raw)))
  }
  if (raw <= 1) return Math.round(Math.min(100, Math.max(0, raw * 100)))
  return Math.round(Math.min(100, Math.max(0, raw)))
}

export type PredictionOverlay = {
  riskScore: number
  scoreType: ScoreType
  riskLevel: RiskLevel
  status: AssetStatus
  forecastHorizon: ForecastHorizon
  predictionId: string
  modelId: string
  lastEventAt: number | null
  scoreDelta: number | null
}

export function overlayFromPrediction(prediction: OverlayPrediction): PredictionOverlay {
  const horizon =
    prediction.horizonHours === 72 || prediction.horizonHours === 24
      ? prediction.horizonHours
      : 24
  return {
    riskScore: displayScoreFromPrediction(prediction),
    scoreType: prediction.scoreType,
    riskLevel: riskLevelFromPrediction(prediction.riskLevel),
    status: statusFromPredictionLevel(prediction.riskLevel),
    forecastHorizon: horizon,
    predictionId: prediction.id,
    modelId: prediction.modelId,
    lastEventAt: prediction.lastEventAt,
    scoreDelta:
      prediction.scoreDelta === null || prediction.scoreDelta === undefined
        ? null
        : Math.abs(prediction.scoreDelta) <= 1
          ? Math.round(prediction.scoreDelta * 100)
          : Math.round(prediction.scoreDelta),
  }
}

export function indexPredictionsByAsset(
  predictions: OverlayPrediction[],
): Map<string, OverlayPrediction> {
  const rank: Record<OverlayPrediction["riskLevel"], number> = {
    critical: 4,
    attention: 3,
    observe: 2,
    normal: 1,
  }
  const best = new Map<string, OverlayPrediction>()
  for (const prediction of predictions) {
    const current = best.get(prediction.assetId)
    if (!current) {
      best.set(prediction.assetId, prediction)
      continue
    }
    const byLevel = rank[prediction.riskLevel] - rank[current.riskLevel]
    if (byLevel > 0 || (byLevel === 0 && prediction.score > current.score)) {
      best.set(prediction.assetId, prediction)
    }
  }
  return best
}
