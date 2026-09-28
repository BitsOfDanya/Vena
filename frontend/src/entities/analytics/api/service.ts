import { z } from "zod"

import { apiFetch } from "@/shared/api/http"

import type { Seasonality } from "../model/types"

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
