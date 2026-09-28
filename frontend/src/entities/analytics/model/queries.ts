"use client"

import { useQuery } from "@tanstack/react-query"

import { workflowMode } from "@/shared/config/env"

import { getSeasonality } from "../api/service"

export function useSeasonality() {
  return useQuery({ queryKey: ["ml", "seasonality"], queryFn: getSeasonality, enabled: workflowMode === "api", staleTime: 3_600_000 })
}
