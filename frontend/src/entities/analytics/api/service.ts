import { z } from "zod"

import { ApiError, apiFetch } from "@/shared/api/http"

import type {
  AlarmKpis,
  EffectReport,
  EventTypeStats,
  HealthPoint,
  InspectionPlan,
  MlModel,
  ObjectNode,
  Prospective,
  Seasonality,
  TodaysInspectionPlan,
} from "../model/types"

const monthly = z.record(z.string(), z.record(z.string(), z.number()))

const SeasonalitySchema = z.object({
  monthly_onsets_per_100_channels: monthly,
  seasonal_share: monthly,
  flooding_vs_weather: z.record(z.string(), z.number()).optional(),
})

export async function getSeasonality(): Promise<Seasonality> {
  const raw = SeasonalitySchema.parse(await apiFetch<unknown>("/api/v1/ml/reports/seasonality"))
  const rows = Object.entries(raw.monthly_onsets_per_100_channels).map(([scenario, months]) => ({
    scenario,
    months: Array.from({ length: 12 }, (_, index) => months[String(index + 1)] ?? 0),
  }))
  return { rows, weather: raw.flooding_vs_weather ?? {} }
}

const ProspectiveSchema = z.object({
  start: z.string(),
  now: z.string(),
  models: z.record(
    z.string(),
    z.object({
      forecasts: z.number(),
      event_rate: z.number(),
      mean_probability: z.number(),
      brier: z.number(),
      alerts: z.number(),
      alert_precision: z.number().nullable(),
      episodes: z.number(),
      episodes_warned: z.number(),
      episode_recall: z.number().nullable(),
    })
  ),
})

export async function getProspective(): Promise<Prospective | null> {
  try {
    const raw = ProspectiveSchema.parse(await apiFetch<unknown>("/api/v1/ml/prospective"))
    return {
      start: Date.parse(raw.start),
      now: Date.parse(raw.now),
      models: Object.fromEntries(
        Object.entries(raw.models).map(([name, item]) => [
          name,
          {
            forecasts: item.forecasts,
            eventRate: item.event_rate,
            meanProbability: item.mean_probability,
            brier: item.brier,
            alerts: item.alerts,
            alertPrecision: item.alert_precision,
            episodes: item.episodes,
            episodesWarned: item.episodes_warned,
            episodeRecall: item.episode_recall,
          },
        ])
      ),
    }
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null
    throw error
  }
}

export async function getEffectReport(): Promise<EffectReport> {
  const raw = await apiFetch<{
    channels_at_risk: number
    incidents: number
    lead_time: {
      model_id: string
      level: string
      episode_recall: number | null
      alert_precision: number | null
      median_lead_time_hours: number | null
      alerts_per_day: number | null
    }[]
    alarms_30d: number
    alarms_to_verify: number
    alarm_filter_share: number | null
    access_events_30d: number
    forecasts_in_journal: number
    decided: number
    confirmed: number
    rejected: number
    dispatches_avoided: number
  }>("/api/v1/analytics/effect")
  return {
    channelsAtRisk: raw.channels_at_risk,
    incidents: raw.incidents,
    leadTime: raw.lead_time.map((item) => ({
      modelId: item.model_id,
      level: item.level,
      episodeRecall: item.episode_recall,
      alertPrecision: item.alert_precision,
      medianLeadTimeHours: item.median_lead_time_hours,
      alertsPerDay: item.alerts_per_day,
    })),
    alarms30d: raw.alarms_30d,
    alarmsToVerify: raw.alarms_to_verify,
    alarmFilterShare: raw.alarm_filter_share,
    accessEvents30d: raw.access_events_30d,
    forecastsInJournal: raw.forecasts_in_journal,
    decided: raw.decided,
    confirmed: raw.confirmed,
    rejected: raw.rejected,
    dispatchesAvoided: raw.dispatches_avoided,
  }
}

