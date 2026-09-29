"use client"

import type { PulseSummary } from "@/entities/infrastructure"
import type { SnapshotStatus } from "@/entities/prediction"
import { formatCount, plural } from "@/shared/lib/plural"
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
    <button
      type="button"
      onClick={onAction}
      className="group relative flex min-w-0 cursor-pointer flex-col border-r border-b border-border bg-elevated px-4 pt-3.5 pb-3 text-left outline-none transition-colors hover:bg-accent/40 focus-visible:z-10 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/60"
    >
      {tone === "critical" || tone === "attention" ? (
        <span aria-hidden className={cn("absolute inset-x-0 top-0 h-[3px]", tone === "critical" ? "bg-status-critical" : "bg-status-attention")} />
      ) : null}
      <span className="text-[12.5px] font-medium text-muted-foreground">{title}</span>
      <span className="mt-2 flex items-baseline gap-2">
        <span className={cn("font-mono text-[30px] leading-none font-medium tabular-nums", TONE_TEXT[tone])}>{value}</span>
        <span className="text-[14px] text-muted-foreground">{unit}</span>
      </span>
      <span className="mt-2 min-h-[36px] space-y-0.5">
        {lines.map((line) => (
          <span key={line} className="block truncate text-[13px] text-muted-foreground">
            {line}
          </span>
        ))}
      </span>
      <span className="mt-2 text-[13px] font-medium text-vena group-hover:underline group-hover:underline-offset-4">
        {actionLabel} →
      </span>
    </button>
  )
}

export function SnapshotLine({ snapshot }: { snapshot: SnapshotStatus | undefined }) {
  if (!snapshot) return null
  if (!snapshot.available) {
    return (
      <p className="text-[13px] text-status-critical">{snapshot.detail || "Снимок прогнозов недоступен"}</p>
    )
  }
  return (
    <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px] text-muted-foreground">
      <span className="inline-flex items-center gap-1.5">
        <span aria-hidden className={cn("size-1.5 rounded-full", snapshot.stream ? "bg-status-normal" : "bg-faint")} />
        {snapshot.stream ? "Поток СМВУ подключён" : "Прогноз по журналу"}
      </span>
      {snapshot.predictionTime === null ? null : <span>на {formatDateTime(snapshot.predictionTime)}</span>}
      <span aria-hidden className="text-border">|</span>
      <span className="tabular-nums">{formatCount(snapshot.predictionCount)} {plural(snapshot.predictionCount, ["прогноз", "прогноза", "прогнозов"])}</span>
      <span aria-hidden className="text-border">|</span>
      <span className="tabular-nums">{snapshot.models.length} {plural(snapshot.models.length, ["модель", "модели", "моделей"])}</span>
      {snapshot.stream ? (
        <>
          <span aria-hidden className="text-border">|</span>
          <span className="tabular-nums text-vena">
            {formatCount(snapshot.stream.events)} событий, задержка {Math.round(snapshot.stream.latencySeconds)} с
          </span>
        </>
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
      <div className="grid grid-cols-2 border-t border-l border-border lg:grid-cols-4">
        <Module
          title="Критично"
          value={predictionsUnavailable ? "—" : formatCount(criticalCount)}
          unit={plural(criticalCount, ["канал", "канала", "каналов"])}
          tone={criticalCount > 0 ? "critical" : "neutral"}
          lines={
            predictionsUnavailable
              ? ["Прогнозы недоступны."]
              : criticalAssets.length > 0
                ? criticalAssets
                : ["критичных рисков нет"]
          }
          actionLabel="Открыть"
          onAction={onInspectCritical}
        />
        <Module
          title="Внимание"
          value={predictionsUnavailable ? "—" : formatCount(attentionCount)}
          unit={plural(attentionCount, ["канал", "канала", "каналов"])}
          tone={attentionCount > 0 ? "attention" : "neutral"}
          lines={predictionsUnavailable ? ["Прогнозы недоступны."] : ["риск выше обычного, стоит проверить"]}
          actionLabel="Открыть"
          onAction={onInspectCritical}
        />
        <Module
          title="Рост риска"
          value={predictionsUnavailable ? "—" : formatCount(risingCount)}
          unit={plural(risingCount, ["канал", "канала", "каналов"])}
          tone={risingCount > 0 ? "attention" : "neutral"}
          lines={
            predictionsUnavailable
              ? ["Прогнозы недоступны."]
              : risingTop
                ? ["наибольший прирост", risingTop]
                : ["риск не вырос с прошлого расчёта"]
          }
          actionLabel="Смотреть изменения"
          onAction={onViewChanges}
        />
        <Module
          title="Работы к сроку"
          value={formatCount(actionsDue)}
          unit="на ближайшие 24 ч"
          tone={actionsOverdue > 0 ? "attention" : "neutral"}
          lines={[actionsOverdue > 0 ? `${actionsOverdue} просрочено` : "просроченных нет"]}
          actionLabel="Открыть план"
          onAction={onOpenPlan}
        />
      </div>
    )
  }

  return (
    <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
      <Module
        title="Критично"
        value={String(critical?.count ?? 0)}
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
        value={String(rising?.count ?? 0)}
        unit={rising && rising.count === 1 ? "объект" : "объектов"}
        tone={rising && rising.count > 0 ? "attention" : "neutral"}
        lines={rising?.top ? [`наибольший прирост`, `${rising.top.id} +${rising.top.delta}`] : ["Без изменений за 6 часов."]}
        actionLabel="Смотреть изменения"
        onAction={onViewChanges}
      />
      <Module
        title="Новые связки"
        value={String(patterns?.count ?? 0)}
        unit="обнаружено"
        tone={patterns && patterns.count > 0 ? "vena" : "neutral"}
        lines={
          patterns?.latest
            ? [`последняя`, `Связка ${String(patterns.latest.number).padStart(3, "0")} · ${patterns.latest.systems} систем`]
            : ["Коррелированных связок нет."]
        }
        actionLabel="Исследовать"
        onAction={onInvestigatePattern}
      />
      <Module
        title="Работы к сроку"
        value={String(actionsDue)}
        unit="за 24ч"
        tone={actionsOverdue > 0 ? "attention" : "neutral"}
        lines={[`${String(actionsOverdue)} просрочено`]}
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
    summary.shift.patterns > 0 ? `+${summary.shift.patterns} связк${summary.shift.patterns === 1 ? "а" : summary.shift.patterns < 5 ? "и" : "ок"}` : null,
    summary.shift.rising > 0 ? `+${summary.shift.rising} рост риска` : null,
    completed > 0 ? `${completed} работ${completed === 1 ? "а" : completed < 5 ? "ы" : ""} завершено` : null,
  ].filter((part): part is string => part !== null)

  return (
    <p className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-[12px] text-muted-foreground">
      <span className="font-medium text-faint">С {formatClock(summary.shift.since)}</span>
      {parts.length > 0 ? parts.map((part) => <span key={part}>{part}</span>) : <span>за смену без изменений</span>}
    </p>
  )
}
