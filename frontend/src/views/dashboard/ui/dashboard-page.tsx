"use client"

import { ArrowDown, ArrowDownToLine, ArrowUp, ArrowUpDown, ArrowUpRight, RefreshCw, Search } from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import * as React from "react"

import { TYPE_LABEL, TYPE_ORDER, formatScore, useAssets, type ForecastHorizon } from "@/entities/infrastructure"
import { OUTCOME_LABEL, useActions } from "@/entities/maintenance"
import { useAssetTree, useEventTypes, useObjectHealthHistory } from "@/entities/analytics"
import { useDashboardPredictions, useSnapshotStatus, modelLabel } from "@/entities/prediction"
import { CreateActionSheet, type ActionDraft } from "@/features/create-action"
import { useWorkspace } from "@/features/workspace"
import { workflowMode } from "@/shared/config/env"
import { formatDateTime } from "@/shared/lib/time"
import { cn } from "@/shared/lib/utils"
import { Button } from "@/shared/ui/button"
import { Input } from "@/shared/ui/input"
import { Inspector, InspectorBody, InspectorFooter, InspectorHeader, InspectorSection } from "@/shared/ui/inspector"
import { NativeSelect, NativeSelectOption } from "@/shared/ui/native-select"
import { Segmented } from "@/shared/ui/segmented"
import { LoadingBar, StateMessage } from "@/shared/ui/state-message"

import {
  dashboardRows,
  exportDashboardCsv,
  filterRows,
  responseLabels,
  sortDashboardRows,
  summarizeDashboard,
  type DashboardLevel,
  type DashboardRow,
  type DashboardSort,
  type DashboardSortKey,
} from "../model/analytics"
import { ProspectivePanel } from "./prospective-panel"
import { SeasonalityPanel } from "./seasonality-panel"

const HORIZONS: { value: ForecastHorizon; label: string }[] = [
  { value: 24, label: "24ч" },
  { value: 72, label: "72ч" },
]
const LEVELS: DashboardLevel[] = ["critical", "attention", "observe", "normal", "offline"]
const FOCUS_LEVELS: DashboardLevel[] = ["critical", "attention", "observe", "offline"]
const LABEL: Record<DashboardLevel, string> = {
  critical: "Критично",
  attention: "Внимание",
  observe: "Наблюдение",
  normal: "Норма",
  offline: "Офлайн",
}
const COLOR: Record<DashboardLevel, string> = {
  critical: "bg-status-critical",
  attention: "bg-status-attention",
  observe: "bg-vena-soft",
  normal: "bg-status-normal",
  offline: "bg-status-offline",
}
const TONE: Record<DashboardLevel, string> = {
  critical: "text-status-critical",
  attention: "text-status-attention",
  observe: "text-vena",
  normal: "text-status-normal",
  offline: "text-faint",
}
const EMPTY_ROWS: DashboardRow[] = []
const PAGE_SIZE = 20
const COLUMNS: { key: DashboardSortKey; label: string }[] = [
  { key: "asset", label: "Объект / группа" },
  { key: "system", label: "Система" },
  { key: "risk", label: "Риск" },
  { key: "score", label: "Скор" },
  { key: "horizon", label: "Горизонт" },
  { key: "response", label: "Ответ" },
]

function SectionTitle({ children, description, action }: { children: React.ReactNode; description?: string; action?: React.ReactNode }) {
  return (
    <div className="mb-5 flex items-start justify-between gap-4">
      <div>
        <h2 className="text-[12px] font-medium tracking-[0.12em] uppercase">{children}</h2>
        {description ? <p className="mt-1.5 text-[12px] text-muted-foreground">{description}</p> : null}
      </div>
      {action}
    </div>
  )
}

function Level({ level }: { level: DashboardLevel }) {
  return (
    <span className={cn("inline-flex items-center gap-2 text-[12px]", TONE[level])}>
      <span aria-hidden className={cn("size-1.5", COLOR[level])} />
      {LABEL[level]}
    </span>
  )
}

