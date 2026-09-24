"use client"

import { useQuery } from "@tanstack/react-query"

import { workflowMode } from "@/shared/config/env"

import { getBackendSituations, getPredictions, getSnapshotStatus } from "../api/service"

const enabled = workflowMode === "api"

export function useSnapshotStatus(available = true) {
  return useQuery({ queryKey: ["prediction-snapshot"], queryFn: getSnapshotStatus, enabled: enabled && available, staleTime: 60_000 })
}

export function useBackendSituations() {
  return useQuery({ queryKey: ["backend-situations"], queryFn: getBackendSituations, enabled, staleTime: 30_000 })
}

export function useRiskRising(limit = 20) {
  return useQuery({
    queryKey: ["predictions", "delta", limit],
    queryFn: () => getPredictions({ sort: "delta_desc", limit }),
    enabled,
    staleTime: 60_000,
  })
}

export function useCriticalPredictions(limit = 20) {
  return useQuery({
    queryKey: ["predictions", "critical", limit],
    queryFn: async () => {
      const [critical, attention] = await Promise.all([
        getPredictions({ riskLevel: "critical", limit }),
        getPredictions({ riskLevel: "attention", limit }),
      ])
      return { critical, attention }
    },
    enabled,
    staleTime: 60_000,
  })
}
