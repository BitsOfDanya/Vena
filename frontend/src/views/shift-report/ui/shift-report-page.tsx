"use client"

import { useQuery } from "@tanstack/react-query"
import { Printer } from "lucide-react"
import * as React from "react"

import { OUTCOME_LABEL } from "@/entities/maintenance"
import { SCENARIO_LABEL, type PredictionScenario } from "@/entities/prediction"
import { apiFetch } from "@/shared/api/http"
import { formatCount } from "@/shared/lib/plural"
import { formatDateTime } from "@/shared/lib/time"
import { cn } from "@/shared/lib/utils"
import { Button } from "@/shared/ui/button"
import { Segmented } from "@/shared/ui/segmented"
import { LoadingBar, StateMessage } from "@/shared/ui/state-message"

type TopItem = {
  asset_id: string
  name: string | null
  location: string | null
  scenario: string
  probability: number
  horizon_hours: number | null
  risk_level: string
  reason: string | null
}

type EventItem = { event_id: string; channel_id: string; name: string; object_id: string | null; ts: string; value: string; alarm: boolean }

type ShiftReport = {
  generated_at: string
  hours: number
  from: string
  to: string
  predicted: {
    available: boolean
    prediction_time: string | null
    total: number
    levels: Record<string, number>
    scenarios: Record<string, number>
    incidents: number
    top: TopItem[]
  }
  happened: {
    available: boolean
    from: string | null
    to: string | null
    total: number
    truncated?: boolean
    kinds: Record<string, number>
    objects: { object_id: string; events: number }[]
    latest: EventItem[]
  }
  done: {
    created: number
    from_models: number
    completed: number
    open: number
    overdue: number
    outcomes: Record<string, number>
    completed_items: { asset_id: string; reason: string; outcome: string | null; note: string; completed_at: string | null }[]
  }
}

const WINDOWS = [
  { value: 8, label: "8 ч" },
  { value: 12, label: "12 ч" },
  { value: 24, label: "24 ч" },
]

const KIND_LABEL: Record<string, string> = {
  smoke: "обнаружен дым",
  fault: "неисправность",
  power: "обесточивание",
  flood: "затопление",
  alarm: "прочие тревоги",
  state: "смена состояния",
}

const OUTCOMES: Record<string, string> = {
  ...OUTCOME_LABEL,
  false_or_irrelevant_signal: "Ложный или нерелевантный сигнал",
  "без исхода": "без исхода",
}

function stamp(value: string | null) {
  return value ? formatDateTime(Date.parse(value)) : "—"
}

function Cell({ label, value, tone }: { label: string; value: React.ReactNode; tone?: "critical" | "attention" }) {
  return (
    <div className="border-r border-b border-border px-4 py-3">
      <p className="text-[12px] text-muted-foreground">{label}</p>
      <p
        className={cn(
          "mt-1 font-mono text-[24px] leading-none font-medium tabular-nums",
          tone === "critical" && "text-status-critical",
          tone === "attention" && "text-status-attention"
        )}
      >
        {value}
      </p>
    </div>
  )
}

function Section({ index, title, note, children }: { index: string; title: string; note: string; children: React.ReactNode }) {
  return (
    <section className="break-inside-avoid border border-border bg-elevated">
      <header className="flex flex-wrap items-baseline gap-x-4 gap-y-1 border-b border-border px-4 py-3">
        <span className="font-mono text-[13px] text-vena">{index}</span>
        <h2 className="text-[16px] font-semibold">{title}</h2>
        <span className="text-[12.5px] text-muted-foreground">{note}</span>
      </header>
      {children}
    </section>
  )
}

