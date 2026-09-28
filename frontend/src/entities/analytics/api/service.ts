import { z } from "zod"

import { ApiError, apiFetch } from "@/shared/api/http"

import type { Prospective, Seasonality } from "../model/types"

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

/** Null until the stream has produced forecasts after the training journal. */
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
