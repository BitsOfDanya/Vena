"use client"

import Link from "next/link"
import * as React from "react"

import { useEffectReport } from "@/entities/analytics"
import { OPEN_STATUSES, useActions } from "@/entities/maintenance"
import { SCENARIO_LABEL, useBackendSituations, type PredictionScenario } from "@/entities/prediction"
import { ApiError } from "@/shared/api/http"
import { workflowMode } from "@/shared/config/env"
import { cn } from "@/shared/lib/utils"
import { Button } from "@/shared/ui/button"
import { LoadingBar, StateMessage } from "@/shared/ui/state-message"

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
    <section className="border border-border bg-elevated px-4 py-3">
      <h3 className="text-[11px] font-medium tracking-[0.12em] text-muted-foreground uppercase">{title}</h3>
      <p className="mt-2 flex items-baseline gap-2">
        <span className="font-mono text-[28px] leading-none tabular-nums">{value}</span>
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

function modelLabel(modelId: string) {
  const prefix = modelId.split("_")[0]
  const map: Record<string, string> = {
    phase: "Питание",
    power: "Питание",
    pump: "Подтопление",
    flood: "Подтопление",
    smoke: "Пожар",
    fan: "Вентиляция",
    alarm: "Тревоги",
  }
  return map[prefix] ? `${map[prefix]} · ${modelId}` : modelId
}

async function downloadManagementReport() {
  const response = await fetch(`${API_URL}/api/v1/reports/management.xlsx`, {
    credentials: "include",
    headers: { Accept: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" },
  })
  if (!response.ok) throw new ApiError(response.status, response.statusText)
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = url
  link.download = "vena-management-report.xlsx"
  link.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function EffectPage() {
  const effect = useEffectReport()
  const situations = useBackendSituations()
  const actions = useActions()
  const apiMode = workflowMode === "api"
  const [downloading, setDownloading] = React.useState(false)
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
      <div className="flex shrink-0 flex-wrap items-center gap-x-6 gap-y-3 px-6 pt-4 pb-3 print:border-b print:pb-4">
        <h1 className="text-[26px] font-semibold tracking-[-0.01em]">Эффект</h1>
        <p className="text-[13px] text-muted-foreground">Предсказано · опережение · решения · избежанные выезды</p>
        <div className="ml-auto flex items-center gap-3 print:hidden">
          <Button
            variant="outline"
            size="sm"
            disabled={downloading}
            onClick={() => {
              setDownloading(true)
              setDownloadError(null)
              void downloadManagementReport()
                .catch(() => setDownloadError("Не удалось скачать отчёт."))
                .finally(() => setDownloading(false))
            }}
          >
            {downloading ? "Скачивание…" : "Скачать XLSX"}
          </Button>
          <Button variant="outline" size="sm" onClick={() => window.print()}>
            Печать / PDF
          </Button>
          <Button asChild variant="outline" size="sm">
            <Link href="/dashboard">К дашборду</Link>
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
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
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

            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <Metric title="Алармы 30д" value={String(effect.data.alarms30d)} />
              <Metric
                title="К проверке"
                value={String(effect.data.alarmsToVerify)}
                detail={
                  effect.data.alarmFilterShare === null
                    ? undefined
                    : `Фильтр срезает ${pct(effect.data.alarmFilterShare)} неподтверждённых`
                }
              />
              <Metric title="Доступ 30д" value={String(effect.data.accessEvents30d)} unit="событий" />
              <Metric title="Прогнозов в журнале" value={String(effect.data.forecastsInJournal)} />
            </div>

            <section className="border border-border bg-elevated">
              <div className="border-b border-border-soft px-4 py-3">
                <h2 className="text-[12px] font-medium tracking-[0.12em] uppercase">Опережение по моделям</h2>
                <p className="mt-1 text-[12px] text-muted-foreground">Медианный lead time, полнота эпизодов и точность алертов</p>
              </div>
              {effect.data.leadTime.length === 0 ? (
                <p className="px-4 py-6 text-[13px] text-muted-foreground">Метрики lead time ещё не рассчитаны.</p>
              ) : (
                <ul>
                  {effect.data.leadTime.map((row) => (
                    <li
                      key={`${row.modelId}-${row.level}`}
                      className="grid grid-cols-[1fr_5rem_5rem_5rem_5rem] gap-3 border-b border-border-soft px-4 py-2.5 text-[13px] last:border-b-0"
                    >
                      <span className="truncate">{modelLabel(row.modelId)}</span>
                      <span className="font-mono text-muted-foreground tabular-nums">
                        {row.level === "high" ? "высокий" : row.level === "critical" ? "критич." : row.level}
                      </span>
                      <span className="font-mono tabular-nums" title="Медианный lead time, ч">
                        {row.medianLeadTimeHours === null ? "—" : `${row.medianLeadTimeHours.toFixed(1)}ч`}
                      </span>
                      <span className="font-mono tabular-nums" title="Полнота эпизодов">
                        {pct(row.episodeRecall)}
                      </span>
                      <span className="font-mono tabular-nums" title="Точность алертов">
                        {pct(row.alertPrecision)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </>
        ) : null}

        <section className="border border-border bg-elevated">
          <div className="border-b border-border-soft px-4 py-3">
            <h2 className="text-[12px] font-medium tracking-[0.12em] uppercase">Топ локаций → действие</h2>
            <p className="mt-1 text-[12px] text-muted-foreground">
              Сортировка по HI (хуже выше). Открытых работ: {openActions.length}.
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
                      {item.healthIndex === null ? "—" : `HI ${item.healthIndex}`}
                    </span>
                    <span className="truncate text-muted-foreground">
                      {item.recommendation?.title ?? item.primaryReason}
                    </span>
                    <span className={cn("text-[12px] tracking-[0.04em] uppercase", hasAction ? "text-vena" : "text-faint")}>
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
