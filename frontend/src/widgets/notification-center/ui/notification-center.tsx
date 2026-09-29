"use client"

import { Bell } from "lucide-react"
import { useRouter } from "next/navigation"
import * as React from "react"

import { StatusMark } from "@/entities/infrastructure"
import {
  NOTIFICATION_TYPE_LABEL,
  useAcknowledgeNotification,
  useMarkNotificationsRead,
  useNotifications,
  type Notification,
  type NotificationSeverity,
} from "@/entities/notification"
import { useWorkspace } from "@/features/workspace"
import { formatAgo } from "@/shared/lib/time"
import { cn } from "@/shared/lib/utils"
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/ui/popover"

const MARK: Record<NotificationSeverity, "critical" | "attention" | "normal"> = {
  critical: "critical",
  warning: "attention",
  info: "normal",
}

const FILTERS = [
  { key: "all", label: "Все" },
  { key: "critical", label: "Критично" },
  { key: "warning", label: "Внимание" },
  { key: "action", label: "Работы" },
  { key: "system", label: "Система" },
] as const

type FilterKey = (typeof FILTERS)[number]["key"]

function matches(item: Notification, filter: FilterKey) {
  if (filter === "all") return true
  if (filter === "critical" || filter === "warning") return item.severity === filter
  return item.type === filter || (filter === "system" && item.type === "integration")
}

export function NotificationCenter() {
  const router = useRouter()
  const { now, selectAsset } = useWorkspace()
  const [open, setOpen] = React.useState(false)
  const [filter, setFilter] = React.useState<FilterKey>("all")
  const notifications = useNotifications()
  const markRead = useMarkNotificationsRead(now)
  const acknowledge = useAcknowledgeNotification(now)
  const list = notifications.data ?? []
  const unread = list.filter((item) => item.readAt === null)
  const visible = list.filter((item) => matches(item, filter))

  function openCenter(next: boolean) {
    setOpen(next)
    if (next && unread.length > 0) markRead.mutate(unread.map((item) => item.id))
  }

  return (
    <Popover open={open} onOpenChange={openCenter}>
      <PopoverTrigger
        aria-label={unread.length > 0 ? `Уведомления, ${unread.length} непрочитанных` : "Уведомления"}
        className="relative flex size-8 cursor-pointer items-center justify-center text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/60"
      >
        <Bell className="size-[18px]" aria-hidden />
        {unread.length > 0 ? (
          <span className="absolute top-1 right-1 flex size-4 items-center justify-center rounded-full bg-status-critical font-mono text-[10px] text-background tabular-nums">
            {unread.length}
          </span>
        ) : null}
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[420px] p-0">
        <div className="flex items-center gap-3 border-b px-4 py-2.5">
          <h2 className="text-[14px] font-semibold">Уведомления</h2>
          <span className="font-mono text-[12px] text-faint tabular-nums">{list.length}</span>
        </div>
        <div className="flex items-center gap-1 border-b px-3 py-1.5">
          {FILTERS.map((item) => (
            <button
              key={item.key}
              type="button"
              aria-pressed={filter === item.key}
              onClick={() => setFilter(item.key)}
              className={cn(
                "px-2 py-1 text-[12px] outline-none focus-visible:ring-2 focus-visible:ring-ring/60",
                filter === item.key ? "font-medium text-foreground underline underline-offset-4" : "text-muted-foreground hover:text-foreground"
              )}
            >
              {item.label}
            </button>
          ))}
        </div>
        <ul className="max-h-[420px] overflow-y-auto">
          {visible.length === 0 ? (
            <li className="px-4 py-6 text-[13px] text-muted-foreground">Нет уведомлений в этой группе.</li>
          ) : (
            visible.map((item) => (
              <li key={item.id} className={cn("border-b px-4 py-3 last:border-b-0", item.status === "resolved" && "opacity-60")}>
                <div className="flex items-baseline gap-2">
                  <StatusMark status={MARK[item.severity]} className="translate-y-0.5" />
                  <p className="text-[13px] font-medium">{item.title}</p>
                  <span className="ml-auto font-mono text-[11px] text-faint tabular-nums">{formatAgo(item.createdAt, now)}</span>
                </div>
                <p className="mt-1 pl-5 text-[12px] text-muted-foreground">{item.description}</p>
                <div className="mt-2 flex items-center gap-3 pl-5">
                  <span className="text-[12px] text-faint">{NOTIFICATION_TYPE_LABEL[item.type]}</span>
                  {item.status !== "new" ? (
                    <span className="text-[12px] text-faint">{item.status === "resolved" ? "Закрыто" : "Принято"}</span>
                  ) : null}
                  <span className="ml-auto flex items-center gap-3">
                    {item.status === "new" ? (
                      <button
                        type="button"
                        onClick={() => acknowledge.mutate(item.id)}
                        className="text-[12px] text-muted-foreground underline-offset-4 outline-none hover:text-foreground hover:underline focus-visible:ring-2 focus-visible:ring-ring/60"
                      >
                        Принять
                      </button>
                    ) : null}
                    {item.assetId ? (
                      <button
                        type="button"
                        onClick={() => {
                          selectAsset(item.assetId)
                          setOpen(false)
                          router.push("/timeline")
                        }}
                        className="text-[12px] text-vena underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring/60"
                      >
                        Открыть
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => {
                          setOpen(false)
                          router.push("/pulse")
                        }}
                        className="text-[12px] text-vena underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring/60"
                      >
                        Открыть
                      </button>
                    )}
                  </span>
                </div>
              </li>
            ))
          )}
        </ul>
        <div className="border-t px-4 py-2">
          <button
            type="button"
            onClick={() => {
              setOpen(false)
              router.push("/settings/notifications")
            }}
            className="text-[12px] text-muted-foreground underline-offset-4 outline-none hover:text-foreground hover:underline focus-visible:ring-2 focus-visible:ring-ring/60"
          >
            Настройки уведомлений
          </button>
        </div>
      </PopoverContent>
    </Popover>
  )
}
