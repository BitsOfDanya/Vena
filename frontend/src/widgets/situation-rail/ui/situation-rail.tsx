"use client"

import { StatusMark, type Situation } from "@/entities/infrastructure"
import { formatAgo } from "@/shared/lib/time"
import { cn } from "@/shared/lib/utils"

export function SituationRail({
  className,
  situations,
  now,
  onInspect,
  onAcknowledge,
  onCreateAction,
}: {
  className?: string
  situations: Situation[]
  now: number
  onInspect: (situation: Situation) => void
  onAcknowledge: (situation: Situation) => void
  onCreateAction: (situation: Situation) => void
}) {
  if (situations.length === 0) {
    return (
      <div className="border border-border bg-elevated px-5 py-6">
        <p className="text-[13px] font-medium tracking-[0.06em] text-muted-foreground uppercase">Nothing needs attention</p>
        <p className="mt-1 text-[14px] text-muted-foreground">В выбранном окне нет объектов и паттернов, требующих вмешательства.</p>
      </div>
    )
  }

  return (
    <ul className={cn("border border-border bg-elevated", className)}>
      {situations.map((situation) => (
        <li
          key={situation.id}
          className="grid grid-cols-[3px_1fr] gap-3 border-b border-border-soft last:border-b-0"
        >
          <span
            aria-hidden
            className={cn("self-stretch", situation.severity === "critical" ? "bg-status-critical" : "bg-status-attention")}
          />
          <div className="min-w-0 py-2 pr-4">
            <div className="flex flex-wrap items-baseline gap-x-3">
              <StatusMark status={situation.severity === "critical" ? "critical" : "attention"} className="translate-y-0.5 size-3" />
              <span className={cn("text-[15px] font-semibold", situation.type === "pattern" && "text-vena")}>{situation.title}</span>
              {situation.scoreText !== null ? (
                <span className="font-mono text-[13px] tabular-nums">{situation.scoreText}</span>
              ) : null}
              {situation.delta !== null && situation.delta !== 0 ? (
                <span
                  className={cn(
                    "font-mono text-[13px] tabular-nums",
                    situation.delta > 0 ? "text-status-attention" : "text-muted-foreground"
                  )}
                >
                  {situation.delta > 0 ? "↑" : "↓"}
                  {Math.abs(situation.delta) < 1 ? Math.abs(situation.delta).toFixed(3) : Math.abs(Math.round(situation.delta))}
                </span>
              ) : null}
              {situation.horizon !== null ? <span className="font-mono text-[12px] text-faint">{situation.horizon}h</span> : null}
              <span className="ml-auto font-mono text-[12px] text-faint tabular-nums">{formatAgo(situation.changedAt, now)}</span>
            </div>
            <div className="mt-0.5 flex flex-wrap items-baseline gap-x-4">
              <p className="min-w-0 flex-1 truncate text-[13px] text-muted-foreground">{situation.primaryReason}</p>
              <span className="flex shrink-0 items-center gap-3">
                <button
                  type="button"
                  onClick={() => onInspect(situation)}
                  className="text-[13px] font-medium text-vena underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring/60"
                >
                  Inspect
                </button>
                {situation.status === "new" ? (
                  <button
                    type="button"
                    onClick={() => onAcknowledge(situation)}
                    className="text-[13px] text-muted-foreground underline-offset-4 outline-none hover:text-foreground hover:underline focus-visible:ring-2 focus-visible:ring-ring/60"
                  >
                    Acknowledge
                  </button>
                ) : null}
                {situation.status !== "action_created" ? (
                  <button
                    type="button"
                    onClick={() => onCreateAction(situation)}
                    className="text-[13px] text-muted-foreground underline-offset-4 outline-none hover:text-foreground hover:underline focus-visible:ring-2 focus-visible:ring-ring/60"
                  >
                    Create action
                  </button>
                ) : (
                  <span className="text-[12px] tracking-[0.04em] text-faint uppercase">action created</span>
                )}
                {situation.status === "acknowledged" ? (
                  <span className="text-[12px] tracking-[0.04em] text-faint uppercase">ack</span>
                ) : null}
              </span>
            </div>
          </div>
        </li>
      ))}
    </ul>
  )
}
