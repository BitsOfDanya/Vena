"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { getNotificationSettings, getSystemNotices, notificationRepository } from "../api/repository"

const KEY = ["notifications"] as const

export function useNotifications() {
  return useQuery({ queryKey: KEY, queryFn: () => notificationRepository.list(), staleTime: 0 })
}

export function useSystemNotices() {
  return useQuery({ queryKey: ["system-notices"], queryFn: getSystemNotices, staleTime: 30_000 })
}

export function useNotificationSettings() {
  return useQuery({ queryKey: ["notification-settings"], queryFn: getNotificationSettings, staleTime: 60_000 })
}

export function useMarkNotificationsRead(now: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (ids: string[]) => notificationRepository.markRead(ids, now),
    onSuccess: (data) => client.setQueryData(KEY, data),
  })
}

export function useAcknowledgeNotification(now: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => notificationRepository.acknowledge(id, now),
    onSuccess: (data) => client.setQueryData(KEY, data),
  })
}

export function useResolveNotification(now: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => notificationRepository.resolve(id, now),
    onSuccess: (data) => client.setQueryData(KEY, data),
  })
}
