"use client"

import { ArrowDown, ArrowDownToLine, ArrowUp, ArrowUpDown, ArrowUpRight, RefreshCw, Search } from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import * as React from "react"

import { TYPE_LABEL, TYPE_ORDER, formatScore, useAssets, type ForecastHorizon } from "@/entities/infrastructure"
import { OUTCOME_LABEL, useActions } from "@/entities/maintenance"
import { useDashboardPredictions, useSnapshotStatus } from "@/entities/prediction"
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
import { SeasonalityPanel } from "./seasonality-panel"

const HORIZONS: { value: ForecastHorizon; label: string }[] = [
  { value: 24, label: "24h" },
  { value: 72, label: "72h" },
]
const LEVELS: DashboardLevel[] = ["critical", "attention", "observe", "normal", "offline"]
const LABEL: Record<DashboardLevel, string> = {
  critical: "Critical",
  attention: "Attention",
  observe: "Observe",
  normal: "Normal",
  offline: "Offline",
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
  { key: "asset", label: "Asset / group" },
  { key: "system", label: "System" },
  { key: "risk", label: "Risk" },
  { key: "score", label: "Score" },
  { key: "horizon", label: "Horizon" },
  { key: "response", label: "Response" },
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
  return (
    <section className="border-b border-border p-5 lg:border-r lg:border-b-0">
      <SectionTitle description="Число прогнозов по уровням риска">Risk distribution</SectionTitle>
      <div
        className="my-7 flex h-7 w-full overflow-hidden bg-surface"
        role="img"
        aria-label={LEVELS.map((level) => `${LABEL[level]}: ${counts[level]}`).join(", ")}
      >
        {LEVELS.map((level) =>
          counts[level] ? (
            <div
              key={level}
              className={cn("border-r border-background/50 last:border-0", COLOR[level])}
              style={{ width: `${(counts[level] / rows.length) * 100}%` }}
            />
          ) : null
        )}
      </div>
      <div className="space-y-1">
        {LEVELS.map((level) => (
          <button
            key={level}
            type="button"
            onClick={() => onLevel(level)}
            className="flex w-full items-center justify-between gap-4 px-1 py-2 text-left outline-none hover:bg-surface/40 focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Level level={level} />
            <span className="flex gap-5 font-mono text-[12px] tabular-nums">
              <span className="w-9 text-right text-faint">{rows.length ? Math.round((counts[level] / rows.length) * 100) : 0}%</span>
              <span className="w-8 text-right">{counts[level]}</span>
            </span>
          </button>
        ))}
      </div>
    </section>
  )
}

