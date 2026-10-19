"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  getReplayScenarios,
  getReplayState,
  startScenarioReplay,
  startWeekReplay,
  stopReplay,
  type ReplayState,
} from "../api/replay"

const KEY = ["system", "replay"] as const

export function useReplayState() {
  return useQuery({
    queryKey: KEY,
    queryFn: getReplayState,
    retry: false,
    refetchInterval: (query) => (query.state.data?.active ? 5_000 : 30_000),
  })
}

export function useReplayScenarios(enabled = true) {
  return useQuery({ queryKey: ["system", "replay-scenarios"], queryFn: getReplayScenarios, retry: false, staleTime: 60_000, enabled })
}

function useReplayMutation<T>(mutationFn: (input: T) => Promise<ReplayState>) {
  const client = useQueryClient()
  return useMutation({ mutationFn, onSuccess: (data) => client.setQueryData(KEY, data) })
}

export function useStartWeekReplay() {
  return useReplayMutation(startWeekReplay)
}

export function useStartScenarioReplay() {
  return useReplayMutation(startScenarioReplay)
}

export function useStopReplay() {
  return useReplayMutation(stopReplay)
}