function RiskDistribution({ rows, onLevel }: { rows: DashboardRow[]; onLevel: (level: DashboardLevel) => void }) {
  const counts = Object.fromEntries(LEVELS.map((level) => [level, rows.filter((row) => row.level === level).length]))
  const focusTotal = FOCUS_LEVELS.reduce((sum, level) => sum + counts[level], 0) || 1
  return (
    <section className="border-b border-border p-5 lg:border-r lg:border-b-0">
      <SectionTitle description="Фокус на отклонениях; норма не доминирует на шкале">Распределение риска</SectionTitle>
      <div
        className="my-7 flex h-7 w-full overflow-hidden bg-surface"
        role="img"
        aria-label={FOCUS_LEVELS.map((level) => `${LABEL[level]}: ${counts[level]}`).join(", ")}
      >
        {FOCUS_LEVELS.map((level) =>
          counts[level] ? (
            <div
              key={level}
              className={cn("border-r border-background/50 last:border-0", COLOR[level])}
              style={{ width: `${(counts[level] / focusTotal) * 100}%` }}
            />
          ) : null
        )}
      </div>
      <div className="space-y-1">
        {FOCUS_LEVELS.map((level) => (
          <button
            key={level}
            type="button"
            onClick={() => onLevel(level)}
            className="flex w-full items-center justify-between gap-4 px-1 py-2 text-left outline-none hover:bg-surface/40 focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Level level={level} />
            <span className="flex gap-5 font-mono text-[12px] tabular-nums">
              <span className="w-9 text-right text-faint">{focusTotal ? Math.round((counts[level] / focusTotal) * 100) : 0}%</span>
              <span className="w-8 text-right">{counts[level]}</span>
            </span>
          </button>
        ))}
        <button
          type="button"
          onClick={() => onLevel("normal")}
          className="flex w-full items-center justify-between gap-4 px-1 py-2 text-left text-faint outline-none hover:bg-surface/40 focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Level level="normal" />
          <span className="font-mono text-[12px] tabular-nums">{counts.normal}</span>
        </button>
      </div>
    </section>
  )
}

function SystemDistribution({ rows, onSystem }: { rows: DashboardRow[]; onSystem: (system: string) => void }) {
  const max = Math.max(1, ...TYPE_ORDER.map((type) => rows.filter((row) => row.type === type).length))
  return (
    <section className="border-b border-border p-5 lg:border-r lg:border-b-0">
      <SectionTitle description="Распределение прогнозов по системам">Нагрузка по системам</SectionTitle>
      <div className="space-y-5 pt-2">
        {TYPE_ORDER.map((type) => {
          const systemRows = rows.filter((row) => row.type === type)
          return (
            <button
              type="button"
              key={type}
              onClick={() => onSystem(type)}
              aria-label={`Фильтр ${TYPE_LABEL[type]}: ${systemRows.length} прогнозов`}
              className="block w-full text-left outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <span className="mb-2 flex justify-between text-[12px]">
                <span>{TYPE_LABEL[type]}</span>
                <span className="font-mono text-faint">{systemRows.length}</span>
              </span>
              <span className="flex h-2 bg-surface/60">
                {LEVELS.map((level) => (
                  <span
                    key={level}
                    className={COLOR[level]}
                    style={{ width: `${(systemRows.filter((row) => row.level === level).length / max) * 100}%` }}
                  />
                ))}
              </span>
            </button>
          )
        })}
      </div>
      <p className="mt-5 text-[11px] text-faint">Шкала — число прогнозов. Цвета соответствуют уровню риска.</p>
    </section>
  )
}

