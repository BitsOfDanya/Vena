"use client"

import type { PulseSummary } from "@/entities/infrastructure"
import { formatClock } from "@/shared/lib/time"
import { cn } from "@/shared/lib/utils"

type Tone = "critical" | "attention" | "vena" | "neutral"

const TONE_TEXT: Record<Tone, string> = {
  critical: "text-status-critical",
  attention: "text-status-attention",
  vena: "text-vena",
  neutral: "text-foreground",
}

function Module({
  title,
  value,
  unit,
  tone,
  lines,
  actionLabel,
  onAction,
}: {
  title: string
  value: string
  unit: string
  tone: Tone
  lines: string[]
  actionLabel: string
  onAction: () => void
}) {
  return (
    <section className="flex min-w-0 flex-col rounded-[5px] border border-border bg-elevated px-3.5 py-2.5">
      <h3 className="text-[11px] font-medium tracking-[0.12em] text-muted-foreground uppercase">{title}</h3>
      <p className="mt-1 flex items-baseline gap-2">
        <span className={cn("font-mono text-[22px] leading-none tabular-nums", TONE_TEXT[tone])}>{value}</span>
        <span className="text-[13px] text-muted-foreground">{unit}</span>
      </p>
      <div className="mt-1 min-h-[30px] space-y-0.5">
        {lines.map((line) => (
          <p key={line} className="truncate font-mono text-[12px] text-muted-foreground tabular-nums">
            {line}
          </p>
        ))}
      </div>
      <button
        type="button"
        onClick={onAction}
        className="mt-1.5 self-start text-[13px] text-vena underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring/60"
      >
        {actionLabel} →
      </button>
    </section>
  )
}

export function PulseSummaryModules({
  summary,
  actionsDue,
  actionsOverdue,
  onInspectCritical,
  onViewChanges,
  onInvestigatePattern,
  onOpenPlan,
}: {
  summary: PulseSummary | undefined
  actionsDue: number
  actionsOverdue: number
  onInspectCritical: () => void
  onViewChanges: () => void
  onInvestigatePattern: () => void
  onOpenPlan: () => void
}) {
  const critical = summary?.critical
  const rising = summary?.rising
  const patterns = summary?.patterns

  return (
    <div className="grid gap-2.5 md:grid-cols-2 xl:grid-cols-4">
      <Module
        title="Critical"
        value={String(critical?.count ?? 0).padStart(2, "0")}
        unit={critical && critical.count === 1 ? "asset" : "assets"}
        tone={critical && critical.count > 0 ? "critical" : "neutral"}
        lines={
          critical && critical.assets.length > 0
            ? critical.assets.map((asset) => `${asset.id} · ${asset.score}/100`)
            : ["No critical risks."]
        }
        actionLabel="Inspect"
        onAction={onInspectCritical}
      />
      <Module
        title="Risk rising"
        value={String(rising?.count ?? 0).padStart(2, "0")}
        unit={rising && rising.count === 1 ? "asset" : "assets"}
        tone={rising && rising.count > 0 ? "attention" : "neutral"}
        lines={rising?.top ? [`largest increase`, `${rising.top.id} +${rising.top.delta}`] : ["No increases in 6 hours."]}
        actionLabel="View changes"
        onAction={onViewChanges}
      />
      <Module
        title="New patterns"
        value={String(patterns?.count ?? 0).padStart(2, "0")}
        unit="detected"
        tone={patterns && patterns.count > 0 ? "vena" : "neutral"}
        lines={
          patterns?.latest
            ? [`latest`, `Pattern ${String(patterns.latest.number).padStart(3, "0")} · ${patterns.latest.systems} systems`]
            : ["No correlated patterns."]
        }
        actionLabel="Investigate"
        onAction={onInvestigatePattern}
      />
      <Module
        title="Actions due"
        value={String(actionsDue).padStart(2, "0")}
        unit="within 24h"
        tone={actionsOverdue > 0 ? "attention" : "neutral"}
        lines={[`${String(actionsOverdue).padStart(2, "0")} overdue`]}
        actionLabel="Open plan"
        onAction={onOpenPlan}
      />
    </div>
  )
}

export function ShiftSummary({ summary, completed }: { summary: PulseSummary | undefined; completed: number }) {
  if (!summary) return null
  const parts = [
    summary.shift.critical > 0 ? `+${summary.shift.critical} critical` : null,
    summary.shift.patterns > 0 ? `+${summary.shift.patterns} pattern${summary.shift.patterns === 1 ? "" : "s"}` : null,
    summary.shift.rising > 0 ? `+${summary.shift.rising} increased risk` : null,
    completed > 0 ? `${completed} action${completed === 1 ? "" : "s"} completed` : null,
  ].filter((part): part is string => part !== null)

  return (
    <p className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-[12px] text-muted-foreground">
      <span className="font-medium tracking-[0.1em] text-faint uppercase">Since {formatClock(summary.shift.since)}</span>
      {parts.length > 0 ? parts.map((part) => <span key={part}>{part}</span>) : <span>no changes this shift</span>}
    </p>
  )
}
