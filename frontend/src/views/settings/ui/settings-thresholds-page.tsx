"use client"

import * as React from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"

import { useAuthSession } from "@/features/auth"
import { apiFetch, ApiError } from "@/shared/api/http"
import { useElementSize } from "@/shared/lib/hooks/use-element-size"
import { cn } from "@/shared/lib/utils"
import { Button } from "@/shared/ui/button"
import { Segmented } from "@/shared/ui/segmented"
import { Slider } from "@/shared/ui/slider"
import { LoadingBar, StateMessage } from "@/shared/ui/state-message"

import {
  LEVELS,
  nearestIndex,
  pointAt,
  sameLevels,
  sliderSteps,
  withLevel,
  type CurvePoint,
  type ThresholdLevel,
  type ThresholdLevels,
} from "../model/threshold-curve"
import { SettingsSection, SettingsShell } from "./settings-shell"

type ModelThresholds = {
  model_id: string
  label: string
  horizon_hours: number | null
  period: string | null
  base_rate: number | null
  default: ThresholdLevels | null
  override: ThresholdLevels | null
  effective: ThresholdLevels | null
  current: Partial<Record<ThresholdLevel, CurvePoint>>
  curve: CurvePoint[]
}

const QUERY_KEY = "model-thresholds"
const LEVEL_LABEL: Record<ThresholdLevel, string> = { critical: "Критично", high: "Внимание", medium: "Наблюдение" }
const LEVEL_COLOR: Record<ThresholdLevel, string> = {
  critical: "var(--status-critical)",
  high: "var(--status-attention)",
  medium: "var(--vena-soft)",
}
const CHART = { height: 164, left: 34, right: 8, top: 20, bottom: 34 }
const AXIS_TEXT = { fontSize: "10.5", fill: "var(--muted-foreground)" }

const errorText = (error: unknown) => (error instanceof ApiError ? error.detail : "Не удалось выполнить запрос")
const percent = (value: number | null | undefined) =>
  value == null ? "—" : value > 0 && value < 0.01 ? "<1%" : `${Math.round(value * 100)}%`
const decimal = (value: number | null | undefined, digits = 1) =>
  value == null ? "—" : value.toLocaleString("ru-RU", { minimumFractionDigits: digits, maximumFractionDigits: digits })

function metrics(item: ModelThresholds, threshold: number): CurvePoint | null {
  const exact = Object.values(item.current).find((point) => Math.abs(point.threshold - threshold) < 1e-9)
  return exact ?? pointAt(item.curve, threshold)
}

function CurveChart({
  curve,
  levels,
  selected,
  baseRate,
}: {
  curve: CurvePoint[]
  levels: ThresholdLevels
  selected: ThresholdLevel
  baseRate: number | null
}) {
  const [ref, size] = useElementSize<HTMLDivElement>()
  const width = Math.max(size.width, 280)
  const { height, left, right, top, bottom } = CHART
  const plotW = width - left - right
  const plotH = height - top - bottom
  const steps = curve.map((point) => point.threshold)
  const x = (index: number) => left + (curve.length > 1 ? index / (curve.length - 1) : 0.5) * plotW
  const y = (value: number) => top + (1 - value) * plotH
  const path = (key: "precision" | "recall") => {
    let pen = false
    return curve
      .map((point, index) => {
        const value = point[key]
        if (value == null) {
          pen = false
          return ""
        }
        const segment = `${pen ? "L" : "M"}${x(index).toFixed(1)},${y(value).toFixed(1)}`
        pen = true
        return segment
      })
      .join(" ")
      .trim()
  }
  const ticks = [...new Set([0, Math.floor((curve.length - 1) / 2), curve.length - 1])]

  return (
    <div ref={ref}>
      <svg width={width} height={height} className="block" role="img" aria-label="Точность и полнота в зависимости от порога">
        <text x={left} y={10} {...AXIS_TEXT}>
          точность и полнота, %
        </text>
        {[0, 0.5, 1].map((value) => (
          <g key={value}>
            <line x1={left} x2={left + plotW} y1={y(value)} y2={y(value)} stroke="var(--grid)" />
            <text x={left - 6} y={y(value) + 3.5} textAnchor="end" fontSize="10.5" fill="var(--muted-foreground)" fontFamily="var(--font-plex-mono)">
              {value * 100}%
            </text>
          </g>
        ))}
        {baseRate != null && baseRate > 0 && baseRate < 1 ? (
          <g>
            <line
              x1={left}
              x2={left + plotW}
              y1={y(baseRate)}
              y2={y(baseRate)}
              stroke="var(--muted-foreground)"
              strokeDasharray="5 4"
            />
            <text
              x={left + plotW - 2}
              y={y(baseRate) - 4}
              textAnchor="end"
              stroke="var(--elevated)"
              strokeWidth={3}
              paintOrder="stroke"
              {...AXIS_TEXT}
            >
              уровень случайного прогноза · {percent(baseRate)}
            </text>
          </g>
        ) : null}
        <path d={path("recall")} fill="none" stroke="var(--foreground)" strokeOpacity="0.5" strokeWidth="1.5" />
        <path d={path("precision")} fill="none" stroke="var(--vena)" strokeWidth="2" />
        {LEVELS.map((level) => {
          const px = x(nearestIndex(steps, levels[level]))
          return (
            <line
              key={level}
              x1={px}
              x2={px}
              y1={top}
              y2={top + plotH}
              stroke={LEVEL_COLOR[level]}
              strokeWidth={level === selected ? 2 : 1}
              strokeDasharray={level === selected ? undefined : "3 3"}
            />
          )
        })}
        {ticks.map((index) => (
          <text
            key={index}
            x={x(index)}
            y={top + plotH + 14}
            textAnchor={index === 0 ? "start" : index === curve.length - 1 ? "end" : "middle"}
            fontSize="10.5"
            fill="var(--muted-foreground)"
            fontFamily="var(--font-plex-mono)"
          >
            {decimal(curve[index]?.threshold, 3)}
          </text>
        ))}
        <text x={left + plotW / 2} y={height - 4} textAnchor="middle" {...AXIS_TEXT}>
          порог оценки модели
        </text>
      </svg>
    </div>
  )
}