function Table({ head, rows }: { head: string[]; rows: React.ReactNode[][] }) {
  if (rows.length === 0) return <p className="px-4 py-4 text-[13px] text-muted-foreground">Нет записей.</p>
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-left text-[13px]">
        <thead className="border-b border-border bg-surface/60 text-[12px] text-muted-foreground">
          <tr>
            {head.map((label) => (
              <th key={label} className="px-4 py-2 font-medium">
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index} className="border-b border-border-soft align-top last:border-b-0">
              {row.map((cell, cellIndex) => (
                <td key={cellIndex} className="px-4 py-2">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function ShiftReportPage() {
  const [hours, setHours] = React.useState(12)
  const report = useQuery({
    queryKey: ["shift-report", hours],
    queryFn: () => apiFetch<ShiftReport>(`/api/v1/reports/shift?hours=${hours}`),
    staleTime: 30_000,
  })
  const data = report.data

  return (
    <div className="size-full overflow-y-auto print:overflow-visible">
      <div className="mx-auto flex w-full max-w-[1200px] flex-col gap-5 px-4 py-5 sm:px-6 print:max-w-none print:px-0">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="font-mono text-[12px] text-muted-foreground">VENA · ОТЧЁТ СМЕНЫ</p>
            <h1 className="text-[24px] font-semibold tracking-[-0.01em]">Отчёт смены</h1>
            <p className="text-[13px] text-muted-foreground">
              {data ? `${stamp(data.from)} — ${stamp(data.to)} · сформирован ${stamp(data.generated_at)}` : "Что предсказали, что произошло, что сделали"}
            </p>
          </div>
          <div className="flex items-center gap-2 print:hidden">
            <Segmented label="Длительность смены" value={hours} onChange={setHours} options={WINDOWS} />
            <Button variant="outline" size="sm" onClick={() => window.print()} disabled={!data}>
              <Printer className="size-3.5" /> Печать / PDF
            </Button>
          </div>
        </div>

        {report.isPending ? (
          <LoadingBar className="min-h-40" />
        ) : report.isError || !data ? (
          <StateMessage title="Отчёт недоступен" description="Не удалось собрать отчёт смены." />
        ) : (
          <>
            <Section
              index="01"
              title="Что предсказали"
              note={data.predicted.prediction_time ? `прогноз на ${stamp(data.predicted.prediction_time)}` : "снимок прогнозов недоступен"}
            >
              <div className="grid grid-cols-2 border-l border-border sm:grid-cols-4">
                <Cell label="Критично" value={formatCount(data.predicted.levels.critical ?? 0)} tone="critical" />
                <Cell label="Внимание" value={formatCount(data.predicted.levels.attention ?? 0)} tone="attention" />
                <Cell label="Ситуаций по участкам" value={formatCount(data.predicted.incidents)} />
                <Cell label="Прогнозов всего" value={formatCount(data.predicted.total)} />
              </div>
              <p className="px-4 pt-3 text-[12.5px] text-muted-foreground">
                По сценариям:{" "}
                {Object.entries(data.predicted.scenarios)
                  .sort((left, right) => right[1] - left[1])
                  .map(([scenario, count]) => `${SCENARIO_LABEL[scenario as PredictionScenario] ?? scenario} ${count}`)
                  .join(" · ") || "—"}
              </p>
              <div className="mt-3 border-t border-border">
                <Table
                  head={["Канал", "Место", "Сценарий", "Риск", "Причина"]}
                  rows={data.predicted.top.map((item) => [
                    <span key="name" className="font-medium">{item.name ?? item.asset_id}</span>,
                    <span key="place" className="text-muted-foreground">{item.location ?? "—"}</span>,
                    SCENARIO_LABEL[item.scenario as PredictionScenario] ?? item.scenario,
                    <span key="risk" className={cn("font-mono tabular-nums", item.risk_level === "critical" ? "text-status-critical" : "text-status-attention")}>
                      {Math.round(item.probability * 100)}% / {item.horizon_hours ?? "—"} ч
                    </span>,
                    <span key="why" className="text-muted-foreground">{item.reason ?? "—"}</span>,
                  ])}
                />
              </div>
            </Section>

            <Section
              index="02"
              title="Что произошло"
              note={
                data.happened.available
                  ? `по журналу СМВУ, ${stamp(data.happened.from)} — ${stamp(data.happened.to)}${data.happened.truncated ? ", показаны последние 500" : ""}`
                  : "журнал событий не подключён"
              }
            >
              <div className="grid grid-cols-2 border-l border-border sm:grid-cols-5">
                {["smoke", "fault", "power", "flood", "alarm"].map((kind) => (
                  <Cell
                    key={kind}
                    label={KIND_LABEL[kind]}
                    value={formatCount(data.happened.kinds[kind] ?? 0)}
                    tone={kind === "smoke" || kind === "flood" ? "critical" : kind === "fault" || kind === "power" ? "attention" : undefined}
                  />
                ))}
              </div>
              {data.happened.objects.length ? (
                <p className="px-4 pt-3 text-[12.5px] text-muted-foreground">
                  Больше всего событий: {data.happened.objects.map((item) => `объект ${item.object_id} — ${item.events}`).join(" · ")}
                </p>
              ) : null}
              <div className="mt-3 border-t border-border">
                <Table
                  head={["Время", "Канал", "Объект", "Состояние"]}
                  rows={data.happened.latest.map((event) => [
                    <span key="ts" className="font-mono text-[12px] whitespace-nowrap">{stamp(event.ts)}</span>,
                    event.name,
                    event.object_id ?? "—",
                    <span key="value" className={event.alarm ? "text-status-critical" : "text-status-attention"}>{event.value}</span>,
                  ])}
                />
              </div>
            </Section>

            <Section index="03" title="Что сделали" note={`работы за последние ${data.hours} ч`}>
              <div className="grid grid-cols-2 border-l border-border sm:grid-cols-5">
                <Cell label="Создано работ" value={formatCount(data.done.created)} />
                <Cell label="Из них по моделям" value={formatCount(data.done.from_models)} />
                <Cell label="Закрыто" value={formatCount(data.done.completed)} />
                <Cell label="Открыто сейчас" value={formatCount(data.done.open)} />
                <Cell label="Просрочено" value={formatCount(data.done.overdue)} tone={data.done.overdue ? "attention" : undefined} />
              </div>
              {Object.keys(data.done.outcomes).length ? (
                <p className="px-4 pt-3 text-[12.5px] text-muted-foreground">
                  Исходы:{" "}
                  {Object.entries(data.done.outcomes)
                    .map(([outcome, count]) => `${OUTCOMES[outcome] ?? outcome} ${count}`)
                    .join(" · ")}
                </p>
              ) : null}
              <div className="mt-3 border-t border-border">
                <Table
                  head={["Закрыта", "Канал", "Работа", "Исход"]}
                  rows={data.done.completed_items.map((item) => [
                    <span key="ts" className="font-mono text-[12px] whitespace-nowrap">{stamp(item.completed_at)}</span>,
                    <span key="asset" className="font-mono">{item.asset_id}</span>,
                    item.reason || "—",
                    item.outcome ? (OUTCOMES[item.outcome] ?? item.outcome) : "—",
                  ])}
                />
              </div>
            </Section>
            <p className="font-mono text-[11px] text-faint">VENA · КОМАНДА 5BIT · ОТЧЁТ СФОРМИРОВАН АВТОМАТИЧЕСКИ</p>
          </>
        )}
      </div>
    </div>
  )
}
