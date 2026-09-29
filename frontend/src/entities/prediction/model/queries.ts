"use client"

import { useQuery } from "@tanstack/react-query"

import { workflowMode } from "@/shared/config/env"

import {
  getBackendSituations,
  getDashboardPredictions,
  getPredictionSummary,
  getPredictions,
  getSnapshotStatus,
} from "../api/service"

const enabled = workflowMode === "api"

export function useDashboardPredictions(horizon: 24 | 72) {
  return useQuery({
    queryKey: ["dashboard-predictions", horizon],
    queryFn: () => getDashboardPredictions(horizon),
    enabled,
    staleTime: 60_000,
    refetchInterval: 60_000,
    retry: 1,
  })
}

export function useSnapshotStatus() {
  return useQuery({ queryKey: ["prediction-snapshot"], queryFn: getSnapshotStatus, enabled, staleTime: 60_000, refetchInterval: 60_000 })
}

export function useBackendSituations() {
  return useQuery({ queryKey: ["backend-situations"], queryFn: getBackendSituations, enabled, staleTime: 30_000 })
}

export function useRiskRising(horizon: 24 | 72, limit = 20) {
  return useQuery({
    queryKey: ["predictions", "delta", horizon, limit],
    queryFn: () => getPredictions({ sort: "delta_desc", limit, horizon }),
    enabled,
    staleTime: 60_000,
  })
}

export function useCriticalPredictions(horizon: 24 | 72) {
  const summary = useQuery({
    queryKey: ["prediction-summary", horizon],
    queryFn: () => getPredictionSummary(horizon, 5),
    enabled,
    staleTime: 60_000,
    refetchInterval: 60_000,
    retry: 1,
  })
  return {
    ...summary,
    data: summary.data
      ? {
          critical: summary.data.topCritical,
          attention: summary.data.topAttention,
          criticalCount: summary.data.counts.critical,
          attentionCount: summary.data.counts.attention,
          total: summary.data.total,
        }
      : undefined,
  }
}