function ThresholdCard({ item, admin }: { item: ModelThresholds; admin: boolean }) {
  const cache = useQueryClient()
  const [draft, setDraft] = React.useState<ThresholdLevels | null>(null)
  const [level, setLevel] = React.useState<ThresholdLevel>("high")
  const [busy, setBusy] = React.useState(false)
  const [message, setMessage] = React.useState("")
  const [error, setError] = React.useState("")
  const levels = draft ?? item.effective
  const steps = sliderSteps(item.curve)
  const dirty = draft !== null && !sameLevels(draft, item.effective)

  async function submit(method: "PUT" | "DELETE") {
    if (!levels) return
    setBusy(true)
    setError("")
    setMessage("")
    try {
      const saved = await apiFetch<ModelThresholds>(
        `/api/v1/ml/thresholds/${encodeURIComponent(item.model_id)}`,
        method === "PUT" ? { method, body: JSON.stringify(levels) } : { method }
      )
      cache.setQueryData<ModelThresholds[]>([QUERY_KEY], (list) => list?.map((entry) => (entry.model_id === saved.model_id ? saved : entry)))
      await cache.invalidateQueries({ predicate: (query) => query.queryKey[0] !== QUERY_KEY })
      setDraft(null)
      setMessage(method === "PUT" ? "Пороги сохранены" : "Возвращены пороги модели")
    } catch (e) {
      setError(errorText(e))
    } finally {
      setBusy(false)
    }
  }

  const point = levels ? metrics(item, levels[level]) : null

  return (
    <section className="border border-border bg-elevated">
      <header className="flex flex-wrap items-baseline justify-between gap-2 border-b border-border px-4 py-2.5">
        <h3 className="text-[14.5px] font-semibold">{item.label}</h3>
        <span className="font-mono text-[12px] text-muted-foreground">
          {item.model_id} · горизонт {item.horizon_hours ?? "—"} ч{item.override ? " · изменено" : ""}
        </span>
      </header>
      {!levels ? (
        <p className="px-4 py-3 text-[13px] text-muted-foreground">Модель не передала пороги в снимке прогнозов.</p>
      ) : (
        <>
          <dl className="grid grid-cols-3 divide-x divide-border-soft border-b border-border-soft">
            {LEVELS.map((entry) => {
              const stats = metrics(item, levels[entry])
              return (
                <div key={entry} className={cn("px-4 py-2.5", entry === level && "bg-accent/40")}>
                  <dt className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
                    <span aria-hidden className="inline-block size-2" style={{ background: LEVEL_COLOR[entry] }} />
                    {LEVEL_LABEL[entry]}
                  </dt>
                  <dd className="mt-0.5 font-mono text-[15px] tabular-nums">{decimal(levels[entry], 3)}</dd>
                  {stats ? (
                    <>
                      <dd className="text-[11.5px] text-muted-foreground tabular-nums">
                        точность {percent(stats.precision)} · полнота {percent(stats.recall)}
                      </dd>
                      <dd className="text-[11.5px] text-muted-foreground tabular-nums">
                        каналов в сутки {decimal(stats.channels_per_day)}
                      </dd>
                    </>
                  ) : null}
                </div>
              )
            })}
          </dl>
          <div className="space-y-3 px-4 py-3">
            <Segmented
              label={`Уровень для настройки: ${item.label}`}
              value={level}
              onChange={setLevel}
              options={LEVELS.map((entry) => ({ value: entry, label: LEVEL_LABEL[entry] }))}
            />
            {item.curve.length ? (
              <div>
                <CurveChart curve={item.curve} levels={levels} selected={level} baseRate={item.base_rate} />
                <p className="mt-1 flex flex-wrap gap-x-4 text-[11px] text-muted-foreground">
                  <span>
                    <span className="mr-1 inline-block size-2 bg-vena align-middle" /> точность
                  </span>
                  <span>
                    <span className="mr-1 inline-block size-2 bg-foreground/50 align-middle" /> полнота
                  </span>
                  {item.base_rate != null ? (
                    <span>
                      <span className="mr-1 inline-block w-3 border-t border-dashed border-muted-foreground align-middle" /> уровень
                      случайного прогноза — доля событий
                    </span>
                  ) : null}
                  {item.period ? <span>проверка {item.period}</span> : null}
                </p>
              </div>
            ) : (
              <p className="text-[12px] text-muted-foreground">
                Кривая «точность — полнота» для модели ещё не рассчитана: метрики появятся после расчёта на отложенной выборке.
              </p>
            )}
            <div className={cn(item.curve.length > 0 && "pr-2 pl-[34px]")}>
              <Slider
                aria-label={`Порог «${LEVEL_LABEL[level]}»`}
                min={0}
                max={steps.length - 1}
                step={1}
                value={[nearestIndex(steps, levels[level])]}
                disabled={!admin || busy}
                onValueChange={([index]) => {
                  const threshold = steps[index]
                  if (threshold !== undefined) setDraft(withLevel(levels, level, threshold))
                }}
              />
            </div>
            <p aria-live="polite" className="font-mono text-[12.5px] tabular-nums">
              порог {decimal(levels[level], 3)}
              {point
                ? ` · точность ${percent(point.precision)} · полнота ${percent(point.recall)} · каналов в сутки ${decimal(point.channels_per_day)} · вероятность ${percent(point.probability)}`
                : null}
            </p>
          </div>
          {admin ? (
            <div className="flex flex-wrap items-center gap-3 border-t border-border-soft px-4 py-2.5">
              <Button size="sm" disabled={!dirty || busy} onClick={() => void submit("PUT")}>
                Сохранить
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={busy || (!item.override && !dirty)}
                onClick={() => (item.override ? void submit("DELETE") : setDraft(null))}
              >
                Сбросить к значениям модели
              </Button>
              {message ? (
                <span role="status" className="text-[12px] text-muted-foreground">
                  {message}
                </span>
              ) : null}
              {error ? (
                <span role="alert" className="text-[12px] text-status-critical">
                  {error}
                </span>
              ) : null}
            </div>
          ) : null}
        </>
      )}
    </section>
  )
}

