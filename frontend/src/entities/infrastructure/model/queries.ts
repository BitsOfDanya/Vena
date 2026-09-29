import { keepPreviousData, useQueries, useQuery } from "@tanstack/react-query"

import { MINUTE } from "@/shared/lib/time"

import {
  getAsset,
  getAssets,
  getEvents,
  getForecast,
  getNetwork,
  getPredictionAssets,
  getPulse,
  getPulseSummary,
  getReplayEpisodes,
  getRiskHistory,
  getSituations,
  getStateHistory,
  getTemporal,
  searchAssets,
} from "../api/service"
import type { ForecastHorizon, TemporalBundle } from "./types"
import { workflowMode } from "@/shared/config/env"

export function bucketNow(now: number, minutes = 1) {
  const size = minutes * MINUTE
  return Math.floor(now / size) * size
}

export function usePulse(now: number, windowHours = 6) {
  return useQuery({
    queryKey: ["pulse", bucketNow(now, 1), windowHours],
    queryFn: () => getPulse({ now, windowHours }),
    placeholderData: keepPreviousData,
  })
}

export function useNetwork(now: number, horizon: ForecastHorizon) {
  return useQuery({
    queryKey: ["network", bucketNow(now, 1), horizon],
    queryFn: () => getNetwork({ now, horizon }),
    placeholderData: keepPreviousData,
  })
}

export function useAssets(now: number, horizon: ForecastHorizon) {
  return useQuery({
    queryKey: ["assets", bucketNow(now, 5), horizon],
    queryFn: () => getAssets({ now, horizon }),
    placeholderData: keepPreviousData,
  })
}

export function useAssetSearch(query: string, now: number, horizon: ForecastHorizon) {
  return useQuery({
    queryKey: ["asset-search", query, bucketNow(now, 5), horizon, workflowMode],
    queryFn: async () => {
      if (workflowMode !== "api") return searchAssets(query, { now, horizon })
      const needle = query.trim().toLowerCase()
      const assets = await getPredictionAssets(horizon)
      if (!needle) return assets.slice(0, 12)
      return assets
        .filter((asset) => asset.id.toLowerCase().includes(needle) || asset.channelId.includes(needle))
        .slice(0, 12)
    },
    placeholderData: keepPreviousData,
  })
}

export function usePredictionAssets(horizon: ForecastHorizon) {
  return useQuery({
    queryKey: ["prediction-assets", horizon],
    queryFn: () => getPredictionAssets(horizon),
    enabled: workflowMode === "api",
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  })
}

export function useAssetDetail(id: string | null, now: number, horizon: ForecastHorizon) {
  return useQuery({
    queryKey: ["asset", id, bucketNow(now, 1), horizon],
    queryFn: () => getAsset(id as string, { now, horizon }),
    enabled: id !== null,
    placeholderData: keepPreviousData,
  })
}

export function useRiskHistory(id: string | null, from: number, to: number, horizon: ForecastHorizon) {
  return useQuery({
    queryKey: ["risk-history", id, bucketNow(from, 30), bucketNow(to, 1), horizon],
    queryFn: () => getRiskHistory(id as string, from, to, horizon),
    enabled: id !== null,
    placeholderData: keepPreviousData,
  })
}

export function useAssetEvents(id: string | null, from: number, to: number) {
  return useQuery({
    queryKey: ["events", id, bucketNow(from, 30), bucketNow(to, 1)],
    queryFn: () => getEvents(id as string, from, to),
    enabled: id !== null,
    placeholderData: keepPreviousData,
  })
}

export function useStateHistory(id: string | null, from: number, to: number) {
  return useQuery({
    queryKey: ["state-history", id, bucketNow(from, 30), bucketNow(to, 1)],
    queryFn: () => getStateHistory(id as string, from, to),
    enabled: id !== null,
    placeholderData: keepPreviousData,
  })
}

export function useForecast(id: string | null, now: number, horizon: number) {
  return useQuery({
    queryKey: ["forecast", id, bucketNow(now, 1), horizon],
    queryFn: () => getForecast(id as string, now, horizon),
    enabled: id !== null,
    placeholderData: keepPreviousData,
  })
}

export function useReplayEpisodes() {
  return useQuery({ queryKey: ["replay-episodes"], queryFn: getReplayEpisodes, staleTime: Infinity })
}

export function useTemporalBundles(ids: string[], now: number, halfSpanHours: number, horizon: ForecastHorizon) {
  return useQueries({
    queries: ids.map((id) => ({
      queryKey: ["temporal", id, bucketNow(now, 1), halfSpanHours, horizon],
      queryFn: () => getTemporal(id, { now, horizon }, halfSpanHours),
      placeholderData: keepPreviousData,
    })),
    combine: (results) => ({
      bundles: results.map((result) => result.data).filter((bundle): bundle is TemporalBundle => Boolean(bundle)),
      pending: results.some((result) => result.isPending),
      error: results.some((result) => result.isError),
    }),
  })
}

export function useSituations(now: number, horizon: ForecastHorizon) {
  return useQuery({
    queryKey: ["situations", bucketNow(now, 1), horizon],
    queryFn: () => getSituations({ now, horizon }),
    placeholderData: keepPreviousData,
  })
}

export function usePulseSummary(now: number, horizon: ForecastHorizon) {
  return useQuery({
    queryKey: ["pulse-summary", bucketNow(now, 1), horizon],
    queryFn: () => getPulseSummary({ now, horizon }),
    placeholderData: keepPreviousData,
  })
}
