"use client"

import Link from "next/link"
import * as React from "react"

import { useAlarmKpis, useEffectReport, leadHorizonPhrase } from "@/entities/analytics"
import { OPEN_STATUSES, useActions } from "@/entities/maintenance"
import { SCENARIO_LABEL, useBackendSituations, modelLabel, type PredictionScenario } from "@/entities/prediction"
import { ApiError } from "@/shared/api/http"
import { workflowMode } from "@/shared/config/env"
import { cn } from "@/shared/lib/utils"
import { Button } from "@/shared/ui/button"
import { LoadingBar, StateMessage } from "@/shared/ui/state-message"

import { ForecastVsFactPanel } from "./forecast-vs-fact-panel"

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

const STATUS_RU: Record<string, string> = {
  new: "нужна работа",
  acknowledged: "принято",
  action_created: "работа есть",
  resolved: "закрыто",
}

function Metric({
  title,
  value,
  unit,
  detail,
}: {
  title: string
  value: string
  unit?: string
  detail?: string
}) {
  return (
    <section className="border-r border-b border-border bg-elevated px-4 py-3.5">
      <h3 className="text-[12.5px] font-medium text-muted-foreground">{title}</h3>
      <p className="mt-2 flex items-baseline gap-2">
        <span className="font-mono text-[28px] leading-none font-medium tabular-nums">{value}</span>
        {unit ? <span className="text-[13px] text-muted-foreground">{unit}</span> : null}
      </p>
      {detail ? <p className="mt-2 text-[12px] text-muted-foreground">{detail}</p> : null}
    </section>
  )
}

function pct(value: number | null | undefined) {
  if (value === null || value === undefined) return "—"
  return `${Math.round(value * 100)}%`
}

