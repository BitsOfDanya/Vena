import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { actionRepository } from "../api/repository"
import type { ActionStatus, CloseActionInput, CreateActionInput } from "./types"

const KEY = ["actions"] as const

export function useActions() {
  return useQuery({ queryKey: KEY, queryFn: () => actionRepository.list(), staleTime: 0 })
}

export function useCreateAction(now: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: CreateActionInput) => actionRepository.create(input, now),
    onSuccess: () => client.invalidateQueries({ queryKey: KEY }),
  })
}

export function useCloseAction(now: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: CloseActionInput) => actionRepository.close(input, now),
    onSuccess: () => client.invalidateQueries({ queryKey: KEY }),
  })
}

export function useSetActionStatus(now: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: ActionStatus }) => actionRepository.setStatus(id, status, now),
    onSuccess: () => client.invalidateQueries({ queryKey: KEY }),
  })
}

export function useApproveAction(now: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => actionRepository.approve(id, now),
    onSuccess: () => client.invalidateQueries({ queryKey: KEY }),
  })
}

export function useDismissAction(now: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => actionRepository.dismiss(id, now),
    onSuccess: () => client.invalidateQueries({ queryKey: KEY }),
  })
}