export async function getAssetTree(): Promise<ObjectNode[]> {
  const raw = await apiFetch<
    {
      object_id: string
      label: string
      health_index: number | null
      sections: {
        group: string
        label: string | null
        health_index: number | null
        main_scenario: string | null
        risk_by_scenario: Record<string, number>
        channels: {
          asset_id: string
          name: string | null
          sensor_type: string | null
          scenario: string
          model_id: string
          probability: number
          risk_level: string
        }[]
      }[]
    }[]
  >("/api/v1/assets/tree")
  return raw.map((object) => ({
    objectId: object.object_id,
    label: object.label,
    healthIndex: object.health_index,
    sections: object.sections.map((section) => ({
      group: section.group,
      label: section.label,
      healthIndex: section.health_index,
      mainScenario: section.main_scenario,
      riskByScenario: section.risk_by_scenario,
      channels: section.channels.map((channel) => ({
        assetId: channel.asset_id,
        name: channel.name,
        sensorType: channel.sensor_type,
        scenario: channel.scenario,
        modelId: channel.model_id,
        probability: channel.probability,
        riskLevel: channel.risk_level,
      })),
    })),
  }))
}

export async function getEventTypes(): Promise<EventTypeStats[]> {
  const raw = await apiFetch<
    {
      event_type: string
      title: string
      scenario: string
      models?: string[]
      channels_at_risk: Record<string, number>
      episodes_30d: number | null
      episodes_365d: number | null
      forecast?: { day: string; expected: number }[]
      next_7_days: { expected: number; low?: number; high?: number } | null
      week_error?: number | null
      week_error_baseline?: number | null
      backtest?: { day: string; actual: number; forecast: number }[]
    }[]
  >("/api/v1/analytics/event-types")
  return raw.map((item) => ({
    eventType: item.event_type,
    title: item.title,
    scenario: item.scenario,
    models: item.models ?? [],
    channelsAtRisk: item.channels_at_risk,
    episodes30d: item.episodes_30d,
    episodes365d: item.episodes_365d,
    forecast: item.forecast ?? [],
    next7Days: item.next_7_days
      ? {
          expected: item.next_7_days.expected,
          low: item.next_7_days.low ?? null,
          high: item.next_7_days.high ?? null,
        }
      : null,
    weekError: item.week_error ?? null,
    weekErrorBaseline: item.week_error_baseline ?? null,
    backtest: item.backtest ?? [],
  }))
}

export async function getMlModels(): Promise<MlModel[]> {
  const raw = await apiFetch<
    {
      name: string
      scenario?: string
      sensor?: string | null
      target?: string | null
      horizon_hours?: number
      recipe?: string | null
      features?: number | null
      train_years?: string | null
      version?: string | null
      held_out?: {
        period?: string
        base_rate?: number | null
        avg_precision?: number | null
        roc_auc?: number | null
        precision_top5_per_day?: number | null
        ece?: number | null
      } | null
      lead_time?: {
        episode_recall?: number | null
        alert_precision_dedup?: number | null
        median_lead_time_hours?: number | null
        alerts_per_day?: number | null
      } | null
      daily_top_k?: Record<string, number> | null
    }[]
  >("/api/v1/ml/models")
  return raw.map((item) => ({
    name: item.name,
    scenario: item.scenario ?? "equipment",
    sensor: item.sensor ?? null,
    target: item.target ?? null,
    horizonHours: item.horizon_hours ?? 24,
    recipe: item.recipe ?? null,
    features: item.features ?? null,
    trainYears: item.train_years ?? null,
    version: item.version ?? null,
    heldOut: item.held_out
      ? {
          period: item.held_out.period ?? "2026H1",
          baseRate: item.held_out.base_rate ?? null,
          avgPrecision: item.held_out.avg_precision ?? null,
          rocAuc: item.held_out.roc_auc ?? null,
          precisionTop5PerDay: item.held_out.precision_top5_per_day ?? null,
          ece: item.held_out.ece ?? null,
        }
      : null,
    leadTime: item.lead_time
      ? {
          episodeRecall: item.lead_time.episode_recall ?? null,
          alertPrecisionDedup: item.lead_time.alert_precision_dedup ?? null,
          medianLeadTimeHours: item.lead_time.median_lead_time_hours ?? null,
          alertsPerDay: item.lead_time.alerts_per_day ?? null,
        }
      : null,
    dailyTopK: item.daily_top_k ?? null,
  }))
}

