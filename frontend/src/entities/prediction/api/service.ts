import { z } from "zod"

import { apiFetch } from "@/shared/api/http"

import type { BackendSituation, Prediction, PredictionScenario, SnapshotStatus } from "../model/types"

type ApiPrediction = {
  id: string
  asset_id: string
  device_type: string
  model_id: string
  model_version: string | null
  prediction_time: string
  horizon_hours: number | null
  score: number
  score_type: Prediction["scoreType"]
  risk_level: Prediction["riskLevel"]
  model_risk_level: string
  score_delta: number | null
  factors: { key: string; label: string; value: number }[]
  sensor_type: string | null
  system_type: string | null
  last_event_at: string | null
  scenario?: string
  location?: string | null
  location_tag?: string | null
}

const SCENARIOS = new Set<PredictionScenario>(["flooding", "fire", "power_loss", "ventilation", "equipment"])

function toScenario(value: string | null | undefined): PredictionScenario {
  return value && SCENARIOS.has(value as PredictionScenario) ? (value as PredictionScenario) : "equipment"
}

// ML names models after the sensor they read: phase monitors belong to power supply,
// and the flooding model reads the pump chamber state.
const DEVICE_ALIASES: Record<string, string> = { phase: "power", flood: "pump" }

function toPrediction(item: ApiPrediction): Prediction {
  return {
    id: item.id,
    assetId: item.asset_id,
    deviceType: DEVICE_ALIASES[item.device_type] ?? item.device_type,
    modelId: item.model_id,
    modelVersion: item.model_version,
    predictionTime: Date.parse(item.prediction_time),
    horizonHours: item.horizon_hours,
    score: item.score,
    scoreType: item.score_type,
    riskLevel: item.risk_level,
    modelRiskLevel: item.model_risk_level,
    scoreDelta: item.score_delta,
    factors: item.factors,
    sensorType: item.sensor_type,
    systemType: item.system_type,
    lastEventAt: item.last_event_at ? Date.parse(item.last_event_at) : null,
    scenario: toScenario(item.scenario),
    location: item.location ?? null,
    locationTag: item.location_tag ?? null,
  }
}

export async function getPredictions(
  params: {
    riskLevel?: string
    sort?: "risk_desc" | "delta_desc" | "latest"
    limit?: number
    offset?: number
    horizon?: number
  } = {}
): Promise<Prediction[]> {
  const query = new URLSearchParams()
  if (params.riskLevel) query.set("risk_level", params.riskLevel)
  if (params.sort) query.set("sort", params.sort)
  query.set("limit", String(params.limit ?? 50))
  if (params.offset !== undefined) query.set("offset", String(params.offset))
  if (params.horizon !== undefined) query.set("horizon", String(params.horizon))
  const items = await apiFetch<ApiPrediction[]>(`/api/v1/predictions?${query.toString()}`)
  return items.map(toPrediction)
}

const PredictionSchema = z.object({
  id: z.string(),
  asset_id: z.string(),
  device_type: z.string(),
  model_id: z.string(),
  model_version: z.string().nullable(),
  prediction_time: z.iso.datetime({ offset: true }),
  horizon_hours: z.number().int().positive().nullable(),
  score: z.number().finite().min(0).max(1),
  score_type: z.enum(["risk_score", "calibrated_probability"]),
  risk_level: z.enum(["critical", "attention", "observe", "normal"]),
  model_risk_level: z.string(),
  score_delta: z.number().nullable(),
  factors: z.array(z.object({ key: z.string(), label: z.string(), value: z.number() })),
  sensor_type: z.string().nullable(),
  system_type: z.string().nullable(),
  last_event_at: z.iso.datetime({ offset: true }).nullable(),
  scenario: z.string().optional(),
  location: z.string().nullable().optional(),
  location_tag: z.string().nullable().optional(),
})

/** A complete horizon-specific snapshot; a failed page never becomes a partial total. */
export async function getDashboardPredictions(horizon: 24 | 72): Promise<Prediction[]> {
  const before = await getSnapshotStatus()
  if (!before.available || !before.snapshotId) throw new Error("Predictions unavailable")
  const result: Prediction[] = []
  const ids = new Set<string>()
  for (let offset = 0; offset < 100_000; offset += 500) {
    const raw = await apiFetch<unknown>(`/api/v1/predictions?horizon=${horizon}&sort=risk_desc&limit=500&offset=${offset}`)
    const page = z.array(PredictionSchema).parse(raw).map(toPrediction)
    for (const item of page) {
      if (item.horizonHours !== horizon || ids.has(item.id)) throw new Error("Inconsistent prediction snapshot")
      ids.add(item.id)
      result.push(item)
    }
    if (page.length < 500) {
      const after = await getSnapshotStatus()
      if (!after.available || after.snapshotId !== before.snapshotId) throw new Error("Snapshot changed; refresh dashboard")
      return result
    }
  }
  throw new Error("Prediction snapshot exceeds dashboard capacity")
}

export async function getAssetPrediction(assetId: string): Promise<Prediction | null> {
  try {
    return toPrediction(await apiFetch<ApiPrediction>(`/api/v1/assets/${assetId}/prediction`))
  } catch {
    return null
  }
}

export async function getSnapshotStatus(): Promise<SnapshotStatus> {
  const item = await apiFetch<{
    available: boolean
    snapshot_id: string | null
    prediction_time: string | null
    age_seconds: number | null
    stale: boolean
    prediction_count: number
    models: { model_id: string; model_version: string | null; horizon_hours: number | null; calibrated: boolean }[]
    detail: string
  }>("/api/v1/predictions/snapshot")
  return {
    available: item.available,
    snapshotId: item.snapshot_id,
    predictionTime: item.prediction_time ? Date.parse(item.prediction_time) : null,
    ageSeconds: item.age_seconds,
    stale: item.stale,
    predictionCount: item.prediction_count,
    models: item.models.map((model) => ({
      modelId: model.model_id,
      modelVersion: model.model_version,
      horizonHours: model.horizon_hours,
      calibrated: model.calibrated,
    })),
    detail: item.detail,
  }
}

export async function getBackendSituations(): Promise<BackendSituation[]> {
  const items = await apiFetch<
    {
      id: string
      type: BackendSituation["type"]
      severity: BackendSituation["severity"]
      title: string
      summary: string
      asset_ids: string[]
      pattern_id: string | null
      risk_score: number | null
      risk_delta: number | null
      forecast_horizon: number | null
      primary_reason: string
      status: BackendSituation["status"]
      updated_at: string
      open_action_id: string | null
      notification_id: string | null
      scenario?: string | null
      location?: string | null
      asset_count?: number
    }[]
  >("/api/v1/situations")
  return items.map((item) => ({
    id: item.id,
    type: item.type,
    severity: item.severity,
    title: item.title,
    summary: item.summary,
    assetIds: item.asset_ids,
    patternId: item.pattern_id,
    riskScore: item.risk_score,
    riskDelta: item.risk_delta,
    forecastHorizon: item.forecast_horizon,
    primaryReason: item.primary_reason,
    status: item.status,
    updatedAt: Date.parse(item.updated_at),
    openActionId: item.open_action_id,
    notificationId: item.notification_id,
    scenario: item.scenario ? toScenario(item.scenario) : null,
    location: item.location ?? null,
    assetCount: item.asset_count ?? item.asset_ids.length,
  }))
}