function ScenarioExposure() {
  const eventTypes = useEventTypes()
  if (workflowMode !== "api") return null
  if (eventTypes.isPending) return <LoadingBar className="mx-6 mt-4 min-h-24" />
  if (eventTypes.isError || !eventTypes.data?.length) return null
  return (
    <section className="mx-6 mt-4 border border-border bg-elevated p-5">
      <SectionTitle description="Сценарии ТЗ: риск сейчас и объём за 30 дней">Сценарии инцидентов</SectionTitle>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {eventTypes.data.map((item) => {
          const critical = item.channelsAtRisk.critical ?? 0
          const attention = item.channelsAtRisk.attention ?? 0
          return (
            <div key={item.eventType} className="border border-border-soft px-3 py-2.5">
              <p className="text-[13px] font-medium">{item.title}</p>
              <p className="mt-2 flex flex-wrap gap-x-4 font-mono text-[12px] tabular-nums">
                <span className="text-status-critical">{critical} крит.</span>
                <span className="text-status-attention">{attention} вним.</span>
                <span className="text-faint">{item.episodes30d ?? "—"} / 30д</span>
                {item.next7Days !== null ? (
                  <span className="text-muted-foreground">~{item.next7Days.expected.toFixed(1)} / 7д</span>
                ) : null}
                {item.weekError !== null ? (
                  <span className="text-faint" title="Ошибка недельного прогноза vs факт">
                    ош. нед. {item.weekError.toFixed(2)}
                  </span>
                ) : null}
                {item.episodes365d !== null ? (
                  <span className="text-faint">{item.episodes365d} / год</span>
                ) : null}
              </p>
            </div>
          )
        })}
      </div>
    </section>
  )
}

function healthDelta(series: { day: string; value: number }[] | undefined) {
  if (!series || series.length < 8) return null
  const latest = series[series.length - 1]?.value
  const weekAgo = series[series.length - 8]?.value
  if (latest === undefined || weekAgo === undefined) return null
  return latest - weekAgo
}

