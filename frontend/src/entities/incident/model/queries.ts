"use client"

import { useQuery } from "@tanstack/react-query"

import { workflowMode } from "@/shared/config/env"

import { getIncidentRegistry, getObjectRisks } from "../api/service"

const api = workflowMode === "api"

export function useIncidentRegistry() {
  return useQuery({
    queryKey: ["incidents", "registry"],
    queryFn: getIncidentRegistry,
    enabled: api,
    staleTime: 300_000,
  })
}

export function useObjectRisks() {
  return useQuery({
    queryKey: ["incidents", "objects"],
    queryFn: getObjectRisks,
    enabled: api,
    staleTime: 60_000,
    refetchInterval: 60_000,
  })
}
