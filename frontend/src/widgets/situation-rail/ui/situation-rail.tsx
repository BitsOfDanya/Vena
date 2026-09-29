"use client"

import Link from "next/link"
import * as React from "react"

import { useMlModels, useObjectHealthHistory, useSectionHealthHistory } from "@/entities/analytics"
import { StatusMark, type Situation } from "@/entities/infrastructure"
import { SCENARIO_LABEL, type PredictionScenario } from "@/entities/prediction"
import {
  leadTimeLine,
  topKTrustLine,
  verifiedLine,
} from "@/entities/analytics"
import { workflowMode } from "@/shared/config/env"
import { formatAgo } from "@/shared/lib/time"
import { cn } from "@/shared/lib/utils"

function scenarioLabel(scenario: string | null | undefined) {
  if (!scenario) return null
  return SCENARIO_LABEL[scenario as PredictionScenario] ?? scenario
}

function historyLine(situation: Situation) {
  const history = situation.history
  if (!history || history.episodes365d <= 0) return null
  const parts = [`${history.episodes365d} эпизодов за год`]
  if (history.channels > 0) parts.push(`${history.channels} каналов`)
  if (history.lastEpisodeAt) {
    const days = Math.max(0, Math.round((Date.now() - history.lastEpisodeAt) / (24 * 3600_000)))
    parts.push(days === 0 ? "последний сегодня" : `последний ${days} дн. назад`)
  }
  if (history.medianDurationMinutes != null && history.medianDurationMinutes > 0) {
    const hours = history.medianDurationMinutes / 60
    parts.push(hours >= 1 ? `медиана ${hours.toFixed(1)} ч` : `медиана ${Math.round(history.medianDurationMinutes)} мин`)
  }
  return parts.join(" · ")
}

function whatText(situation: Situation) {
  if (situation.recommendation?.what) return situation.recommendation.what
  if (situation.recommendation?.title) return situation.recommendation.title
  return situation.summary || situation.title
}

function objectIdFromLocation(location: string | null | undefined) {
  const match = location?.match(/Объект\s+(\d+)/i)
  return match?.[1] ?? null
}

function whenText(situation: Situation) {
  const probability =
    situation.incidentProbability ??
    (situation.scoreText !== null && situation.riskScore !== null ? situation.riskScore : null)
  const pct =
    probability === null
      ? situation.scoreText
      : `вероятность ${Math.round(probability * 100)} %`
  const horizon =
    situation.horizon == null
      ? null
      : situation.horizon >= 24
        ? `В ближайшие ${Math.round(situation.horizon / 24)} ${situation.horizon >= 72 ? "суток" : "сут."}`
        : `В ближайшие ${situation.horizon} ч`
  if (horizon && pct) return `${horizon}, ${pct}`
  return horizon ?? pct
}

function whereText(situation: Situation) {
  const parts: string[] = []
  if (situation.location) parts.push(situation.location)
  const count = situation.assetCount ?? situation.assetIds.length
  if (count > 1) parts.push(`${count} каналов на участке`)
  else if (situation.assetIds[0]) parts.push(`канал ${situation.assetIds[0]}`)
  return parts.join(" · ") || null
}