function HealthStrip() {
  const tree = useAssetTree()
  const history = useObjectHealthHistory()
  if (workflowMode !== "api") return null
  if (tree.isPending || tree.isError || !tree.data?.length) return null
  const ranked = [...tree.data]
    .filter((item) => item.healthIndex !== null)
    .sort((a, b) => (a.healthIndex ?? 101) - (b.healthIndex ?? 101))
  const worst = ranked.slice(0, 6)
  if (worst.length === 0) return null
  const minHi = worst[0]?.healthIndex ?? null
  const criticalCount = ranked.filter((item) => (item.healthIndex ?? 100) < 40).length
  const objects = history.data?.objects ?? {}
  return (
    <section className="mx-6 mt-4 border border-border bg-elevated p-5">
      <SectionTitle
        description={
          history.data?.period
            ? `Индекс 0–100 по объектам СМВУ · тренд за неделю · период ${history.data.period}`
            : "Индекс 0–100 по объектам СМВУ (хуже — ниже). HI &lt;40 критично · &lt;70 внимание"
        }
        action={
          <Link className="text-[13px] text-vena" href="/effect">
            Эффект →
          </Link>
        }
      >
        Индекс здоровья
      </SectionTitle>
      <p className="mb-3 font-mono text-[22px] tabular-nums">
        {minHi}
        <span className="ml-2 text-[13px] text-muted-foreground">
          минимум · {criticalCount} объект{criticalCount === 1 ? "" : criticalCount < 5 ? "а" : "ов"} &lt;40
        </span>
      </p>
      <ul className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {worst.map((item) => {
          const delta = healthDelta(objects[item.objectId])
          return (
            <li key={item.objectId} className="flex items-baseline justify-between gap-3 text-[13px]">
              <span className="truncate">{item.label}</span>
              <span className="flex shrink-0 items-baseline gap-2 font-mono tabular-nums">
                {delta !== null ? (
                  <span
                    className={cn(
                      "text-[11px]",
                      delta < 0 ? "text-status-critical" : delta > 0 ? "text-status-normal" : "text-faint"
                    )}
                    title="Изменение HI за 7 дней"
                  >
                    {delta > 0 ? `+${delta}` : delta}
                  </span>
                ) : null}
                <span
                  className={cn(
                    (item.healthIndex ?? 100) < 40
                      ? "text-status-critical"
                      : (item.healthIndex ?? 100) < 70
                        ? "text-status-attention"
                        : "text-status-normal"
                  )}
                >
                  {item.healthIndex}
                </span>
              </span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

function PredictionInspector({
  row,
  onClose,
  onCreate,
}: {
  row: DashboardRow
  onClose: () => void
  onCreate: (row: DashboardRow) => void
}) {
  const { selectAsset, setCompare } = useWorkspace()
  const router = useRouter()
  return (
    <Inspector label="Инспектор прогноза на сводке">
      <InspectorHeader title={row.assetId} eyebrow={`${TYPE_LABEL[row.type]} · ${row.group}`} onClose={onClose}>
        <div className="mt-2">
          <Level level={row.level} />
        </div>
      </InspectorHeader>
      <InspectorBody>
        <InspectorSection title={row.scoreType === "calibrated_probability" ? "Оценка вероятности" : "Оценка риска"}>
          <p className="font-mono text-4xl tabular-nums">{row.level === "offline" ? "—" : formatScore(row.score, row.scoreType)}</p>
          <p className="mt-2 text-[12px] text-muted-foreground">
            {row.scoreType === "risk_score"
              ? "Шкала приоритета. Это не вероятность отказа."
              : "Калиброванная вероятность из снимка модели."}
          </p>
          <dl className="mt-5 space-y-2 text-[12px]">
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Окно прогноза</dt>
              <dd className="font-mono">{row.horizon}h</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Время прогноза</dt>
              <dd className="font-mono">{formatDateTime(row.time)} MSK</dd>
            </div>
          </dl>
        </InspectorSection>
        <InspectorSection title="Контекст прогноза">
          <p className="text-[13px]">{row.name}</p>
          <p className="mt-2 text-[12px] text-muted-foreground">{row.modelId ? modelLabel(row.modelId) : "Демо-телеметрия"}</p>
          <p className="mt-3 text-[11px] text-faint">Точное время до отказа в источнике не указано. Горизонт — окно прогноза.</p>
        </InspectorSection>
        <InspectorSection title="Почему этот риск">
          {row.factors.length ? (
            <ul className="space-y-3">
              {row.factors.map((factor, index) => (
                <li key={`${index}:${factor}`} className="break-words text-[12px] text-muted-foreground">
                  {factor}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[12px] text-muted-foreground">Источник не передал факторы. Диагностика доступна на экране сети.</p>
          )}
        </InspectorSection>
        {!row.registered ? (
          <InspectorSection>
            <p className="text-[12px] text-muted-foreground">
              Объект отсутствует в текущем реестре интерфейса. Прогноз учтён в аналитике; создание работ доступно после сопоставления
              реестра.
            </p>
          </InspectorSection>
        ) : null}
      </InspectorBody>
      <InspectorFooter>
        <Button
          variant="outline"
          disabled={!row.registered}
          onClick={() => {
            selectAsset(row.assetId)
            setCompare([row.assetId])
            router.push("/timeline")
          }}
        >
          Хронология
        </Button>
        <Button className="flex-1" disabled={!row.registered || row.level === "offline"} onClick={() => onCreate(row)}>
          Создать работу
        </Button>
      </InspectorFooter>
    </Inspector>
  )
}

export function DashboardPage() {
  const { now, horizon, setHorizon } = useWorkspace()
  const assets = useAssets(now, horizon)
  const predictions = useDashboardPredictions(horizon)
  const snapshot = useSnapshotStatus()
  const actions = useActions()
  const [query, setQuery] = React.useState("")
  const [system, setSystem] = React.useState("all")
  const [level, setLevel] = React.useState("all")
  const [page, setPage] = React.useState(0)
  const [sort, setSort] = React.useState<DashboardSort>({ key: "risk", direction: "desc" })
  const [selectedId, setSelectedId] = React.useState<string | null>(null)
  const [sheetOpen, setSheetOpen] = React.useState(false)
  const [draft, setDraft] = React.useState<ActionDraft>({})
  const source = workflowMode === "api" ? predictions : assets
  const rows = React.useMemo(
    () => dashboardRows(assets.data ?? [], predictions.data ?? [], workflowMode, horizon, now),
    [assets.data, predictions.data, horizon, now]
  )
  const loading = source.isPending || source.isPlaceholderData
  const availableRows = source.isError || loading ? EMPTY_ROWS : rows
  const filtered = React.useMemo(() => filterRows(availableRows, query, system, level), [availableRows, query, system, level])
  const summary = React.useMemo(
    () => summarizeDashboard(availableRows, actions.isError ? [] : (actions.data ?? [])),
    [availableRows, actions.data, actions.isError]
  )
  const selected = filtered.find((row) => row.id === selectedId) ?? null
  const responses = React.useMemo(() => responseLabels(summary.open), [summary.open])
  const sorted = React.useMemo(() => sortDashboardRows(filtered, sort, responses), [filtered, sort, responses])
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const currentPage = Math.min(page, totalPages - 1)
  const currentRows = sorted.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE)
  const actionUnavailable = actions.isPending || actions.isError
  const sourceUnavailable = loading || source.isError
  const sampleTime = availableRows.length ? availableRows.reduce((latest, row) => Math.max(latest, row.time), 0) : null
  const changeSystem = (value: string) => {
    setSystem(value)
    setPage(0)
  }
  const changeLevel = (value: string) => {
    setLevel(value)
    setPage(0)
  }
  const changeSort = (key: DashboardSortKey) => {
    setSort((current) => ({
      key,
      direction: current.key === key ? (current.direction === "asc" ? "desc" : "asc") : key === "risk" || key === "score" ? "desc" : "asc",
    }))
    setPage(0)
  }
  const reset = () => {
    setQuery("")
    setSystem("all")
    setLevel("all")
    setPage(0)
  }
  const refresh = () => {
    void source.refetch()
    void actions.refetch()
    if (workflowMode === "api") void snapshot.refetch()
  }
  const createAction = (row: DashboardRow) => {
    setDraft({
      assetId: row.assetId,
      reason: `${TYPE_LABEL[row.type]} · ${LABEL[row.level]} · ${formatScore(row.score, row.scoreType)} на ${row.horizon}h`,
      priority: row.level === "critical" || row.level === "attention" ? "high" : "medium",
      sourcePredictionId: row.predictionId ?? undefined,
      sourceModelId: row.modelId ?? undefined,
      sourceScore: row.score / 100,
      sourceHorizonHours: row.horizon,
    })
    setSheetOpen(true)
  }
  const exportCsv = () => {
    const url = URL.createObjectURL(new Blob([exportDashboardCsv(sorted, workflowMode)], { type: "text/csv;charset=utf-8" }))
    const link = document.createElement("a")
    link.href = url
    link.download = `vena-dashboard-${workflowMode}-${horizon}h.csv`
    link.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  return (
    <div className="flex size-full min-h-0 flex-col">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-4 border-b border-border px-6 py-4">
        <div className="flex items-baseline gap-4">
          <h1 className="text-[26px] font-semibold tracking-[-0.01em]">Дашборд</h1>
          <span className="font-mono text-[12px] text-faint">горизонт {horizon}ч</span>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Segmented
            label="Горизонт прогноза"
            options={HORIZONS}
            value={horizon}
            onChange={(value) => {
              setHorizon(value)
              setPage(0)
              setSelectedId(null)
            }}
          />
          <Button variant="outline" size="sm" onClick={refresh} disabled={source.isFetching} aria-label="Обновить сводку">
            <RefreshCw className={cn("size-3.5", source.isFetching && "animate-spin")} />
          </Button>
          <Button variant="outline" size="sm" onClick={exportCsv} disabled={sourceUnavailable || !filtered.length}>
            <ArrowDownToLine className="size-3.5" /> CSV
          </Button>
          {workflowMode === "api" ? (
            <Button asChild variant="outline" size="sm">
              <Link href="/effect">Эффект</Link>
            </Button>
          ) : null}
        </div>
      </div>
      <div className="relative flex min-h-0 flex-1">
        <div className="min-w-0 flex-1 overflow-y-auto">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border-soft px-6 py-2.5 text-[11px] text-muted-foreground">
            <span className="flex items-center gap-2">
              <span aria-hidden className={cn("size-1.5", workflowMode === "demo" ? "bg-brass" : "bg-vena")} />
              {workflowMode === "demo"
                ? "DEMO · Детерминированные данные стенда, не результаты модели"
                : "API · Все прогнозы выбранного горизонта, без демо-подстановки"}
            </span>
            <span className="font-mono">{sampleTime ? `${formatDateTime(sampleTime)} MSK` : "Нет снимка"}</span>
          </div>
          {workflowMode === "api" && snapshot.data?.stale ? (
            <p role="status" className="border-b border-vena/40 bg-vena/10 px-6 py-3 text-[12px] text-vena">
              Демонстрационный снимок: аналитика показывает зафиксированный срез стенда, а не сбой сервиса.
            </p>
          ) : workflowMode === "api" && (snapshot.isError || snapshot.data?.available === false) ? (
            <p
              role="status"
              className="border-b border-status-attention/40 bg-status-attention/10 px-6 py-3 text-[12px] text-status-attention"
            >
              Свежесть снимка не подтверждена. Проверьте источник прогнозов.
            </p>
          ) : null}
          <section aria-label="Фильтры сводки" className="flex flex-wrap items-center gap-3 px-6 py-4">
            <div className="relative min-w-48 flex-1">
              <Search className="pointer-events-none absolute top-2.5 left-2.5 size-3.5 text-faint" />
              <Input
                aria-label="Поиск прогнозов"
                className="h-9 pl-8 text-[12px]"
                placeholder="Объект, группа или модель…"
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value)
                  setPage(0)
                }}
              />
            </div>
            <NativeSelect aria-label="Фильтр по системе" value={system} onChange={(event) => changeSystem(event.target.value)}>
              <NativeSelectOption value="all">Все системы</NativeSelectOption>
              {TYPE_ORDER.map((type) => (
                <NativeSelectOption key={type} value={type}>
                  {TYPE_LABEL[type]}
                </NativeSelectOption>
              ))}
            </NativeSelect>
            <NativeSelect aria-label="Фильтр по риску" value={level} onChange={(event) => changeLevel(event.target.value)}>
              <NativeSelectOption value="focus">Требуют внимания</NativeSelectOption>
              <NativeSelectOption value="all">Все уровни риска</NativeSelectOption>
              {LEVELS.map((value) => (
                <NativeSelectOption key={value} value={value}>
                  {LABEL[value]}
                </NativeSelectOption>
              ))}
            </NativeSelect>
            {query || system !== "all" || level !== "all" ? (
              <Button variant="ghost" size="sm" onClick={reset}>
                Сбросить
              </Button>
            ) : null}
          </section>
          <section aria-label="Оперативная сводка" className="mx-6 grid grid-cols-2 border-y border-border lg:grid-cols-4">
            {[
              { label: "Объектов в выборке", value: summary.assets, hint: `${summary.forecasts} прогнозов`, tone: "text-foreground" },
              {
                label: "Критичных прогнозов",
                value: summary.counts.critical,
                hint: `${summary.counts.attention} внимание · по всему снимку ${horizon}ч`,
                tone: "text-status-critical",
              },
              {
                label: "Без работы",
                value: actionUnavailable ? null : summary.unassigned,
                hint: "Объекты высокого риска без открытых работ",
                tone: "text-status-attention",
              },
              {
                label: "Открытых работ",
                value: actionUnavailable ? null : summary.open.length,
                hint: "По объектам текущей выборки",
                tone: "text-vena",
              },
            ].map((item) => (
              <div key={item.label} className="border-r border-border-soft px-5 py-5 last:border-0">
                <p className="text-[11px] font-medium tracking-[0.1em] text-muted-foreground uppercase">{item.label}</p>
                <p className={cn("mt-3 font-mono text-[38px] leading-none tabular-nums", item.tone)}>
                  {sourceUnavailable || item.value === null ? "—" : String(item.value).padStart(2, "0")}
                </p>
                <p className="mt-3 text-[11px] text-faint">{item.value === null ? "Данные работ недоступны" : item.hint}</p>
              </div>
            ))}
          </section>
          {loading ? (
            <div className="m-6">
              <LoadingBar />
            </div>
          ) : source.isError ? (
            <StateMessage
              title="Прогнозы недоступны"
              description="Не удалось получить полный набор прогнозов. Частичные данные не используются для сводки."
              action={
                <Button size="sm" variant="outline" onClick={refresh}>
                  Повторить
                </Button>
              }
            />
          ) : (
            <>
              <ScenarioExposure />
              <HealthStrip />
              <div className="mx-6 mt-6 grid border border-border bg-elevated lg:grid-cols-3">
                <RiskDistribution rows={filtered} onLevel={changeLevel} />
                <SystemDistribution rows={filtered} onSystem={changeSystem} />
                <section className="p-5">
                  <SectionTitle
                    description="Статусы работ по выбранным объектам"
                    action={
                      <Link className="text-vena" href="/actions" aria-label="Открыть план работ">
                        <ArrowUpRight className="size-4" />
                      </Link>
                    }
                  >
                    Работы и исходы
                  </SectionTitle>
                  {actionUnavailable ? (
                    <StateMessage
                      title="Работы недоступны"
                      description="Сводка работ недоступна."
                      action={
                        <Button size="sm" variant="outline" onClick={() => actions.refetch()}>
                          Повторить
                        </Button>
                      }
                    />
                  ) : (
                    <>
                      <div className="grid grid-cols-2 gap-4 border-b border-border-soft pb-4">
                        <div>
                          <p className="font-mono text-3xl">{summary.open.length}</p>
                          <p className="mt-2 text-[11px] text-faint">ОТКРЫТЫ</p>
                        </div>
                        <div>
                          <p className="font-mono text-3xl">{summary.closed.length}</p>
                          <p className="mt-2 text-[11px] text-faint">ЗАКРЫТЫ</p>
                        </div>
                      </div>
                      <div className="mt-4 space-y-3">
                        {(["confirmed_issue", "maintenance_performed", "false_signal", "monitoring_required"] as const).map((outcome) => (
                          <div key={outcome} className="flex items-center justify-between gap-2 text-[12px]">
                            <span className="text-muted-foreground">{OUTCOME_LABEL[outcome]}</span>
                            <span className="font-mono">
                              {summary.closed.filter((action) => action.result?.outcome === outcome).length}
                            </span>
                          </div>
                        ))}
                      </div>
                      <p className="mt-5 text-[11px] leading-relaxed text-faint">
                        Результаты работ — обратная связь диспетчера. Эти числа не являются Precision или Recall модели.
                      </p>
                    </>
                  )}
                </section>
              </div>
              <div className="pt-7">
                <ProspectivePanel />
                <SeasonalityPanel />
              </div>
              <section className="px-6 pt-1 pb-6">
                <SectionTitle
                  description="Нажмите на заголовок столбца, чтобы изменить порядок. Повторное нажатие меняет направление."
                  action={
                    <Link href="/network" className="flex items-center gap-1 text-[12px] whitespace-nowrap text-vena">
                      Сеть и карта <ArrowUpRight className="size-3.5" />
                    </Link>
                  }
                >
                  Реестр прогнозов <span className="ml-2 font-mono text-faint">{filtered.length}</span>
                </SectionTitle>
                {!filtered.length ? (
                  <StateMessage
                    title="Нет подходящих прогнозов"
                    description={
                      rows.length ? "Измените поиск, систему или уровень риска." : `В источнике нет прогнозов для горизонта ${horizon}h.`
                    }
                    action={
                      rows.length ? (
                        <Button variant="outline" size="sm" onClick={reset}>
                          Сбросить фильтры
                        </Button>
                      ) : undefined
                    }
                  />
                ) : (
                  <>
                    <div className="overflow-x-auto border-y border-border">
                      <table className="w-full min-w-[760px] text-left text-[12px]">
                        <thead className="bg-surface/40 text-[10px] tracking-[0.08em] text-muted-foreground uppercase">
                          <tr>
                            {COLUMNS.map((column) => {
                              const active = sort.key === column.key
                              const SortIcon = active ? (sort.direction === "asc" ? ArrowUp : ArrowDown) : ArrowUpDown
                              return (
                                <th
                                  key={column.key}
                                  scope="col"
                                  aria-sort={active ? (sort.direction === "asc" ? "ascending" : "descending") : undefined}
                                  className="font-medium"
                                >
                                  <button
                                    type="button"
                                    onClick={() => changeSort(column.key)}
                                    disabled={column.key === "response" && actionUnavailable}
                                    aria-label={`Сортировать по ${column.label}`}
                                    className={cn(
                                      "flex w-full items-center gap-2 px-3 py-3 text-left tracking-[0.08em] uppercase outline-none hover:bg-surface/60 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
                                      active && "text-vena"
                                    )}
                                  >
                                    {column.label}
                                    <SortIcon aria-hidden className="size-3 shrink-0" />
                                  </button>
                                </th>
                              )
                            })}
                            <th scope="col" className="px-3 py-3">
                              <span className="sr-only">Подробнее</span>
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {currentRows.map((row) => {
                            return (
                              <tr
                                key={row.id}
                                className={cn("border-t border-border-soft hover:bg-elevated", selectedId === row.id && "bg-elevated")}
                              >
                                <td className="px-3 py-3">
                                  <button
                                    onClick={() => setSelectedId(row.id)}
                                    className="font-mono text-[13px] text-vena outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring"
                                  >
                                    {row.assetId}
                                  </button>
                                  <p className="mt-1 text-[10px] text-faint">{row.group}</p>
                                </td>
                                <td className="px-3 py-3">{TYPE_LABEL[row.type]}</td>
                                <td className="px-3 py-3">
                                  <Level level={row.level} />
                                </td>
                                <td className="px-3 py-3">
                                  <span className="font-mono">{row.level === "offline" ? "—" : formatScore(row.score, row.scoreType)}</span>
                                  <p className="mt-1 text-[10px] text-faint">
                                    {row.scoreType === "calibrated_probability" ? "Вероятность" : "Скор риска"}
                                  </p>
                                </td>
                                <td className="px-3 py-3 font-mono">{row.horizon}h</td>
                                <td className="px-3 py-3 text-muted-foreground">
                                  {actionUnavailable ? "Недоступно" : (responses.get(row.assetId) ?? "Нет открытой работы")}
                                </td>
                                <td className="px-3 py-3">
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    aria-label={`Открыть прогноз ${row.assetId}`}
                                    onClick={() => setSelectedId(row.id)}
                                  >
                                    <ArrowUpRight className="size-4" />
                                  </Button>
                                </td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>
                    <div className="mt-3 flex items-center justify-between gap-3">
                      <span className="font-mono text-[11px] text-faint">
                        {currentPage * PAGE_SIZE + 1}–{Math.min((currentPage + 1) * PAGE_SIZE, filtered.length)} / {filtered.length}
                      </span>
                      <div className="flex items-center gap-3">
                        <Button variant="ghost" size="sm" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>
                          Назад
                        </Button>
                        <span className="font-mono text-[11px] text-faint">
                          {currentPage + 1} / {totalPages}
                        </span>
                        <Button variant="ghost" size="sm" disabled={currentPage + 1 >= totalPages} onClick={() => setPage(currentPage + 1)}>
                          Далее
                        </Button>
                      </div>
                    </div>
                  </>
                )}
              </section>
              <div className="mx-6 mb-6 flex flex-wrap items-center justify-between gap-3 border-t border-border-soft pt-3 text-[11px] text-faint">
                <span>VENA · Аналитика снимка · {workflowMode === "demo" ? "Демо-срез" : "Результаты моделей"}</span>
                <span className="flex gap-4">
                  <Link href="/effect" className="text-vena">
                    Эффект и XLSX ↗
                  </Link>
                  <Link href="/network" className="text-vena">
                    Объекты и карта ↗
                  </Link>
                </span>
              </div>
            </>
          )}
        </div>
        {selected ? <PredictionInspector row={selected} onClose={() => setSelectedId(null)} onCreate={createAction} /> : null}
      </div>
      <CreateActionSheet open={sheetOpen} onOpenChange={setSheetOpen} draft={draft} />
    </div>
  )
}
