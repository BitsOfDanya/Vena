import { useQuery } from "@tanstack/react-query"

import { getDataActivity, getDataChannels, getDataEvents, getDataObjects, getDataSummary } from "../api/data"

export function useDataSummary() { return useQuery({ queryKey: ["data", "summary"], queryFn: getDataSummary, refetchInterval: 10_000 }) }
export function useDataActivity() { return useQuery({ queryKey: ["data", "activity"], queryFn: getDataActivity, refetchInterval: 10_000 }) }
export function useDataEvents() { return useQuery({ queryKey: ["data", "events"], queryFn: getDataEvents, refetchInterval: 10_000 }) }
export function useDataObjects() { return useQuery({ queryKey: ["data", "objects"], queryFn: getDataObjects }) }
export function useDataChannels() { return useQuery({ queryKey: ["data", "channels"], queryFn: getDataChannels }) }
