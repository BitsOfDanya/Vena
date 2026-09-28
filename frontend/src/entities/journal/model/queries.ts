"use client"

import { useQuery } from "@tanstack/react-query"

import { workflowMode } from "@/shared/config/env"

import { getJournal, getJournalSummary } from "../api/service"

const enabled = workflowMode === "api"

export function useJournal() {
  return useQuery({ queryKey: ["journal"], queryFn: getJournal, enabled, staleTime: 15_000, refetchInterval: 60_000 })
}

export function useJournalSummary() {
  return useQuery({ queryKey: ["journal", "summary"], queryFn: getJournalSummary, enabled, staleTime: 15_000, refetchInterval: 60_000 })
}
