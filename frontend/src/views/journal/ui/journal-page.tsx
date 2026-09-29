"use client"

import { ArrowDownToLine, RefreshCw, Search } from "lucide-react"
import Link from "next/link"
import * as React from "react"

import {
  DECISION_LABEL,
  JOURNAL_OUTCOME_LABEL,
  useJournal,
  useJournalSummary,
  type JournalDecision,
  type JournalEntry,
} from "@/entities/journal"
import { SCENARIO_LABEL, formatProbability, modelLabel, type PredictionScenario } from "@/entities/prediction"
import { workflowMode } from "@/shared/config/env"
import { formatDateTime } from "@/shared/lib/time"
import { cn } from "@/shared/lib/utils"
import { Button } from "@/shared/ui/button"
import { Input } from "@/shared/ui/input"
import { NativeSelect, NativeSelectOption } from "@/shared/ui/native-select"
import { StateMessage } from "@/shared/ui/state-message"

import { exportJournalCsv, filterJournal, type JournalFilter } from "../model/journal"

const PAGE_SIZE = 50
const SCENARIOS = Object.keys(SCENARIO_LABEL) as PredictionScenario[]
const DECISIONS = Object.keys(DECISION_LABEL) as JournalDecision[]
const DECISION_TONE: Record<JournalDecision, string> = {
  awaiting_decision: "text-status-attention",
  crew_dispatched: "text-vena",
  no_dispatch: "text-muted-foreground",
  completed: "text-status-normal",
  cancelled: "text-faint",
}

function Metric({ label, value, hint }: { label: string; value: React.ReactNode; hint: string }) {
  return (
    <div className="flex flex-col gap-2 border-r border-border-soft px-5 py-4 last:border-r-0">
      <span className="text-[11px] tracking-[0.08em] text-faint uppercase">{label}</span>
      <span className="font-mono text-[30px] leading-none tabular-nums">{value}</span>
      <span className="text-[12px] text-muted-foreground">{hint}</span>
    </div>
  )
}

function scoreText(row: JournalEntry) {
  return row.score === null ? "—" : formatProbability(row.score)
}

