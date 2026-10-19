"use client"

import Link from "next/link"
import * as React from "react"

import { heldOutPeriodPhrase } from "@/entities/analytics"
import {
  INCIDENT_KIND_LABEL,
  OBJECT_SCENARIOS,
  daysSinceText,
  formatPercent,
  incidentFlags,
  nowcastCaption,
  qualityCaption,
  useIncidentRegistry,
  useObjectRisks,
  type IncidentKind,
  type IncidentKindSummary,
  type ObjectRiskScenario,
} from "@/entities/incident"
import { workflowMode } from "@/shared/config/env"
import { formatCount } from "@/shared/lib/plural"
import { formatClock, formatFullDay } from "@/shared/lib/time"
import { cn } from "@/shared/lib/utils"
import { Button } from "@/shared/ui/button"
import { Segmented } from "@/shared/ui/segmented"
import { LoadingBar, StateMessage } from "@/shared/ui/state-message"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/shared/ui/table"

const HEAD = "h-9 px-4 text-[12px] font-normal text-faint"
const CELL = "px-4 py-2.5 text-right font-mono tabular-nums"
const KIND_FILTERS: { value: "all" | IncidentKind; label: string }[] = [
  { value: "all", label: "Все" },
  { value: "power", label: INCIDENT_KIND_LABEL.power },
  { value: "flood", label: INCIDENT_KIND_LABEL.flood },
  { value: "fire", label: INCIDENT_KIND_LABEL.fire },
]
const RECENT_LIMIT = 100
const OBJECT_LIST_SIZE = 15

function count(value: number | null) {
  return value == null ? "—" : formatCount(value)
}

function horizonTerm(hours: number | null | undefined) {
  if (hours == null) return "горизонт модели"
  if (hours >= 72) return "3 суток"
  if (hours >= 24) return "сутки"
  return `${hours} ч`
}

function moment(timestamp: number) {
  return `${formatFullDay(timestamp)}, ${formatClock(timestamp)}`
}

