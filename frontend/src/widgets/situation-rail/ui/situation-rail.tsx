"use client"

import Link from "next/link"
import * as React from "react"

import { useMlModels, useObjectHealthHistory, useSectionHealthHistory } from "@/entities/analytics"
import type { Situation } from "@/entities/infrastructure"
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

function probabilityOf(situation: Situation) {
  const value =
    situation.incidentProbability ??
    (situation.scoreText !== null && situation.riskScore !== null ? situation.riskScore : null)
  if (value === null || value === undefined) return null
  return Math.round(value <= 1 ? value * 100 : value)
}

function horizonText(situation: Situation) {
  if (situation.horizon == null) return null
  if (situation.horizon >= 72) return "за 3 суток"
  if (situation.horizon >= 24) return "за сутки"
  return `за ${situation.horizon} ч`
}

function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  if (!children) return null
  return (
    <div className="min-w-0">
      <dt className="text-[12px] font-medium text-faint">{label}</dt>
      <dd className="mt-0.5 text-[13.5px] text-foreground">{children}</dd>
    </div>
  )
}

function SituationCard({
  situation,
  now,
  onInspect,
  onAcknowledge,
  onCreateAction,
}: {
  situation: Situation
  now: number
  onInspect: (situation: Situation) => void
  onAcknowledge: (situation: Situation) => void
  onCreateAction: (situation: Situation) => void
}) {
  const [open, setOpen] = React.useState(false)
  const whyText = situation.recommendation?.hint || situation.primaryReason
  const actions = situation.recommendation?.actions ?? []
  const past = historyLine(situation)
  const group = situation.locationGroup ?? null
  const consequence = situation.recommendation?.consequence
  const critical = situation.severity === "critical"
  const probability = probabilityOf(situation)
  const horizon = horizonText(situation)

  return (
    <li className="relative px-4 py-4">
      <span aria-hidden className={cn("absolute inset-y-4 left-0 w-[3px] rounded-r-full", critical ? "bg-status-critical" : "bg-status-attention")} />
      <div className="flex items-start gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
            <span
              className={cn(
                "rounded-full px-2 py-0.5 text-[11.5px] font-medium",
                critical ? "bg-status-critical/12 text-status-critical" : "bg-status-attention/14 text-status-attention"
              )}
            >
              {critical ? "Критично" : "Внимание"}
            </span>
            {scenarioLabel(situation.scenario) ? (
              <span className="text-[12.5px] text-muted-foreground">{scenarioLabel(situation.scenario)}</span>
            ) : null}
            <span className="text-[12px] text-faint">· {formatAgo(situation.changedAt, now)}</span>
          </div>
          <h3 className={cn("mt-1.5 text-[16px] leading-snug font-semibold", situation.type === "pattern" && "text-vena")}>
            {whatText(situation)}
          </h3>
          {whereText(situation) ? <p className="mt-0.5 text-[13px] text-muted-foreground">{whereText(situation)}</p> : null}
        </div>
        {probability !== null ? (
          <div className="shrink-0 text-right">
            <p className={cn("text-[26px] leading-none font-semibold tabular-nums", critical ? "text-status-critical" : "text-status-attention")}>
              {probability}%
            </p>
            {horizon ? <p className="mt-1 text-[12px] text-muted-foreground">{horizon}</p> : null}
          </div>
        ) : null}
      </div>

      <dl className="mt-3 grid gap-3 sm:grid-cols-2">
        <Detail label="Почему">{whyText}</Detail>
        <Detail label="Первый шаг">{actions[0] ?? situation.recommendation?.title}</Detail>
        {consequence ? <Detail label="Если не отреагировать">{consequence}</Detail> : null}
      </dl>

      {open ? (
        <div className="mt-3 space-y-3 rounded-md bg-surface/60 p-3">
          {actions.length > 1 ? (
            <div>
              <p className="text-[12px] font-medium text-faint">Порядок действий</p>
              <ol className="mt-1 list-decimal space-y-0.5 pl-5 text-[13px]">
                {actions.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ol>
            </div>
          ) : null}
          {past ? (
            <p className="text-[13px]">
              <span className="text-faint">Так было раньше: </span>
              {past}
            </p>
          ) : null}
          {situation.healthIndex !== null && situation.healthIndex !== undefined ? (
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px]">
              <span>
                <span className="text-faint">Индекс здоровья участка: </span>
                <span className="font-medium tabular-nums">{situation.healthIndex} из 100</span>
              </span>
              {workflowMode === "api" && group ? <HealthSpark group={group} location={situation.location} /> : null}
            </div>
          ) : null}
          {workflowMode === "api" ? <ModelTrust situation={situation} /> : null}
        </div>
      ) : null}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {situation.status !== "action_created" ? (
          <button
            type="button"
            onClick={() => onCreateAction(situation)}
            className="h-8 cursor-pointer rounded-md bg-primary px-3 text-[13px] font-medium text-primary-foreground outline-none transition-opacity hover:opacity-90 focus-visible:ring-2 focus-visible:ring-ring/60"
          >
            Создать работу
          </button>
        ) : (
          <span className="rounded-md bg-status-normal/12 px-2.5 py-1 text-[12.5px] font-medium text-status-normal">Работа создана</span>
        )}
        {situation.status === "new" ? (
          <button
            type="button"
            onClick={() => onAcknowledge(situation)}
            className="h-8 cursor-pointer rounded-md border border-border px-3 text-[13px] outline-none hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring/60"
          >
            Принять
          </button>
        ) : situation.status === "acknowledged" ? (
          <span className="text-[12.5px] text-muted-foreground">Принято</span>
        ) : null}
        <button
          type="button"
          onClick={() => onInspect(situation)}
          className="h-8 cursor-pointer rounded-md px-2 text-[13px] text-vena outline-none hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring/60"
        >
          Показать на схеме
        </button>
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          className="ml-auto h-8 cursor-pointer rounded-md px-2 text-[13px] text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/60"
        >
          {open ? "Свернуть" : "Подробнее"}
        </button>
      </div>
    </li>
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
      <div className="px-5 py-10 text-center">
        <p className="text-[15px] font-medium">Всё спокойно</p>
        <p className="mt-1 text-[13.5px] text-muted-foreground">Ситуаций, требующих вмешательства, сейчас нет.</p>
      </div>
    )
  }

  return (
    <ul className={cn("divide-y divide-border", className)}>
      {situations.map((situation) => (
        <SituationCard
          key={situation.id}
          situation={situation}
          now={now}
          onInspect={onInspect}
          onAcknowledge={onAcknowledge}
          onCreateAction={onCreateAction}
        />
      ))}
    </ul>
  )
}