function HealthSpark({ group, location }: { group: string; location?: string | null }) {
  const section = useSectionHealthHistory(group)
  const objects = useObjectHealthHistory()
  const objectId = objectIdFromLocation(location)
  const objectSeries = objectId ? objects.data?.objects[objectId] : undefined
  const points =
    (section.data?.length ?? 0) >= 2 ? section.data! : (objectSeries?.length ?? 0) >= 2 ? objectSeries! : []
  if (section.isPending && objects.isPending) return null
  if (points.length < 2) return null
  const values = points.map((point) => point.value)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = Math.max(1, max - min)
  const width = 120
  const height = 28
  const path = points
    .map((point, index) => {
      const x = (index / (points.length - 1)) * width
      const y = height - ((point.value - min) / span) * (height - 4) - 2
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(" ")
  const newest = values[values.length - 1]
  const weekAgo = values[Math.max(0, values.length - 8)]
  const trend =
    newest == null || weekAgo == null
      ? null
      : newest < weekAgo - 2
        ? "хуже, чем неделю назад"
        : newest > weekAgo + 2
          ? "лучше, чем неделю назад"
          : "как неделю назад"
  return (
    <span className="inline-flex items-center gap-2">
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden className="text-vena">
        <path d={path} fill="none" stroke="currentColor" strokeWidth="1.5" />
      </svg>
      {trend ? <span className="text-[11px] text-faint">{trend}</span> : null}
    </span>
  )
}

function ModelTrust({ situation }: { situation: Situation }) {
  const models = useMlModels()
  const modelId = situation.modelId
  const card = (models.data ?? []).find((item) => item.name === modelId)
  const scenario = scenarioLabel(situation.scenario) ?? "Модель"
  const hours = situation.horizon
  const term =
    hours == null ? "" : hours >= 72 ? ", 3 суток" : hours >= 24 ? ", сутки" : `, ${hours} ч`
  const href = modelId ? `/models#${modelId}` : "/models"
  const trust = card
    ? topKTrustLine(card.heldOut?.precisionTop5PerDay, card.horizonHours)
    : null
  const lead = card
    ? leadTimeLine(card.leadTime?.medianLeadTimeHours, card.leadTime?.alertPrecisionDedup)
    : null
  const verified = card ? verifiedLine(card.heldOut?.period) : "проверена на январе–июне 2026"

  return (
    <div className="mt-0.5 space-y-0.5 text-[12px] text-muted-foreground">
      <p>
        <span className="text-faint">Модель · </span>
        {scenario}
        {term} · {verified} ·{" "}
        <Link href={href} className="text-vena underline-offset-4 hover:underline">
          карточка модели →
        </Link>
      </p>
      {trust ? <p className="text-[12px]">{trust}</p> : null}
      {lead ? <p className="text-[12px] text-faint">{lead}</p> : null}
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  if (!children) return null
  return (
    <p className="mt-0.5 text-[13px] text-muted-foreground">
      <span className="text-faint">{label} · </span>
      {children}
    </p>
  )
}

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
        <p className="text-[13px] font-medium tracking-[0.06em] text-muted-foreground uppercase">Внимание не требуется</p>
        <p className="mt-1 text-[14px] text-muted-foreground">В выбранном окне нет объектов и паттернов, требующих вмешательства.</p>
      </div>
    )
  }

  return (
    <ul className={cn("border border-border bg-elevated", className)}>
      {situations.map((situation) => {
        const whyText = situation.recommendation?.hint || situation.primaryReason
        const actions = situation.recommendation?.actions.slice(0, 3) ?? []
        const past = historyLine(situation)
        const group = situation.locationGroup ?? null
        const consequence = situation.recommendation?.consequence
        const severityStatus = situation.severity === "critical" ? "critical" : "attention"

        return (
          <li
            key={situation.id}
            className="grid grid-cols-[3px_1fr] gap-3 border-b border-border-soft last:border-b-0"
          >
            <span
              aria-hidden
              className={cn("self-stretch", situation.severity === "critical" ? "bg-status-critical" : "bg-status-attention")}
            />
            <div className="min-w-0 py-2.5 pr-4">
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <StatusMark status={severityStatus} className="translate-y-0.5 size-3" />
                <span className={cn("text-[15px] font-semibold", situation.type === "pattern" && "text-vena")}>
                  {situation.title}
                </span>
                <span className="ml-auto font-mono text-[12px] text-faint tabular-nums">{formatAgo(situation.changedAt, now)}</span>
              </div>

              <div className="mt-1.5 space-y-0">
                <Field label="Что">{whatText(situation)}</Field>
                <Field label="Где">{whereText(situation)}</Field>
                <Field label="Когда">{whenText(situation)}</Field>
                <Field label="Почему">{whyText}</Field>
                {consequence ? <Field label="Последствие">{consequence}</Field> : null}
                {situation.recommendation ? (
                  <div className="mt-0.5 text-[13px] text-muted-foreground">
                    <p>
                      <span className="text-faint">Что делать · </span>
                      {situation.recommendation.title}
                    </p>
                    {actions.length > 0 ? (
                      <ol className="mt-0.5 list-decimal space-y-0.5 pl-4 text-[12px]">
                        {actions.map((step) => (
                          <li key={step}>{step}</li>
                        ))}
                      </ol>
                    ) : null}
                  </div>
                ) : null}
                {past ? <Field label="Так было раньше">{past}</Field> : null}
                {situation.healthIndex !== null && situation.healthIndex !== undefined ? (
                  <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-muted-foreground">
                    <span>
                      <span className="text-faint">Здоровье · </span>
                      <span className="font-mono tabular-nums">{situation.healthIndex} из 100</span>
                    </span>
                    {workflowMode === "api" && group ? <HealthSpark group={group} location={situation.location} /> : null}
                  </div>
                ) : null}
                {workflowMode === "api" ? <ModelTrust situation={situation} /> : null}
              </div>

              <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1">
                <button
                  type="button"
                  onClick={() => onInspect(situation)}
                  className="cursor-pointer text-[13px] font-medium text-vena underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring/60"
                >
                  В дереве
                </button>
                {situation.status === "new" ? (
                  <button
                    type="button"
                    onClick={() => onAcknowledge(situation)}
                    className="cursor-pointer text-[13px] text-muted-foreground underline-offset-4 outline-none hover:text-foreground hover:underline focus-visible:ring-2 focus-visible:ring-ring/60"
                  >
                    Принять
                  </button>
                ) : null}
                {situation.status !== "action_created" ? (
                  <button
                    type="button"
                    onClick={() => onCreateAction(situation)}
                    className="cursor-pointer text-[13px] text-muted-foreground underline-offset-4 outline-none hover:text-foreground hover:underline focus-visible:ring-2 focus-visible:ring-ring/60"
                  >
                    Создать работу
                  </button>
                ) : (
                  <span className="text-[12px] tracking-[0.04em] text-faint uppercase">работа создана</span>
                )}
                {situation.status === "acknowledged" ? (
                  <span className="text-[12px] tracking-[0.04em] text-faint uppercase">принято</span>
                ) : null}
              </div>
            </div>
          </li>
        )
      })}
    </ul>
  )
}