export function SettingsThresholdsPage() {
  const { me } = useAuthSession()
  const admin = me?.role === "admin"
  const thresholds = useQuery({
    queryKey: [QUERY_KEY],
    queryFn: () => apiFetch<ModelThresholds[]>("/api/v1/ml/thresholds"),
  })

  return (
    <SettingsShell title="Пороги и горизонты" descriptor="Уровни тревоги моделей прогноза: точность, полнота и нагрузка на диспетчера">
      <SettingsSection title="Пороги тревог по моделям" description="Порог выше — меньше тревог и выше точность, но больше пропусков.">
        <p className="text-[12px] text-muted-foreground">
          Новые пороги сразу меняют уровни прогнозов и ситуации; уведомления и черновики работ создаются по ним со следующего снимка.
        </p>
        {!admin ? <p className="text-sm text-muted-foreground">Изменять пороги может администратор.</p> : null}
        {thresholds.isPending ? (
          <LoadingBar className="min-h-24" />
        ) : thresholds.isError ? (
          <StateMessage title="Пороги недоступны" description="Не удалось загрузить пороги моделей." />
        ) : thresholds.data.length === 0 ? (
          <p className="text-[13px] text-muted-foreground">Снимок прогнозов ещё не загружен — настраивать пока нечего.</p>
        ) : (
          <div className="space-y-4">
            {thresholds.data.map((item) => (
              <ThresholdCard key={item.model_id} item={item} admin={admin} />
            ))}
          </div>
        )}
      </SettingsSection>
    </SettingsShell>
  )
}
