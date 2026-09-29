import { z } from "zod"

import { ApiError, apiFetch } from "@/shared/api/http"

import type { EffectReport, EventTypeStats, ObjectNode, Prospective, Seasonality } from "../model/types"

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
      channels_at_risk: Record<string, number>
      episodes_30d: number | null
      episodes_365d: number | null
      next_7_days: { expected: number } | null
    }[]
  >("/api/v1/analytics/event-types")
  return raw.map((item) => ({
    eventType: item.event_type,
    title: item.title,
    scenario: item.scenario,
    channelsAtRisk: item.channels_at_risk,
    episodes30d: item.episodes_30d,
    episodes365d: item.episodes_365d,
    next7DaysExpected: item.next_7_days?.expected ?? null,
  }))
}
