import { apiFetch } from "@/shared/api/http"
import { workflowMode } from "@/shared/config/env"

import {
  indexPredictionsByAsset,
  overlayFromPrediction,
  type PredictionOverlay,
} from "../lib/prediction-overlay"
import type { ForecastHorizon } from "../model/types"

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
  name?: string | null
  location?: string | null
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
  name: string | null
  location: string | null
}

type CacheEntry = {
  at: number
  byAsset: Map<string, PredictionOverlay>
  raw: Map<string, LivePrediction>
}

const CACHE_MS = 15_000
const cache = new Map<ForecastHorizon, CacheEntry>()

function mapItem(item: ApiPrediction): LivePrediction {
  return {
    id: item.id,
    assetId: item.asset_id,
    modelId: item.model_id,
    horizonHours: item.horizon_hours,
    score: item.score,
    scoreType: item.score_type,
    riskLevel: item.risk_level,
    scoreDelta: item.score_delta,
    lastEventAt: item.last_event_at ? Date.parse(item.last_event_at) : null,
    name: item.name ?? null,
    location: item.location ?? null,
  }
}

async function fetchHorizonPage(horizon: ForecastHorizon, offset: number) {
  return apiFetch<ApiPrediction[]>(
    `/api/v1/predictions?horizon=${horizon}&sort=risk_desc&limit=500&offset=${offset}`
  )
}

async function loadPredictions(horizon: ForecastHorizon): Promise<CacheEntry> {
  if (workflowMode !== "api") {
    return { at: Date.now(), byAsset: new Map(), raw: new Map() }
  }
  const now = Date.now()
  const hit = cache.get(horizon)
  if (hit && now - hit.at < CACHE_MS) return hit

  try {
    const mapped: LivePrediction[] = []
    for (let offset = 0; offset < 100_000; offset += 500) {
      const page = await fetchHorizonPage(horizon, offset)
      for (const item of page) {
        if (item.horizon_hours !== horizon) continue
        mapped.push(mapItem(item))
      }
      if (page.length < 500) break
    }
    const indexed = indexPredictionsByAsset(mapped)
    const byAsset = new Map<string, PredictionOverlay>()
    for (const [assetId, prediction] of indexed) {
      byAsset.set(assetId, overlayFromPrediction(prediction))
    }
    const raw = new Map(mapped.map((item) => [item.assetId, indexed.get(item.assetId) ?? item]))
    const entry: CacheEntry = { at: now, byAsset, raw }
    cache.set(horizon, entry)
    return entry
  } catch {
    return { at: now, byAsset: new Map(), raw: new Map() }
  }
}

export async function predictionOverlays(horizon: ForecastHorizon = 72): Promise<Map<string, PredictionOverlay>> {
  return (await loadPredictions(horizon)).byAsset
}

export async function listLivePredictions(horizon: ForecastHorizon = 72): Promise<LivePrediction[]> {
  const { raw } = await loadPredictions(horizon)
  return [...raw.values()].sort((left, right) => {
    const rank: Record<LivePrediction["riskLevel"], number> = {
      critical: 4,
      attention: 3,
      observe: 2,
      normal: 1,
    }
    return rank[right.riskLevel] - rank[left.riskLevel] || right.score - left.score
  })
}
