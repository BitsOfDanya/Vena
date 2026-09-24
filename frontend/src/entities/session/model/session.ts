import { useQuery } from "@tanstack/react-query"

import { getSession } from "../api/session"

export const sessionQueryKey = ["session", "current"] as const

export function useSession() {
  return useQuery({ queryKey: sessionQueryKey, queryFn: getSession, retry: false, staleTime: 60_000 })
}