export function JournalPage() {
  const journal = useJournal()
  const summary = useJournalSummary()
  const [filter, setFilter] = React.useState<JournalFilter>({ query: "", scenario: "all", decision: "all" })
  const [page, setPage] = React.useState(0)

  const rows = React.useMemo(() => filterJournal(journal.data ?? [], filter), [journal.data, filter])
  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE))
  const visible = rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  const update = (next: Partial<JournalFilter>) => {
    setFilter((current) => ({ ...current, ...next }))
    setPage(0)
  }

  const exportCsv = () => {
    const url = URL.createObjectURL(new Blob([exportJournalCsv(rows)], { type: "text/csv;charset=utf-8" }))
    const link = document.createElement("a")
    link.href = url
    link.download = "vena-forecast-journal.csv"
    link.click()
    URL.revokeObjectURL(url)
  }

  if (workflowMode !== "api") {
    return (
      <div className="flex size-full items-center justify-center p-6">
        <StateMessage
          title="Журнал требует API"
          description="Журнал прогнозов хранится в PostgreSQL. Запустите стенд с NEXT_PUBLIC_VENA_WORKFLOW_MODE=api."
        />
      </div>
    )
  }

  return (
    <div className="flex size-full min-h-0 flex-col">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-4 border-b border-border px-6 py-4">
        <div className="flex items-baseline gap-4">
          <h1 className="text-[26px] font-semibold tracking-[-0.01em]">Журнал прогнозов</h1>
          <span className="font-mono text-[12px] text-faint">прогноз · решение · результат</span>
        </div>
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            aria-label="Обновить журнал"
            disabled={journal.isFetching}
            onClick={() => {
              void journal.refetch()
              void summary.refetch()
            }}
          >
            <RefreshCw className={cn("size-3.5", journal.isFetching && "animate-spin")} />
          </Button>
          <Button variant="outline" size="sm" onClick={exportCsv} disabled={!rows.length}>
            <ArrowDownToLine className="size-3.5" /> Экспорт CSV
          </Button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <p className="border-b border-border-soft px-6 py-2.5 text-[12px] text-muted-foreground">
          Каждый прогноз, дошедший до диспетчера: решение с причиной из справочника и результат работ. Размеченные записи
          выгружаются для дообучения моделей.
        </p>

        {journal.isError || summary.isError ? (
          <div className="p-6">
            <StateMessage
              title="Журнал недоступен"
              description="Бэкенд не ответил. Проверьте подключение к API."
              action={
                <Button variant="outline" size="sm" onClick={() => journal.refetch()}>
                  Повторить
                </Button>
              }
            />
          </div>
        ) : (
          <>
            <section aria-label="Сводка журнала" className="mx-6 mt-5 grid grid-cols-2 border border-border md:grid-cols-4">
              <Metric label="Прогнозы" value={summary.data?.total ?? "—"} hint="Прогнозов в журнале" />
              <Metric label="Ожидают решения" value={summary.data?.pending ?? "—"} hint="Нужна реакция диспетчера" />
              <Metric label="Бригада выехала" value={summary.data?.inWork ?? "—"} hint="Работы в процессе" />
              <Metric label="С обратной связью" value={summary.data?.decided ?? "—"} hint="Размечено для дообучения" />
            </section>

            <section aria-label="Обратная связь по сценариям" className="mx-6 mt-5 border border-border">
              <div className="border-b border-border-soft px-5 py-3">
                <h2 className="text-[11px] tracking-[0.08em] uppercase">Обратная связь по сценариям</h2>
                <p className="mt-1 text-[12px] text-muted-foreground">
                  Доля подтверждённых среди решённых — обратная связь диспетчеров, а не метрика модели на отложенной
                  выборке.
                </p>
              </div>
              {(summary.data?.byScenario.length ?? 0) === 0 ? (
                <p className="px-5 py-4 text-[13px] text-muted-foreground">Пока нет прогнозов с решениями.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[560px] text-left text-[13px]">
                    <thead className="border-b border-border-soft text-[11px] tracking-[0.08em] text-faint uppercase">
                      <tr>
                        <th className="px-5 py-2 font-medium">Сценарий</th>
                        <th className="px-5 py-2 text-right font-medium">Прогнозы</th>
                        <th className="px-5 py-2 text-right font-medium">Решено</th>
                        <th className="px-5 py-2 text-right font-medium">Подтверждено</th>
                        <th className="px-5 py-2 text-right font-medium">Отклонено</th>
                        <th className="px-5 py-2 text-right font-medium">Подтверждение</th>
                      </tr>
                    </thead>
                    <tbody>
                      {summary.data?.byScenario.map((row) => (
                        <tr key={row.scenario} className="border-b border-border-soft last:border-b-0">
                          <td className="px-5 py-2">{SCENARIO_LABEL[row.scenario]}</td>
                          <td className="px-5 py-2 text-right font-mono tabular-nums">{row.forecasts}</td>
                          <td className="px-5 py-2 text-right font-mono tabular-nums">{row.decided}</td>
                          <td className="px-5 py-2 text-right font-mono text-status-normal tabular-nums">{row.confirmed}</td>
                          <td className="px-5 py-2 text-right font-mono text-muted-foreground tabular-nums">{row.rejected}</td>
                          <td className="px-5 py-2 text-right font-mono tabular-nums">
                            {row.confirmationRate === null ? "—" : `${Math.round(row.confirmationRate * 100)}%`}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <section aria-label="Фильтры журнала" className="flex flex-wrap items-center gap-3 px-6 pt-5 pb-3">
              <div className="relative min-w-48 flex-1">
                <Search className="pointer-events-none absolute top-2.5 left-2.5 size-3.5 text-faint" />
                <Input
                  aria-label="Поиск по журналу"
                  className="h-9 pl-8 text-[12px]"
                  placeholder="Объект, локация, модель, примечание…"
                  value={filter.query}
                  onChange={(event) => update({ query: event.target.value })}
                />
              </div>
              <NativeSelect
                aria-label="Фильтр по сценарию"
                value={filter.scenario}
                onChange={(event) => update({ scenario: event.target.value as JournalFilter["scenario"] })}
              >
                <NativeSelectOption value="all">Все сценарии</NativeSelectOption>
                {SCENARIOS.map((value) => (
                  <NativeSelectOption key={value} value={value}>
                    {SCENARIO_LABEL[value]}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
              <NativeSelect
                aria-label="Фильтр по решению"
                value={filter.decision}
                onChange={(event) => update({ decision: event.target.value as JournalFilter["decision"] })}
              >
                <NativeSelectOption value="all">Все решения</NativeSelectOption>
                {DECISIONS.map((value) => (
                  <NativeSelectOption key={value} value={value}>
                    {DECISION_LABEL[value]}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </section>

            <section aria-label="Реестр прогнозов" className="px-6 pb-8">
              {journal.isPending ? (
                <p className="py-6 text-[13px] text-muted-foreground">Загрузка журнала…</p>
              ) : rows.length === 0 ? (
                <p className="border border-border px-5 py-4 text-[13px] text-muted-foreground">
                  {journal.data?.length ? "Нет записей под выбранные фильтры." : "Журнал пуст: прогнозы ещё не поступали."}
                </p>
              ) : (
                <>
                  <div className="overflow-x-auto border border-border">
                    <table className="w-full min-w-[960px] text-left text-[13px]">
                      <thead className="border-b border-border text-[11px] tracking-[0.08em] text-faint uppercase">
                        <tr>
                          <th className="px-4 py-2 font-medium">Прогноз</th>
                          <th className="px-4 py-2 font-medium">Объект / локация</th>
                          <th className="px-4 py-2 font-medium">Сценарий</th>
                          <th className="px-4 py-2 font-medium">Модель</th>
                          <th className="px-4 py-2 font-medium">Решение</th>
                          <th className="px-4 py-2 font-medium">Результат</th>
                        </tr>
                      </thead>
                      <tbody>
                        {visible.map((row) => (
                          <tr key={row.id} className="border-b border-border-soft align-top last:border-b-0">
                            <td className="px-4 py-2.5">
                              <Link
                                href="/actions"
                                className="font-mono text-[12px] text-vena underline-offset-4 hover:underline"
                              >
                                {row.id}
                              </Link>
                              <div className="font-mono text-[11px] text-faint tabular-nums">
                                {formatDateTime(row.createdAt)}
                              </div>
                            </td>
                            <td className="px-4 py-2.5">
                              <div className="font-mono text-[12px]">{row.assetId}</div>
                              <div className="text-[11px] text-muted-foreground">{row.location ?? "Локация не указана"}</div>
                            </td>
                            <td className="px-4 py-2.5">{SCENARIO_LABEL[row.scenario]}</td>
                            <td className="px-4 py-2.5">
                              <div className="text-[12px]" title={row.modelId ?? undefined}>
                                {modelLabel(row.modelId)}
                              </div>
                              <div className="font-mono text-[11px] text-faint tabular-nums">
                                {scoreText(row)}
                                {row.horizonHours ? ` · ${row.horizonHours} ч` : ""}
                              </div>
                            </td>
                            <td className={cn("px-4 py-2.5", DECISION_TONE[row.decision])}>
                              {DECISION_LABEL[row.decision]}
                              {row.assignee && row.decision === "crew_dispatched" ? (
                                <div className="text-[11px] text-muted-foreground">{row.assignee}</div>
                              ) : null}
                            </td>
                            <td className="px-4 py-2.5">
                              {row.outcome ? (JOURNAL_OUTCOME_LABEL[row.outcome] ?? row.outcome) : "—"}
                              {row.resultNote ? (
                                <div className="max-w-72 text-[11px] text-muted-foreground">{row.resultNote}</div>
                              ) : null}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {pages > 1 ? (
                    <div className="flex items-center justify-between pt-3 text-[12px] text-muted-foreground">
                      <span className="font-mono tabular-nums">
                        {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, rows.length)} из {rows.length}
                      </span>
                      <span className="flex gap-2">
                        <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage(page - 1)}>
                          Назад
                        </Button>
                        <Button variant="outline" size="sm" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>
                          Далее
                        </Button>
                      </span>
                    </div>
                  ) : null}
                </>
              )}
            </section>
          </>
        )}
      </div>
    </div>
  )
}
