"use client"

import { X } from "lucide-react"
import { useRouter } from "next/navigation"
import * as React from "react"

import { useSystemNotices, type NotificationSeverity } from "@/entities/notification"
import { cn } from "@/shared/lib/utils"

const TONE: Record<NotificationSeverity, string> = {
  critical: "border-status-critical/60 bg-status-critical/10 text-status-critical",
  warning: "border-status-attention/60 bg-status-attention/10 text-status-attention",
  info: "border-border bg-surface/60 text-foreground",
}

const DISMISSED_KEY = "vena.notices.dismissed"

function readDismissed(): string[] {
  try {
    const value = JSON.parse(sessionStorage.getItem(DISMISSED_KEY) ?? "[]")
    return Array.isArray(value) ? value : []
  } catch {
    return []
  }
}

export function SystemNoticeBar() {
  const router = useRouter()
  const notices = useSystemNotices()
  const [dismissed, setDismissed] = React.useState<string[]>(readDismissed)
  const visible = (notices.data ?? []).filter((notice) => !dismissed.includes(notice.id))

  if (visible.length === 0) return null

  return (
    <div className="shrink-0">
      {visible.map((notice) => (
        <div key={notice.id} role="status" className={cn("flex items-center gap-3 border-b px-4 py-2 sm:px-6", TONE[notice.severity])}>
          <p className="flex min-w-0 flex-col gap-0.5 sm:flex-row sm:items-baseline sm:gap-2">
            <span className="shrink-0 text-[13px] font-medium whitespace-nowrap">{notice.title}</span>
            <span className="line-clamp-2 text-[13px] text-muted-foreground sm:truncate">{notice.description}</span>
          </p>
          <span className="ml-auto flex shrink-0 items-center gap-4">
            {notice.href ? (
              <button
                type="button"
                onClick={() => router.push(notice.href as string)}
                className="text-[13px] underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring/60"
              >
                Открыть
              </button>
            ) : null}
            {notice.dismissible ? (
              <button
                type="button"
                aria-label="Скрыть"
                onClick={() =>
                  setDismissed((current) => {
                    const next = [...current, notice.id]
                    try {
                      sessionStorage.setItem(DISMISSED_KEY, JSON.stringify(next))
                    } catch {}
                    return next
                  })
                }
                className="text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/60"
              >
                <X className="size-4" aria-hidden />
              </button>
            ) : null}
          </span>
        </div>
      ))}
    </div>
  )
}
