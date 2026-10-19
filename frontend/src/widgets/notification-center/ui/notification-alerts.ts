"use client"

import * as React from "react"
import { toast } from "sonner"

import type { Notification } from "@/entities/notification"

const PREFIX = /^\(\d+\) /

export function useUnreadTitle(unread: number) {
  React.useEffect(() => {
    const apply = () => {
      const base = document.title.replace(PREFIX, "")
      const next = unread > 0 ? `(${unread}) ${base}` : base
      if (document.title !== next) document.title = next
    }
    apply()
    const observer = new MutationObserver(apply)
    observer.observe(document.head, { subtree: true, childList: true, characterData: true })
    return () => {
      observer.disconnect()
      document.title = document.title.replace(PREFIX, "")
    }
  }, [unread])
}

export function useCriticalToasts(list: Notification[] | undefined, onOpen: (item: Notification) => void) {
  const seen = React.useRef<Set<string> | null>(null)
  const openRef = React.useRef(onOpen)

  React.useEffect(() => {
    openRef.current = onOpen
  })

  React.useEffect(() => {
    if (!list) return
    if (seen.current === null) {
      seen.current = new Set(list.map((item) => item.id))
      return
    }
    for (const item of list) {
      if (seen.current.has(item.id)) continue
      seen.current.add(item.id)
      if (item.severity !== "critical" || item.status !== "new" || item.readAt !== null) continue
      toast.error(item.title, {
        id: `notification-${item.id}`,
        description: item.description,
        duration: 15_000,
        action: { label: "Открыть", onClick: () => openRef.current(item) },
      })
    }
  }, [list])
}
