"use client"

import { useQuery } from "@tanstack/react-query"

import { workflowMode } from "@/shared/config/env"

import { getBackendSituations, getDashboardPredictions, getPredictions, getSnapshotStatus } from "../api/service"

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

/** Same snapshot as Dashboard — counts critical/attention for the workspace horizon. */
export function useCriticalPredictions(horizon: 24 | 72) {
  const predictions = useDashboardPredictions(horizon)
  const critical = (predictions.data ?? []).filter((item) => item.riskLevel === "critical")
  const attention = (predictions.data ?? []).filter((item) => item.riskLevel === "attention")
  return {
    ...predictions,
    data: predictions.data ? { critical, attention } : undefined,
  }
}