function SystemDistribution({ rows, onSystem }: { rows: DashboardRow[]; onSystem: (system: string) => void }) {
  const max = Math.max(1, ...TYPE_ORDER.map((type) => rows.filter((row) => row.type === type).length))
  return (
    <section className="border-b border-border p-5 lg:border-r lg:border-b-0">
      <SectionTitle description="Распределение прогнозов по системам">System exposure</SectionTitle>
      <div className="space-y-5 pt-2">
        {TYPE_ORDER.map((type) => {
          const systemRows = rows.filter((row) => row.type === type)
          return (
            <button
              type="button"
              key={type}
              onClick={() => onSystem(type)}
              aria-label={`Filter ${TYPE_LABEL[type]}: ${systemRows.length} predictions`}
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
    <Inspector label="Dashboard prediction inspector">
      <InspectorHeader title={row.assetId} eyebrow={`${TYPE_LABEL[row.type]} · ${row.group}`} onClose={onClose}>
        <div className="mt-2">
          <Level level={row.level} />
        </div>
      </InspectorHeader>
      <InspectorBody>
        <InspectorSection title={row.scoreType === "calibrated_probability" ? "Estimated probability" : "Risk score"}>
          <p className="font-mono text-4xl tabular-nums">{row.level === "offline" ? "—" : formatScore(row.score, row.scoreType)}</p>
          <p className="mt-2 text-[12px] text-muted-foreground">
            {row.scoreType === "risk_score"
              ? "Шкала приоритета. Это не вероятность отказа."
              : "Калиброванная вероятность из снимка модели."}
          </p>
          <dl className="mt-5 space-y-2 text-[12px]">
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Forecast window</dt>
              <dd className="font-mono">{row.horizon}h</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Prediction time</dt>
              <dd className="font-mono">{formatDateTime(row.time)} MSK</dd>
            </div>
          </dl>
        </InspectorSection>
        <InspectorSection title="Forecast context">
          <p className="text-[13px]">{row.name}</p>
          <p className="mt-2 text-[12px] text-muted-foreground">{row.modelId ?? "Demo telemetry"}</p>
          <p className="mt-3 text-[11px] text-faint">Точное время до отказа в источнике не указано. Горизонт — окно прогноза.</p>
        </InspectorSection>
        <InspectorSection title="Why this risk">
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
          Timeline
        </Button>
        <Button className="flex-1" disabled={!row.registered || row.level === "offline"} onClick={() => onCreate(row)}>
          Create action
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
    () => summarizeDashboard(filtered, actions.isError ? [] : (actions.data ?? [])),
    [filtered, actions.data, actions.isError]
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
          <h1 className="text-[26px] font-semibold tracking-[-0.01em]">Dashboard</h1>
          <span className="font-mono text-[12px] text-faint">next {horizon}h</span>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Segmented
            label="Forecast horizon"
            options={HORIZONS}
            value={horizon}
            onChange={(value) => {
              setHorizon(value)
              setPage(0)
              setSelectedId(null)
            }}
          />
          <Button variant="outline" size="sm" onClick={refresh} disabled={source.isFetching} aria-label="Refresh dashboard">
            <RefreshCw className={cn("size-3.5", source.isFetching && "animate-spin")} />
          </Button>
          <Button variant="outline" size="sm" onClick={exportCsv} disabled={sourceUnavailable || !filtered.length}>
            <ArrowDownToLine className="size-3.5" /> Export CSV
          </Button>
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
            <span className="font-mono">{sampleTime ? `${formatDateTime(sampleTime)} MSK` : "No snapshot"}</span>
          </div>
          {workflowMode === "api" && (snapshot.isError || snapshot.data?.stale || snapshot.data?.available === false) ? (
            <p
              role="status"
              className="border-b border-status-attention/40 bg-status-attention/10 px-6 py-3 text-[12px] text-status-attention"
            >
              {snapshot.data?.stale
                ? "Снимок устарел. Аналитика показывает исторический срез, не текущее состояние оборудования."
                : "Свежесть снимка не подтверждена. Проверьте источник прогнозов."}
            </p>
          ) : null}
          <section aria-label="Dashboard filters" className="flex flex-wrap items-center gap-3 px-6 py-4">
            <div className="relative min-w-48 flex-1">
              <Search className="pointer-events-none absolute top-2.5 left-2.5 size-3.5 text-faint" />
              <Input
                aria-label="Search forecasts"
                className="h-9 pl-8 text-[12px]"
                placeholder="Объект, группа или модель…"
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value)
                  setPage(0)
                }}
              />
            </div>
            <NativeSelect aria-label="System filter" value={system} onChange={(event) => changeSystem(event.target.value)}>
              <NativeSelectOption value="all">All systems</NativeSelectOption>
              {TYPE_ORDER.map((type) => (
                <NativeSelectOption key={type} value={type}>
                  {TYPE_LABEL[type]}
                </NativeSelectOption>
              ))}
            </NativeSelect>
            <NativeSelect aria-label="Risk filter" value={level} onChange={(event) => changeLevel(event.target.value)}>
              <NativeSelectOption value="all">All risk levels</NativeSelectOption>
              {LEVELS.map((value) => (
                <NativeSelectOption key={value} value={value}>
                  {LABEL[value]}
                </NativeSelectOption>
              ))}
            </NativeSelect>
            {query || system !== "all" || level !== "all" ? (
              <Button variant="ghost" size="sm" onClick={reset}>
                Reset
              </Button>
            ) : null}
          </section>
          <section aria-label="Operational summary" className="mx-6 grid grid-cols-2 border-y border-border lg:grid-cols-4">
            {[
              { label: "Assets in view", value: summary.assets, hint: `${summary.forecasts} прогнозов`, tone: "text-foreground" },
              {
                label: "Critical forecasts",
                value: summary.counts.critical,
                hint: `${summary.counts.attention} требуют внимания`,
                tone: "text-status-critical",
              },
              {
                label: "Without an action",
                value: actionUnavailable ? null : summary.unassigned,
                hint: "Объекты высокого риска без открытых работ",
                tone: "text-status-attention",
              },
              {
                label: "Open actions",
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
              title="Forecasts unavailable"
              description="Не удалось получить полный набор прогнозов. Частичные данные не используются для сводки."
              action={
                <Button size="sm" variant="outline" onClick={refresh}>
                  Retry
                </Button>
              }
            />
          ) : (
            <>
              <div className="mx-6 mt-6 grid border border-border bg-elevated lg:grid-cols-3">
                <RiskDistribution rows={filtered} onLevel={changeLevel} />
                <SystemDistribution rows={filtered} onSystem={changeSystem} />
                <section className="p-5">
                  <SectionTitle
                    description="Статусы работ по выбранным объектам"
                    action={
                      <Link className="text-vena" href="/actions" aria-label="Open action plan">
                        <ArrowUpRight className="size-4" />
                      </Link>
                    }
                  >
                    Response & outcomes
                  </SectionTitle>
                  {actionUnavailable ? (
                    <StateMessage
                      title="Actions unavailable"
                      description="Сводка работ недоступна."
                      action={
                        <Button size="sm" variant="outline" onClick={() => actions.refetch()}>
                          Retry actions
                        </Button>
                      }
                    />
                  ) : (
                    <>
                      <div className="grid grid-cols-2 gap-4 border-b border-border-soft pb-4">
                        <div>
                          <p className="font-mono text-3xl">{summary.open.length}</p>
                          <p className="mt-2 text-[11px] text-faint">OPEN</p>
                        </div>
                        <div>
                          <p className="font-mono text-3xl">{summary.closed.length}</p>
                          <p className="mt-2 text-[11px] text-faint">CLOSED</p>
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
                <SeasonalityPanel />
              </div>
              <section className="px-6 pt-1 pb-6">
                <SectionTitle
                  description="Нажмите на заголовок столбца, чтобы изменить порядок. Повторное нажатие меняет направление."
                  action={
                    <Link href="/network" className="flex items-center gap-1 text-[12px] whitespace-nowrap text-vena">
                      Network & map <ArrowUpRight className="size-3.5" />
                    </Link>
                  }
                >
                  Forecast register <span className="ml-2 font-mono text-faint">{filtered.length}</span>
                </SectionTitle>
                {!filtered.length ? (
                  <StateMessage
                    title="No matching forecasts"
                    description={
                      rows.length ? "Измените поиск, систему или уровень риска." : `В источнике нет прогнозов для горизонта ${horizon}h.`
                    }
                    action={
                      rows.length ? (
                        <Button variant="outline" size="sm" onClick={reset}>
                          Reset filters
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
                                    aria-label={`Sort by ${column.label}`}
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
                              <span className="sr-only">Details</span>
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
                                    {row.scoreType === "calibrated_probability" ? "Probability" : "Risk score"}
                                  </p>
                                </td>
                                <td className="px-3 py-3 font-mono">{row.horizon}h</td>
                                <td className="px-3 py-3 text-muted-foreground">
                                  {actionUnavailable ? "Unavailable" : (responses.get(row.assetId) ?? "No open action")}
                                </td>
                                <td className="px-3 py-3">
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    aria-label={`View forecast ${row.assetId}`}
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
                          Previous
                        </Button>
                        <span className="font-mono text-[11px] text-faint">
                          {currentPage + 1} / {totalPages}
                        </span>
                        <Button variant="ghost" size="sm" disabled={currentPage + 1 >= totalPages} onClick={() => setPage(currentPage + 1)}>
                          Next
                        </Button>
                      </div>
                    </div>
                  </>
                )}
              </section>
              <div className="mx-6 mb-6 flex flex-wrap items-center justify-between gap-3 border-t border-border-soft pt-3 text-[11px] text-faint">
                <span>VENA · Snapshot analytics · {workflowMode === "demo" ? "Демо-срез" : "Результаты моделей"}</span>
                <Link href="/network" className="text-vena">
                  Перейти к объектам и карте ↗
                </Link>
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