export async function getSectionHealthHistory(group: string): Promise<HealthPoint[]> {
  try {
    const raw = await apiFetch<[string, number][]>(`/api/v1/analytics/health-history/${encodeURIComponent(group)}`)
    return raw.map(([day, value]) => ({ day, value }))
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return []
    throw error
  }
}

export async function getAlarmKpis(): Promise<AlarmKpis | null> {
  try {
    const raw = await apiFetch<{
      definitions?: { acceptable_per_hour?: number; manageable_per_hour?: number }
      recent?: {
        start?: string
        end?: string
        activations?: number
        per_hour_mean?: number
        per_hour_p95?: number | null
        flood_share_of_time?: number | null
        activations_in_floods?: number | null
        top10_share?: number | null
        chattering_top?: { channel_id: string; name?: string | null; activations: number }[]
        maintenance_share?: number | null
      }
      months?: {
        start?: string
        end?: string
        month?: string
        per_hour_mean?: number
        activations_in_floods?: number | null
      }[]
    }>("/api/v1/analytics/alarm-kpis")
    const recent = raw.recent
    return {
      acceptablePerHour: raw.definitions?.acceptable_per_hour ?? 6,
      manageablePerHour: raw.definitions?.manageable_per_hour ?? 12,
      recent: recent
        ? {
            start: recent.start ?? null,
            end: recent.end ?? null,
            activations: recent.activations ?? 0,
            perHourMean: recent.per_hour_mean ?? 0,
            perHourP95: recent.per_hour_p95 ?? null,
            floodShareOfTime: recent.flood_share_of_time ?? null,
            activationsInFloods: recent.activations_in_floods ?? null,
            top10Share: recent.top10_share ?? null,
            chatteringTop: (recent.chattering_top ?? []).map((item) => ({
              channelId: item.channel_id,
              name: item.name ?? null,
              activations: item.activations,
            })),
            maintenanceShare: recent.maintenance_share ?? null,
          }
        : null,
      months: (raw.months ?? []).map((item) => ({
        start: item.start ?? item.month ?? "",
        end: item.end ?? item.month ?? "",
        perHourMean: item.per_hour_mean ?? 0,
        activationsInFloods: item.activations_in_floods ?? null,
      })),
    }
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null
    throw error
  }
}

export async function getObjectHealthHistory(): Promise<{ period: string | null; objects: Record<string, HealthPoint[]> }> {
  try {
    const raw = await apiFetch<{ period?: string; objects?: Record<string, [string, number][]> }>(
      "/api/v1/analytics/health-history"
    )
    const objects: Record<string, HealthPoint[]> = {}
    for (const [id, series] of Object.entries(raw.objects ?? {})) {
      objects[id] = series.map(([day, value]) => ({ day, value }))
    }
    return { period: raw.period ?? null, objects }
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return { period: null, objects: {} }
    throw error
  }
}

type ApiPlanItem = {
  asset_id: string
  name: string | null
  location: string | null
  model_id: string
  probability: number
  risk_level: string
  reason: string | null
}

type ApiInspectionPlan = {
  model_id: string
  count: number
  skipped_recent: string[]
  items: ApiPlanItem[]
}

function mapInspectionPlan(raw: ApiInspectionPlan): InspectionPlan {
  return {
    modelId: raw.model_id,
    count: raw.count,
    skippedRecent: raw.skipped_recent ?? [],
    items: (raw.items ?? []).map((item) => ({
      assetId: item.asset_id,
      name: item.name,
      location: item.location,
      modelId: item.model_id,
      probability: item.probability,
      riskLevel: item.risk_level,
      reason: item.reason,
    })),
  }
}

export async function getInspectionPlan(modelId: string, count = 5): Promise<InspectionPlan> {
  const query = new URLSearchParams({ model_id: modelId, count: String(count) })
  const raw = await apiFetch<ApiInspectionPlan>(`/api/v1/analytics/inspection-plan?${query}`)
  return mapInspectionPlan(raw)
}

export async function getTodaysInspectionPlan(): Promise<TodaysInspectionPlan> {
  const [pumps, fans] = await Promise.all([
    getInspectionPlan("pump_72h", 5),
    getInspectionPlan("fan_72h", 5),
  ])
  return { pumps, fans }
}
