"use client"

import type { PulseSummary } from "@/entities/infrastructure"
import type { SnapshotStatus } from "@/entities/prediction"
import { formatClock, formatDateTime } from "@/shared/lib/time"
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

export function SnapshotLine({ snapshot }: { snapshot: SnapshotStatus | undefined }) {
  if (!snapshot) return null
  if (!snapshot.available) {
    return (
      <p className="text-[12px] text-status-critical">Снимок прогнозов недоступен · {snapshot.detail}</p>
    )
  }
  const days = snapshot.ageSeconds === null ? null : Math.floor(snapshot.ageSeconds / 86_400)
  return (
    <p className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-[12px] text-muted-foreground">
      <span className="font-medium tracking-[0.1em] text-faint uppercase">Снимок</span>
      <span className="font-mono tabular-nums">{snapshot.snapshotId}</span>
      <span className="font-mono tabular-nums">
        {snapshot.predictionTime === null ? "" : formatDateTime(snapshot.predictionTime)}
      </span>
      <span className="font-mono tabular-nums">{snapshot.predictionCount} прогнозов</span>
      <span className="font-mono tabular-nums">{snapshot.models.length} моделей</span>
      {snapshot.stream ? (
        <span className="font-mono tabular-nums text-vena">
          поток · {snapshot.stream.events} соб. · {Math.round(snapshot.stream.latencySeconds)} с
        </span>
      ) : null}
      {snapshot.stale && days !== null ? (
        <span className="text-vena">демо-снимок · {days} дн.</span>
      ) : null}
    </p>
  )
}

export function PulseSummaryModules({
  summary,
  apiMode = false,
  predictionsUnavailable = false,
  criticalCount = 0,
  criticalAssets = [],
  attentionCount = 0,
  risingCount = 0,
  risingTop = null,
  actionsDue,
  actionsOverdue,
  onInspectCritical,
  onViewChanges,
  onInvestigatePattern,
  onOpenPlan,
}: {
  summary: PulseSummary | undefined
  apiMode?: boolean
  predictionsUnavailable?: boolean
  criticalCount?: number
  criticalAssets?: string[]
  attentionCount?: number
  risingCount?: number
  risingTop?: string | null
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

  if (apiMode) {
    return (
      <div className="grid gap-2.5 md:grid-cols-2 xl:grid-cols-4">
        <Module
          title="Критично"
          value={predictionsUnavailable ? "—" : String(criticalCount).padStart(2, "0")}
          unit={criticalCount === 1 ? "объект" : "объектов"}
          tone={criticalCount > 0 ? "critical" : "neutral"}
          lines={
            predictionsUnavailable
              ? ["Прогнозы недоступны."]
              : criticalAssets.length > 0
                ? criticalAssets
                : ["Нет критичных рисков."]
          }
          actionLabel="Открыть"
          onAction={onInspectCritical}
        />
        <Module
          title="Внимание"
          value={predictionsUnavailable ? "—" : String(attentionCount).padStart(2, "0")}
          unit={attentionCount === 1 ? "объект" : "объектов"}
          tone={attentionCount > 0 ? "attention" : "neutral"}
          lines={predictionsUnavailable ? ["Прогнозы недоступны."] : ["высокий уровень риска модели"]}
          actionLabel="Открыть"
          onAction={onInspectCritical}
        />
        <Module
          title="Рост риска"
          value={predictionsUnavailable ? "—" : String(risingCount).padStart(2, "0")}
          unit="объектов"
          tone={risingCount > 0 ? "attention" : "neutral"}
          lines={
            predictionsUnavailable
              ? ["Прогнозы недоступны."]
              : risingTop
                ? ["наибольший прирост", risingTop]
                : ["Без изменений относительно предыдущего снимка."]
          }
          actionLabel="Смотреть изменения"
          onAction={onViewChanges}
        />
        <Module
          title="Работы к сроку"
          value={String(actionsDue).padStart(2, "0")}
          unit="за 24ч"
          tone={actionsOverdue > 0 ? "attention" : "neutral"}
          lines={[`${String(actionsOverdue).padStart(2, "0")} просрочено`]}
          actionLabel="Открыть план"
          onAction={onOpenPlan}
        />
      </div>
    )
  }

  return (
    <div className="grid gap-2.5 md:grid-cols-2 xl:grid-cols-4">
      <Module
        title="Критично"
        value={String(critical?.count ?? 0).padStart(2, "0")}
        unit={critical && critical.count === 1 ? "объект" : "объектов"}
        tone={critical && critical.count > 0 ? "critical" : "neutral"}
        lines={
          critical && critical.assets.length > 0
            ? critical.assets.map((asset) => `${asset.id} · ${asset.score}/100`)
            : ["Нет критичных рисков."]
        }
        actionLabel="Осмотреть"
        onAction={onInspectCritical}
      />
      <Module
        title="Рост риска"
        value={String(rising?.count ?? 0).padStart(2, "0")}
        unit={rising && rising.count === 1 ? "объект" : "объектов"}
        tone={rising && rising.count > 0 ? "attention" : "neutral"}
        lines={rising?.top ? [`наибольший прирост`, `${rising.top.id} +${rising.top.delta}`] : ["Без изменений за 6 часов."]}
        actionLabel="Смотреть изменения"
        onAction={onViewChanges}
      />
      <Module
        title="Новые паттерны"
        value={String(patterns?.count ?? 0).padStart(2, "0")}
        unit="обнаружено"
        tone={patterns && patterns.count > 0 ? "vena" : "neutral"}
        lines={
          patterns?.latest
            ? [`последний`, `Паттерн ${String(patterns.latest.number).padStart(3, "0")} · ${patterns.latest.systems} систем`]
            : ["Коррелированных паттернов нет."]
        }
        actionLabel="Исследовать"
        onAction={onInvestigatePattern}
      />
      <Module
        title="Работы к сроку"
        value={String(actionsDue).padStart(2, "0")}
        unit="за 24ч"
        tone={actionsOverdue > 0 ? "attention" : "neutral"}
        lines={[`${String(actionsOverdue).padStart(2, "0")} просрочено`]}
        actionLabel="Открыть план"
        onAction={onOpenPlan}
      />
    </div>
  )
}

export function ShiftSummary({ summary, completed }: { summary: PulseSummary | undefined; completed: number }) {
  if (!summary) return null
  const parts = [
    summary.shift.critical > 0 ? `+${summary.shift.critical} критичных` : null,
    summary.shift.patterns > 0 ? `+${summary.shift.patterns} паттерн${summary.shift.patterns === 1 ? "" : summary.shift.patterns < 5 ? "а" : "ов"}` : null,
    summary.shift.rising > 0 ? `+${summary.shift.rising} рост риска` : null,
    completed > 0 ? `${completed} работ${completed === 1 ? "а" : completed < 5 ? "ы" : ""} завершено` : null,
  ].filter((part): part is string => part !== null)

  return (
    <p className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-[12px] text-muted-foreground">
      <span className="font-medium tracking-[0.1em] text-faint uppercase">С {formatClock(summary.shift.since)}</span>
      {parts.length > 0 ? parts.map((part) => <span key={part}>{part}</span>) : <span>за смену без изменений</span>}
    </p>
  )
}