async function downloadFile(path: string, filename: string, accept: string) {
  const response = await fetch(`${API_URL}${path}`, {
    credentials: "include",
    headers: { Accept: accept },
  })
  if (!response.ok) throw new ApiError(response.status, response.statusText)
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = url
  link.download = filename
  link.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function monthLabel(start: string) {
  if (!start) return "—"
  const stamp = start.slice(0, 7)
  const [year, month] = stamp.split("-")
  if (!year || !month) return stamp
  return `${month}.${year.slice(2)}`
}

function AlarmLoadBlock() {
  const kpis = useAlarmKpis()
  if (kpis.isPending) return <LoadingBar className="min-h-24" />
  if (kpis.isError || !kpis.data?.recent) return null
  const recent = kpis.data.recent
  const over = recent.perHourMean > kpis.data.manageablePerHour
  const manageable = kpis.data.manageablePerHour
  const months = kpis.data.months.slice(-12)
  const maxMonth = Math.max(manageable, ...months.map((item) => item.perHourMean), 1)
  return (
    <section className="border border-border bg-elevated">
      <div className="border-b border-border-soft px-4 py-3">
        <h2 className="text-[15px] font-semibold">Нагрузка тревог · ISA-18.2</h2>
        <p className="mt-1 text-[12px] text-muted-foreground">
          {recent.start && recent.end ? `${recent.start} — ${recent.end}` : "Последний месяц"} · норма до {manageable}/ч
        </p>
      </div>
      <div className="grid gap-3 px-4 py-3 sm:grid-cols-2 xl:grid-cols-4">
        <div>
          <p className="text-[12px] text-faint">Тревог в час</p>
          <p className={cn("mt-1 font-mono text-[22px] tabular-nums", over && "text-status-attention")}>
            {recent.perHourMean.toFixed(1)}
          </p>
        </div>
        <div>
          <p className="text-[12px] text-faint">Доля лавин</p>
          <p className="mt-1 font-mono text-[22px] tabular-nums">{pct(recent.activationsInFloods)}</p>
        </div>
        <div>
          <p className="text-[12px] text-faint">Топ-10 каналов</p>
          <p className="mt-1 font-mono text-[22px] tabular-nums">{pct(recent.top10Share)}</p>
        </div>
        <div>
          <p className="text-[12px] text-faint">Серии ППР</p>
          <p className="mt-1 font-mono text-[22px] tabular-nums">{pct(recent.maintenanceShare)}</p>
        </div>
      </div>
      {months.length > 0 ? (
        <div className="border-t border-border-soft px-4 py-3">
          <p className="text-[12px] font-medium">Тревог в час по месяцам</p>
          <div className="mt-2 flex h-16 items-end gap-1">
            {months.map((item) => {
              const height = Math.max(4, Math.round((item.perHourMean / maxMonth) * 52))
              const monthOver = item.perHourMean > manageable
              return (
                <div
                  key={item.start}
                  className="flex min-w-0 flex-1 flex-col items-center gap-1"
                  title={`${monthLabel(item.start)}: ${item.perHourMean.toFixed(1)}/ч`}
                >
                  <div
                    className={cn("w-full max-w-6", monthOver ? "bg-status-attention" : "bg-vena/70")}
                    style={{ height }}
                  />
                  <span className="truncate font-mono text-[9px] text-faint">{monthLabel(item.start)}</span>
                </div>
              )
            })}
          </div>
        </div>
      ) : null}
      {recent.chatteringTop.length > 0 ? (
        <div className="border-t border-border-soft px-4 py-3">
          <p className="text-[12px] font-medium">Дребезжащие каналы — на ремонт датчиков</p>
          <ul className="mt-2 space-y-1">
            {recent.chatteringTop.slice(0, 8).map((item) => (
              <li key={item.channelId} className="flex justify-between gap-3 text-[13px]">
                <span className="truncate">{item.name ?? item.channelId}</span>
                <span className="font-mono tabular-nums text-muted-foreground">{item.activations}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  )
}

export function EffectPage() {
  const effect = useEffectReport()
  const situations = useBackendSituations()
  const actions = useActions()
  const apiMode = workflowMode === "api"
  const [downloading, setDownloading] = React.useState<string | null>(null)
  const [downloadError, setDownloadError] = React.useState<string | null>(null)

  const openActions = (actions.data ?? []).filter((action) => OPEN_STATUSES.includes(action.status))
  const topLocations = [...(situations.data ?? [])]
    .filter((item) => item.location)
    .sort((a, b) => {
      const hi = (a.healthIndex ?? 101) - (b.healthIndex ?? 101)
      if (hi !== 0) return hi
      return (b.incidentProbability ?? b.riskScore ?? 0) - (a.incidentProbability ?? a.riskScore ?? 0)
    })
    .slice(0, 8)

  function runDownload(kind: "xlsx" | "csv" | "xml") {
    setDownloading(kind)
    setDownloadError(null)
    const job =
      kind === "xlsx"
        ? downloadFile("/api/v1/reports/management.xlsx", "vena-management-report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        : kind === "csv"
          ? downloadFile("/api/v1/reports/predictions.csv", "vena-predictions.csv", "text/csv")
          : downloadFile("/api/v1/reports/predictions.xml", "vena-predictions.xml", "application/xml")
    void job.catch(() => setDownloadError("Не удалось скачать файл.")).finally(() => setDownloading(null))
  }

  if (!apiMode) {
    return (
      <StateMessage
        title="Эффект доступен в API-режиме"
        description="Подключите workflowMode=api и снимок прогнозов, чтобы видеть отчёт для руководства."
      />
    )
  }

  const headline =
    effect.data != null
      ? `Подтверждено ${effect.data.confirmed}, выездов избежано ${effect.data.dispatchesAvoided}, каналов в риске ${effect.data.channelsAtRisk}`
      : null

  return (
    <div className="flex size-full min-h-0 flex-col overflow-auto print:overflow-visible">
      <div className="flex shrink-0 flex-wrap items-end gap-x-6 gap-y-3 px-6 pt-5 pb-3 print:border-b print:pb-4">
        <div>
          <h1 className="text-[24px] font-semibold tracking-[-0.01em]">Эффект</h1>
          <p className="text-[13px] text-muted-foreground">Что модели предсказали, насколько заранее и что решили диспетчеры</p>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2 print:hidden">
          <span className="text-[12.5px] text-muted-foreground">Выгрузка</span>
          <div className="inline-flex h-8 divide-x divide-border border border-border bg-elevated">
            {(["xlsx", "csv", "xml"] as const).map((kind) => (
              <button
                key={kind}
                type="button"
                disabled={downloading !== null}
                onClick={() => runDownload(kind)}
                className="cursor-pointer px-3 font-mono text-[12px] uppercase outline-none hover:bg-accent focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/60 disabled:opacity-50"
              >
                {downloading === kind ? "…" : kind}
              </button>
            ))}
          </div>
          <Button variant="outline" size="sm" onClick={() => window.print()}>
            Печать / PDF
          </Button>
        </div>
      </div>
      {downloadError ? <p className="px-6 pb-2 text-[13px] text-status-critical print:hidden">{downloadError}</p> : null}
      {headline ? <p className="px-6 pb-3 text-[14px] font-medium">{headline}</p> : null}

      <div className="space-y-6 px-6 pb-8">
        {effect.isPending ? (
          <LoadingBar className="min-h-40" />
        ) : effect.isError ? (
          <StateMessage
            title="Отчёт недоступен"
            description="Не удалось загрузить аналитику эффекта. Проверьте снимок прогнозов."
            action={
              <Button variant="outline" size="sm" onClick={() => effect.refetch()}>
                Повторить
              </Button>
            }
          />
        ) : effect.data ? (
          <>
            <div className="grid border-t border-l border-border sm:grid-cols-2 xl:grid-cols-4">
              <Metric title="Каналы в риске" value={String(effect.data.channelsAtRisk)} unit="сейчас" />
              <Metric title="Инциденты" value={String(effect.data.incidents)} unit="групп" />
              <Metric
                title="Подтверждено"
                value={String(effect.data.confirmed)}
                detail={`Решено ${effect.data.decided} · отклонено ${effect.data.rejected}`}
              />
              <Metric
                title="Выезды избежаны"
                value={String(effect.data.dispatchesAvoided)}
                detail="Ложные/нерелевантные по журналу решений"
              />
            </div>

            <div className="grid border-t border-l border-border sm:grid-cols-2 xl:grid-cols-4">
              <Metric title="Тревоги за 30 дней" value={String(effect.data.alarms30d)} />
              <Metric
                title="К проверке"
                value={String(effect.data.alarmsToVerify)}
                detail={
                  effect.data.alarmFilterShare === null
                    ? undefined
                    : `Фильтр срезает ${pct(effect.data.alarmFilterShare)} неподтверждённых`
                }
              />
              <Metric title="Доступ за 30 дней" value={String(effect.data.accessEvents30d)} unit="событий" />
              <Metric title="Прогнозов в журнале" value={String(effect.data.forecastsInJournal)} />
            </div>

            <section className="border border-border bg-elevated">
              <div className="border-b border-border-soft px-4 py-3">
                <h2 className="text-[15px] font-semibold">Опережение по моделям</h2>
                <p className="mt-1 text-[12px] text-muted-foreground">
                  Насколько заранее модель предупреждает и какая доля тревог подтверждается ·{" "}
                  <Link href="/models" className="text-vena underline-offset-4 hover:underline">
                    карточки моделей →
                  </Link>
                </p>
              </div>
              {effect.data.leadTime.length === 0 ? (
                <p className="px-4 py-6 text-[13px] text-muted-foreground">Метрики опережения ещё не рассчитаны.</p>
              ) : (
                <div>
                  <div className="grid grid-cols-[1fr_minmax(12rem,2fr)] gap-3 border-b border-border-soft px-4 py-2 text-[12px] text-faint">
                    <span>Модель</span>
                    <span>Упреждение</span>
                  </div>
                  <ul>
                    {effect.data.leadTime.map((row) => {
                      const lead = leadHorizonPhrase(row.medianLeadTimeHours, "предупреждает за ~")
                      const precision =
                        row.alertPrecision === null ? null : Math.round(row.alertPrecision * 100)
                      const phrase =
                        lead === null && precision === null
                          ? "данных пока недостаточно"
                          : [lead, precision === null ? null : `${precision} % тревог подтверждаются`]
                              .filter(Boolean)
                              .join(", ")
                      return (
                        <li
                          key={`${row.modelId}-${row.level}`}
                          className="grid grid-cols-[1fr_minmax(12rem,2fr)] gap-3 border-b border-border-soft px-4 py-2.5 text-[13px] last:border-b-0"
                        >
                          <Link
                            href={`/models#${row.modelId}`}
                            className="truncate text-vena underline-offset-4 hover:underline"
                          >
                            {modelLabel(row.modelId)}
                          </Link>
                          <span className="text-muted-foreground">{phrase}</span>
                        </li>
                      )
                    })}
                  </ul>
                </div>
              )}
            </section>
          </>
        ) : null}

        <ForecastVsFactPanel />
        <AlarmLoadBlock />

        <section className="border border-border bg-elevated">
          <div className="border-b border-border-soft px-4 py-3">
            <h2 className="text-[15px] font-semibold">Топ локаций → действие</h2>
            <p className="mt-1 text-[12px] text-muted-foreground">
              Сортировка по индексу здоровья (хуже выше). Открытых работ: {openActions.length}.
            </p>
          </div>
          {situations.isPending ? (
            <LoadingBar className="min-h-24" />
          ) : topLocations.length === 0 ? (
            <p className="px-4 py-6 text-[13px] text-muted-foreground">Нет локаций с повышенным риском.</p>
          ) : (
            <ul>
              {topLocations.map((item) => {
                const hasAction = openActions.some((action) => item.assetIds.includes(action.assetId))
                const scenario =
                  item.scenario && SCENARIO_LABEL[item.scenario as PredictionScenario]
                    ? SCENARIO_LABEL[item.scenario as PredictionScenario]
                    : null
                return (
                  <li
                    key={item.id}
                    className="grid grid-cols-[1fr_7rem_1fr_6rem] items-baseline gap-3 border-b border-border-soft px-4 py-2.5 text-[13px] last:border-b-0"
                  >
                    <span className="truncate font-medium">
                      {item.title}
                      {scenario ? <span className="ml-2 text-[12px] font-normal text-muted-foreground">{scenario}</span> : null}
                    </span>
                    <span className="font-mono tabular-nums text-muted-foreground">
                      {item.healthIndex === null ? "—" : `Здоровье ${item.healthIndex}`}
                    </span>
                    <span className="truncate text-muted-foreground">
                      {item.recommendation?.consequence ?? item.recommendation?.title ?? item.primaryReason}
                    </span>
                    <span className={cn("text-[12px]", hasAction ? "text-vena" : "text-faint")}>
                      {hasAction ? "работа есть" : (STATUS_RU[item.status] ?? "нужна работа")}
                    </span>
                  </li>
                )
              })}
            </ul>
          )}
        </section>
      </div>
    </div>
  )
}
