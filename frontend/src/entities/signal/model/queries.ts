"use client"

import { useQuery } from "@tanstack/react-query"

import { workflowMode } from "@/shared/config/env"

import { getAccessEvents, getAccessRoutes, getAlarms } from "../api/service"

const enabled = workflowMode === "api"

export function useAlarms() {
  return useQuery({ queryKey: ["signals", "alarms"], queryFn: getAlarms, enabled, staleTime: 60_000, refetchInterval: 60_000 })
}

export function useAccessEvents() {
  return useQuery({ queryKey: ["signals", "access"], queryFn: getAccessEvents, enabled, staleTime: 60_000, refetchInterval: 60_000 })
}

export function useAccessRoutes() {
  return useQuery({ queryKey: ["signals", "routes"], queryFn: getAccessRoutes, enabled, staleTime: 60_000, refetchInterval: 60_000 })
}
