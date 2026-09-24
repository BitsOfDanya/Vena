"use client"

import { useQuery } from "@tanstack/react-query"

import { getMapNetwork } from "../api/network"

export function useMapNetwork() {
  return useQuery({ queryKey: ["map", "network"], queryFn: getMapNetwork, staleTime: 30_000 })
}
