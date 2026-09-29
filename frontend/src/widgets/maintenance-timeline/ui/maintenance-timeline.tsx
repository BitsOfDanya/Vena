"use client"

import {
  KIND_LABEL,
  PRIORITY_LABEL,
  STATUS_LABEL,
  type ActionPriority,
  type MaintenanceAction,
} from "@/entities/maintenance"
import { StatusMark } from "@/entities/infrastructure"
import { HOUR, formatDateTime } from "@/shared/lib/time"
import { cn } from "@/shared/lib/utils"

const PRIORITY_MARK = { high: "critical", medium: "attention", low: "offline" } as const

const BAR_STYLE: Record<ActionPriority, string> = {
  high: "bg-status-critical",
  medium: "border border-status-attention [background-image:repeating-linear-gradient(135deg,var(--status-attention)_0_1px,transparent_1px_5px)]",
  low: "border border-dashed border-muted-foreground",
}

function share(value: number, now: number, span: number) {
  return Math.min(1, Math.max(0, (value - now) / span))
}

export function MaintenanceTimeline({
  actions,
  now,
  horizonHours,
  selectedId,
  onSelect,
}: {
  actions: MaintenanceAction[]
  now: number
  horizonHours: number
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  const span = horizonHours * HOUR
  const marks = [0, 24, 48, 72].filter((hour) => hour <= horizonHours)
  const sorted = [...actions].sort((left, right) => left.recommendedAt - right.recommendedAt)

  return (
    <div className="relative min-w-[760px] bg-elevated">
      <div className="grid grid-cols-[minmax(280px,340px)_1fr] border-b border-border-soft">
        <div className="px-6 py-2 text-[12px] font-medium text-muted-foreground">План работ</div>
        <div className="relative h-9 pr-6">
          {marks.map((hour) => (
            <span
              key={hour}
              className={cn("absolute top-2.5 text-[12px] font-medium", hour === 0 ? "text-foreground" : "text-faint")}
              style={{ left: `${(hour / horizonHours) * 100}%`, transform: hour === horizonHours ? "translateX(-100%)" : undefined }}
            >
              {hour === 0 ? "Сейчас" : `${hour} ч`}
            </span>
          ))}
        </div>
      </div>

      {sorted.length === 0 ? (
        <p className="px-6 py-8 text-[14px] text-muted-foreground">В выбранном окне работ не запланировано.</p>
      ) : (
        <ul className="relative">
          {sorted.map((action) => {
            const start = share(Math.max(action.windowStart, now), now, span)
            const end = share(action.recommendedAt, now, span)
            const width = Math.max(0.018, end - start)
            const overflow = action.recommendedAt - now > span
            const selected = action.id === selectedId
            return (
              <li key={action.id} className="border-b border-border-soft last:border-b-0">
                <button
                  type="button"
                  aria-pressed={selected}
                  onClick={() => onSelect(action.id)}
                  title={`${action.assetId} · ${KIND_LABEL[action.kind]} · ${action.reason}`}
                  className={cn(
                    "grid w-full grid-cols-[minmax(280px,340px)_1fr] items-center text-left outline-none hover:bg-surface focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/60",
                    selected && "bg-elevated"
                  )}
                >
                  <span className="flex items-center gap-3 px-6 py-3">
                    <StatusMark status={PRIORITY_MARK[action.priority]} />
                    <span className="min-w-0">
                      <span className="flex items-baseline gap-2">
                        <span className="font-mono text-[14px]">{action.assetId}</span>
                        <span className="text-[12px] font-medium text-faint">{PRIORITY_LABEL[action.priority]}</span>
                      </span>
                      <span className="mt-0.5 block truncate text-[13px] text-muted-foreground">
                        {KIND_LABEL[action.kind]} · {action.reason}
                      </span>
                    </span>
                  </span>
                  <span className="relative h-full min-h-14 pr-6">
                    {marks.map((hour) => (
                      <span key={hour} aria-hidden className={cn("absolute inset-y-0 border-l", hour === 0 ? "border-foreground" : "border-grid")} style={{ left: `${(hour / horizonHours) * 100}%` }} />
                    ))}
                    <span
                      className={cn("absolute top-1/2 h-3 -translate-y-1/2", BAR_STYLE[action.priority], selected && "outline outline-2 outline-offset-2 outline-vena")}
                      style={{ left: `${start * 100}%`, width: `${width * 100}%` }}
                    />
                    <span
                      className="absolute top-1/2 text-[12px] whitespace-nowrap text-muted-foreground"
                      style={
                        start + width > 0.6
                          ? { left: `${start * 100}%`, transform: "translate(calc(-100% - 10px), -50%)" }
                          : { left: `${(start + width) * 100}%`, transform: "translate(10px, -50%)" }
                      }
                    >
                      {STATUS_LABEL[action.status]}
                      {overflow ? " →" : ""}
                      <span className="ml-2 font-mono text-[12px] tabular-nums">{formatDateTime(action.recommendedAt)}</span>
                    </span>
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
