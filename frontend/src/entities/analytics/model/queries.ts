"use client"

import { useQuery } from "@tanstack/react-query"

import { workflowMode } from "@/shared/config/env"

import { getProspective, getSeasonality } from "../api/service"

export function useSeasonality() {
  return useQuery({ queryKey: ["ml", "seasonality"], queryFn: getSeasonality, enabled: workflowMode === "api", staleTime: 3_600_000 })
}

export function useProspective() {
  return useQuery({ queryKey: ["ml", "prospective"], queryFn: getProspective, enabled: workflowMode === "api", staleTime: 60_000, refetchInterval: 60_000 })
}
