import { apiFetch } from "@/shared/api/http"
import { workflowMode } from "@/shared/config/env"

import {
  indexPredictionsByAsset,
  overlayFromPrediction,
  type PredictionOverlay,
} from "../lib/prediction-overlay"

type ApiPrediction = {
  id: string
  asset_id: string
  model_id: string
  horizon_hours: number | null
  score: number
  score_type: "risk_score" | "calibrated_probability"
  risk_level: "critical" | "attention" | "observe" | "normal"
  score_delta: number | null
  last_event_at: string | null
}

export type LivePrediction = {
  id: string
  assetId: string
  modelId: string
  horizonHours: number | null
  score: number
  scoreType: "risk_score" | "calibrated_probability"
  riskLevel: "critical" | "attention" | "observe" | "normal"
  scoreDelta: number | null
  lastEventAt: number | null
}

let cache: { at: number; byAsset: Map<string, PredictionOverlay>; raw: Map<string, LivePrediction> } | null =
  null
const CACHE_MS = 15_000

async function loadPredictions(): Promise<{
  byAsset: Map<string, PredictionOverlay>
  raw: Map<string, LivePrediction>
}> {
  if (workflowMode !== "api") {
    return { byAsset: new Map(), raw: new Map() }
  }
  const now = Date.now()
  if (cache && now - cache.at < CACHE_MS) {
    return { byAsset: cache.byAsset, raw: cache.raw }
  }
  try {
    const items = await apiFetch<ApiPrediction[]>("/api/v1/predictions?limit=500&sort=risk_desc")
    const mapped: LivePrediction[] = items.map((item) => ({
      id: item.id,
      assetId: item.asset_id,
      modelId: item.model_id,
      horizonHours: item.horizon_hours,
      score: item.score,
      scoreType: item.score_type,
      riskLevel: item.risk_level,
      scoreDelta: item.score_delta,
      lastEventAt: item.last_event_at ? Date.parse(item.last_event_at) : null,
    }))
    const indexed = indexPredictionsByAsset(mapped)
    const byAsset = new Map<string, PredictionOverlay>()
    for (const [assetId, prediction] of indexed) {
      byAsset.set(assetId, overlayFromPrediction(prediction))
    }
    const raw = new Map(mapped.map((item) => [item.assetId, indexed.get(item.assetId) ?? item]))
    cache = { at: now, byAsset, raw }
    return { byAsset, raw }
  } catch {
    return { byAsset: new Map(), raw: new Map() }
  }
}

export async function predictionOverlays(): Promise<Map<string, PredictionOverlay>> {
  return (await loadPredictions()).byAsset
}
