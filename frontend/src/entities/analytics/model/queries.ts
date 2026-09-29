"use client"

import { useQuery } from "@tanstack/react-query"

import { workflowMode } from "@/shared/config/env"

import {
  getAlarmKpis,
  getAssetTree,
  getEffectReport,
  getEventTypes,
  getMlModels,
  getObjectHealthHistory,
  getProspective,
  getSeasonality,
  getSectionHealthHistory,
  getTodaysInspectionPlan,
  getWeatherReport,
} from "../api/service"

const api = workflowMode === "api"

export function useSeasonality() {
  return useQuery({ queryKey: ["ml", "seasonality"], queryFn: getSeasonality, enabled: api, staleTime: 3_600_000 })
}

export function useProspective() {
  return useQuery({ queryKey: ["ml", "prospective"], queryFn: getProspective, enabled: api, staleTime: 60_000, refetchInterval: 60_000 })
}

export function useEffectReport() {
  return useQuery({
    queryKey: ["analytics", "effect"],
    queryFn: getEffectReport,
    enabled: api,
    staleTime: 60_000,
    refetchInterval: 60_000,
  })
}

export function useAssetTree() {
  return useQuery({
    queryKey: ["analytics", "asset-tree"],
    queryFn: getAssetTree,
    enabled: api,
    staleTime: 60_000,
    refetchInterval: 60_000,
  })
}

export function useEventTypes() {
  return useQuery({
    queryKey: ["analytics", "event-types"],
    queryFn: getEventTypes,
    enabled: api,
    staleTime: 60_000,
  })
}

export function useMlModels() {
  return useQuery({
    queryKey: ["ml", "models"],
    queryFn: getMlModels,
    enabled: api,
    staleTime: 300_000,
  })
}

export function useSectionHealthHistory(group: string | null) {
  return useQuery({
    queryKey: ["analytics", "health-history", group],
    queryFn: () => getSectionHealthHistory(group!),
    enabled: api && Boolean(group),
    staleTime: 300_000,
  })
}

export function useAlarmKpis() {
  return useQuery({
    queryKey: ["analytics", "alarm-kpis"],
    queryFn: getAlarmKpis,
    enabled: api,
    staleTime: 300_000,
  })
}

export function useObjectHealthHistory() {
  return useQuery({
    queryKey: ["analytics", "health-history-objects"],
    queryFn: getObjectHealthHistory,
    enabled: api,
    staleTime: 300_000,
  })
}

export function useTodaysInspectionPlan() {
  return useQuery({
    queryKey: ["analytics", "inspection-plan", "today"],
    queryFn: getTodaysInspectionPlan,
    enabled: api,
    staleTime: 60_000,
    refetchInterval: 60_000,
  })
}

export function useWeatherReport() {
  return useQuery({
    queryKey: ["analytics", "weather"],
    queryFn: getWeatherReport,
    enabled: api,
    staleTime: 300_000,
  })
}
