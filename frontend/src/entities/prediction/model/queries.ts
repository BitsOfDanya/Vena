"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { workflowMode } from "@/shared/config/env"

import {
  claimSituation,
  getBackendSituations,
  getDashboardPredictions,
  getPredictionContext,
  getPredictionSummary,
  getPredictions,
  getSnapshotStatus,
  releaseSituation,
} from "../api/service"
import type { BackendSituation } from "../model/types"

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

export function usePredictionContext(predictionId: string | null) {
  return useQuery({
    queryKey: ["prediction-context", predictionId],
    queryFn: () => getPredictionContext(predictionId ?? ""),
    enabled: enabled && Boolean(predictionId),
    staleTime: 300_000,
    retry: false,
  })
}

const SITUATIONS_KEY = ["backend-situations"] as const

export function useBackendSituations() {
  return useQuery({
    queryKey: SITUATIONS_KEY,
    queryFn: getBackendSituations,
    enabled,
    staleTime: 0,
    refetchInterval: 15_000,
    refetchIntervalInBackground: true,
  })
}

type ClaimPatch = Pick<BackendSituation, "claimedBy" | "claimedBySubject" | "claimedAt">

function useSituationClaimMutation<T>(
  request: (situationId: string) => Promise<T>,
  patch: (holder: { name: string; subject: string }) => ClaimPatch,
  settle?: (result: T) => ClaimPatch,
) {
  const client = useQueryClient()
  const apply = (situationId: string, values: ClaimPatch) =>
    client.setQueryData<BackendSituation[]>(SITUATIONS_KEY, (list) =>
      list?.map((item) => (item.id === situationId ? { ...item, ...values } : item))
    )
  return useMutation({
    mutationFn: ({ situationId }: { situationId: string; name: string; subject: string }) => request(situationId),
    onMutate: async ({ situationId, name, subject }) => {
      await client.cancelQueries({ queryKey: SITUATIONS_KEY })
      const previous = client.getQueryData<BackendSituation[]>(SITUATIONS_KEY)
      apply(situationId, patch({ name, subject }))
      return { previous }
    },
    onSuccess: (result, { situationId }) => {
      if (settle) apply(situationId, settle(result))
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) client.setQueryData(SITUATIONS_KEY, context.previous)
    },
    onSettled: () => client.invalidateQueries({ queryKey: SITUATIONS_KEY }),
  })
}

export function useClaimSituation() {
  return useSituationClaimMutation(
    claimSituation,
    ({ name, subject }) => ({ claimedBy: name, claimedBySubject: subject, claimedAt: Date.now() }),
    (claim) => ({ claimedBy: claim.claimedBy, claimedBySubject: claim.claimedBySubject, claimedAt: claim.claimedAt }),
  )
}

export function useReleaseSituation() {
  return useSituationClaimMutation(releaseSituation, () => ({ claimedBy: null, claimedBySubject: null, claimedAt: null }))
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