function ObjectListSection() {
  const risks = useObjectRisks()
  const [scenario, setScenario] = React.useState<ObjectRiskScenario>("power_loss")
  const [expanded, setExpanded] = React.useState(false)
  const items = (risks.data?.items ?? []).filter((item) => item.scenario === scenario)
  const visible = expanded ? items : items.slice(0, OBJECT_LIST_SIZE)
  const meta = risks.data?.models.find((item) => item.scenario === scenario)
  const caption = meta ? qualityCaption(meta, heldOutPeriodPhrase(meta.period)) : null
  const shortCaption = meta?.nowcast ? nowcastCaption(meta.nowcast, heldOutPeriodPhrase(meta.nowcast.period)) : null
  const horizon = items[0]?.horizonHours ?? null
  const shortHorizon = items.some((item) => item.probability6h != null) ? (meta?.nowcast?.horizonHours ?? 6) : null

  return (
    <section aria-label="Утренний список объектов" className="border border-border bg-elevated">
      <div className="flex flex-wrap items-start gap-3 border-b border-border-soft px-4 py-3">
        <div className="min-w-0 flex-1">
          <h2 className="text-[15px] font-semibold">Утренний список объектов</h2>
          <p className="mt-1 max-w-[860px] text-[12px] text-muted-foreground">
            Объекты, на которых вероятнее всего начнётся инцидент: модель оценивает объект целиком по всем его каналам.
          </p>
          {caption ? <p className="mt-1 text-[12.5px] text-foreground">{caption}</p> : null}
          {shortCaption ? <p className="mt-0.5 text-[12.5px] text-foreground">{shortCaption}</p> : null}
          {meta?.rule ? <p className="mt-0.5 text-[12px] text-faint">Событие: {meta.rule}</p> : null}
        </div>
        <Segmented
          label="Сценарий"
          value={scenario}
          onChange={setScenario}
          options={OBJECT_SCENARIOS.map((item) => ({
            value: item.value,
            label: risks.data?.available
              ? `${item.label} ${risks.data.items.filter((risk) => risk.scenario === item.value).length}`
              : item.label,
          }))}
        />
      </div>
      {risks.isPending ? (
        <LoadingBar className="min-h-24" />
      ) : risks.isError ? (
        <StateMessage
          title="Утренний список недоступен"
          description="Не удалось загрузить оценки объектов."
          action={
            <Button variant="outline" size="sm" onClick={() => risks.refetch()}>
              Повторить
            </Button>
          }
        />
      ) : !risks.data.available ? (
        <StateMessage
          title={risks.data.detail || "Утренний список объектов ещё не рассчитан"}
          description="Оценки объектов появятся после следующего расчёта моделей."
        />
      ) : items.length === 0 ? (
        <StateMessage
          title="Нет объектов"
          description={
            risks.data.restricted
              ? "Среди ваших объектов нет оценок по этому сценарию."
              : "Для этого сценария оценок объектов пока нет."
          }
        />
      ) : (
        <Table className="text-[13px]">
          <TableHeader>
            <TableRow className="border-border-soft hover:bg-transparent">
              <TableHead className={cn(HEAD, "w-14")}>№</TableHead>
              <TableHead className={HEAD}>Объект</TableHead>
              <TableHead className={cn(HEAD, "text-right")}>Вероятность за {horizonTerm(horizon)}</TableHead>
              {shortHorizon != null ? (
                <TableHead className={cn(HEAD, "text-right")}>За {shortHorizon} ч</TableHead>
              ) : null}
              <TableHead className={cn(HEAD, "text-right")}>Инцидентов за 7 дней</TableHead>
              <TableHead className={cn(HEAD, "text-right")}>Инцидентов за 30 дней</TableHead>
              <TableHead className={cn(HEAD, "text-right")}>Дней с последнего</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {visible.map((item) => (
              <TableRow key={`${item.modelId}-${item.objectId}`} className="border-border-soft">
                <TableCell className="px-4 py-2.5 font-mono text-faint tabular-nums">{item.rank}</TableCell>
                <TableCell className="px-4 py-2.5">
                  <Link href="/timeline" className="font-medium underline-offset-4 hover:text-vena hover:underline">
                    {item.objectName}
                  </Link>
                  <span className="ml-2 font-mono text-[12px] text-faint">{item.objectId}</span>
                </TableCell>
                <TableCell className={CELL}>{formatPercent(item.probability)}</TableCell>
                {shortHorizon != null ? (
                  <TableCell className={CELL}>{formatPercent(item.probability6h)}</TableCell>
                ) : null}
                <TableCell className={CELL}>{count(item.history.events7d)}</TableCell>
                <TableCell className={CELL}>{count(item.history.events30d)}</TableCell>
                <TableCell className={CELL}>{daysSinceText(item.history.daysSince)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      {items.length > OBJECT_LIST_SIZE ? (
        <div className="border-t border-border-soft px-4 py-2.5">
          <Button variant="ghost" size="sm" onClick={() => setExpanded((value) => !value)}>
            {expanded ? `Показать первые ${OBJECT_LIST_SIZE}` : `Показать все ${items.length}`}
          </Button>
        </div>
      ) : null}
    </section>
  )
}

function YearBars({ perYear, journalEnd }: { perYear: IncidentKindSummary["perYear"]; journalEnd: string | null }) {
  if (perYear.length === 0) return null
  const max = Math.max(1, ...perYear.map((item) => item.count))
  const partialYear = journalEnd && !journalEnd.endsWith("-12-31") ? journalEnd.slice(0, 4) : null
  return (
    <div>
      <p className="text-[12px] text-muted-foreground">Инцидентов в год, шт.</p>
      <div className="mt-2 flex h-20 items-end gap-1.5" role="img" aria-label="Инцидентов по годам">
        {perYear.map((item) => {
          const height = Math.max(3, Math.round((item.count / max) * 56))
          const partial = item.year === partialYear
          return (
            <div
              key={item.year}
              className="flex min-w-0 flex-1 flex-col items-center gap-1"
              title={`${item.year}: ${formatCount(item.count)}${partial ? " (неполный год)" : ""}`}
            >
              <div className={cn("w-full max-w-7", partial ? "bg-vena/40" : "bg-vena/70")} style={{ height }} />
              <span className="truncate font-mono text-[10px] text-faint">{item.year.slice(2)}</span>
            </div>
          )
        })}
      </div>
      <p className="mt-1 text-[11px] text-faint">
        По оси — год
        {partialYear ? `; ${partialYear} — по ${journalEnd?.split("-").reverse().join(".")}` : ""}
      </p>
    </div>
  )
}

function KindCard({ summary, journalEnd }: { summary: IncidentKindSummary; journalEnd: string | null }) {
  const extra =
    summary.kind === "fire" && summary.temperatureConfirmed != null
      ? `с ростом температуры — ${formatCount(summary.temperatureConfirmed)}`
      : summary.kind === "flood" && summary.longOver30Minutes != null
        ? `дольше 30 минут — ${formatCount(summary.longOver30Minutes)}`
        : null
  return (
    <div className="flex min-w-0 flex-col gap-3 px-4 py-4">
      <div>
        <p className="text-[12.5px] font-medium text-muted-foreground">{summary.label}</p>
        <p className="mt-1 flex items-baseline gap-2">
          <span className="font-mono text-[26px] leading-none font-medium tabular-nums">
            {formatCount(summary.total)}
          </span>
          <span className="text-[12.5px] text-muted-foreground">
            инцидентов на {formatCount(summary.objects)} объектах
          </span>
        </p>
      </div>
      <YearBars perYear={summary.perYear} journalEnd={journalEnd} />
      {summary.recent2026h1 != null || extra ? (
        <div className="text-[12px] text-muted-foreground">
          {summary.recent2026h1 != null ? (
            <p>
              январь–июнь 2026: {formatCount(summary.recent2026h1)}
              {summary.perDay2026h1 != null ? `, ${summary.perDay2026h1.toFixed(1).replace(".", ",")} в сутки` : ""}
            </p>
          ) : null}
          {extra ? <p>{extra}</p> : null}
        </div>
      ) : null}
      {summary.rule ? <p className="text-[12px] text-faint">Правило: {summary.rule}</p> : null}
    </div>
  )
}

function RegistrySection() {
  const registry = useIncidentRegistry()
  const [kind, setKind] = React.useState<"all" | IncidentKind>("all")
  const recent = (registry.data?.recent ?? []).filter((item) => kind === "all" || item.kind === kind)

  return (
    <section aria-label="Реестр инцидентов" className="border border-border bg-elevated">
      <div className="border-b border-border-soft px-4 py-3">
        <h2 className="text-[15px] font-semibold">Реестр инцидентов</h2>
        <p className="mt-1 max-w-[860px] text-[12px] text-muted-foreground">
          Инциденты, восстановленные из журнала СМВУ по правилам сценариев
          {registry.data?.journalEnd ? `, журнал по ${registry.data.journalEnd.split("-").reverse().join(".")}` : ""}.
          {registry.data?.restricted ? " Сводка — по всей сети, списки — по вашим объектам." : ""}
        </p>
      </div>
      {registry.isPending ? (
        <LoadingBar className="min-h-40" />
      ) : registry.isError ? (
        <StateMessage
          title="Реестр недоступен"
          description="Не удалось загрузить реестр инцидентов."
          action={
            <Button variant="outline" size="sm" onClick={() => registry.refetch()}>
              Повторить
            </Button>
          }
        />
      ) : !registry.data.available ? (
        <StateMessage
          title={registry.data.detail || "Реестр инцидентов ещё не рассчитан"}
          description="Реестр появится после расчёта инцидентов по журналу."
        />
      ) : (
        <>
          {registry.data.kinds.length > 0 ? (
            <div className="grid border-b border-border-soft md:grid-cols-3 md:divide-x md:divide-border-soft">
              {registry.data.kinds.map((summary) => (
                <KindCard key={summary.kind} summary={summary} journalEnd={registry.data.journalEnd} />
              ))}
            </div>
          ) : null}
          <div className="flex flex-wrap items-center gap-3 border-b border-border-soft px-4 py-3">
            <h3 className="text-[14px] font-semibold">Последние инциденты</h3>
            <span className="font-mono text-[12px] text-faint tabular-nums">{recent.length}</span>
            <Segmented
              className="sm:ml-auto"
              label="Тип инцидента"
              value={kind}
              onChange={setKind}
              options={KIND_FILTERS}
            />
          </div>
          {recent.length === 0 ? (
            <StateMessage
              title={registry.data.detail || "Нет инцидентов"}
              description={
                registry.data.detail
                  ? "Список появится после следующего расчёта реестра."
                  : registry.data.restricted
                    ? "На ваших объектах инцидентов этого типа не было."
                    : "Инцидентов этого типа в реестре нет."
              }
            />
          ) : (
            <Table className="text-[13px]">
              <TableHeader>
                <TableRow className="border-border-soft hover:bg-transparent">
                  <TableHead className={HEAD}>Начало</TableHead>
                  <TableHead className={HEAD}>Тип</TableHead>
                  <TableHead className={HEAD}>Объект</TableHead>
                  <TableHead className={cn(HEAD, "text-right")}>Каналов</TableHead>
                  <TableHead className={HEAD}>Признаки</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {recent.slice(0, RECENT_LIMIT).map((item) => {
                  const flags = incidentFlags(item)
                  return (
                    <TableRow key={`${item.kind}-${item.objectId}-${item.start}`} className="border-border-soft">
                      <TableCell className="px-4 py-2.5 font-mono text-[12px] whitespace-nowrap tabular-nums">
                        {moment(item.start)}
                      </TableCell>
                      <TableCell className="px-4 py-2.5">{INCIDENT_KIND_LABEL[item.kind]}</TableCell>
                      <TableCell className="px-4 py-2.5">
                        {item.objectName}
                        <span className="ml-2 font-mono text-[12px] text-faint">{item.objectId}</span>
                      </TableCell>
                      <TableCell className={CELL}>{count(item.channels)}</TableCell>
                      <TableCell className="px-4 py-2.5">
                        {flags.length > 0 ? (
                          <span className="flex flex-wrap gap-1.5">
                            {flags.map((flag) => (
                              <span
                                key={flag}
                                className="border border-status-attention/40 px-1.5 text-[12px] text-status-attention"
                              >
                                {flag}
                              </span>
                            ))}
                          </span>
                        ) : (
                          <span className="text-faint">—</span>
                        )}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
          {recent.length > RECENT_LIMIT ? (
            <p className="border-t border-border-soft px-4 py-2 text-[12px] text-muted-foreground">
              Показаны последние {RECENT_LIMIT} из {formatCount(recent.length)}.
            </p>
          ) : null}
        </>
      )}
    </section>
  )
}

export function IncidentsPage() {
  if (workflowMode !== "api") {
    return (
      <StateMessage
        title="Инциденты доступны в рабочем режиме"
        description="Утренний список объектов и реестр инцидентов загружаются из API сервиса."
      />
    )
  }

  return (
    <div className="size-full overflow-y-auto">
      <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-5 px-4 py-5 sm:px-6">
        <div>
          <h1 className="text-[24px] font-semibold tracking-[-0.01em]">Инциденты</h1>
          <p className="mt-1 max-w-[760px] text-[13.5px] text-muted-foreground">
            Какие объекты проверить в первую очередь и что уже случалось: утренний список по сценариям и реестр
            инцидентов из журнала.
          </p>
        </div>
        <ObjectListSection />
        <RegistrySection />
      </div>
    </div>
  )
}
