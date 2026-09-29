"use client"

import * as React from "react"

import { formatProbability } from "@/entities/prediction"
import { useAlarmKpis } from "@/entities/analytics"
import { useAccessEvents, useAccessRoutes, useAlarms, type AccessEvent, type AccessRoute, type AlarmAssessment } from "@/entities/signal"
import { workflowMode } from "@/shared/config/env"
import { formatDateTime } from "@/shared/lib/time"
import { cn } from "@/shared/lib/utils"
import { Segmented } from "@/shared/ui/segmented"
import { StateMessage } from "@/shared/ui/state-message"

type View = "alarms" | "access"

const VIEWS: { value: View; label: string }[] = [
  { value: "alarms", label: "Тревоги" },
  { value: "access", label: "Доступ" },
]

function Metric({ label, value, hint }: { label: string; value: React.ReactNode; hint: string }) {
  return (
    <div className="flex flex-col gap-2 border-r border-border-soft px-5 py-4 last:border-r-0">
      <span className="text-[12px] text-faint">{label}</span>
      <span className="font-mono text-[30px] leading-none tabular-nums">{value}</span>
      <span className="text-[12px] text-muted-foreground">{hint}</span>
    </div>
  )
}

function Place({ name, location, channelId }: { name: string | null; location: string | null; channelId: string }) {
  return (
    <>
      <div>{name ?? channelId}</div>
      <div className="text-[11px] text-muted-foreground">
        {location ?? "Локация не указана"} · <span className="font-mono">{channelId}</span>
      </div>
    </>
  )
}

const CATEGORY_LABEL: Record<string, string> = {
  fire: "Пожар",
  gas: "Газ",
  flooding: "Затопление",
  flood: "Затопление",
  intrusion: "Проникновение",
  access: "Проникновение",
  temperature: "Температура",
}

function monthLabel(start: string) {
  if (!start) return "—"
  const stamp = start.slice(0, 7)
  const [year, month] = stamp.split("-")
  if (!year || !month) return stamp
  return `${month}.${year.slice(2)}`
}

function AlarmMonthsBars({
  months,
  manageable,
}: {
  months: { start: string; perHourMean: number }[]
  manageable: number
}) {
  if (months.length === 0) return null
  const recent = months.slice(-12)
  const max = Math.max(manageable, ...recent.map((item) => item.perHourMean), 1)
  return (
    <div className="mt-3">
      <p className="text-[12px] text-faint">Тревог /ч по месяцам</p>
      <div className="mt-2 flex h-14 items-end gap-1">
        {recent.map((item) => {
          const height = Math.max(4, Math.round((item.perHourMean / max) * 48))
          const over = item.perHourMean > manageable
          return (
            <div key={item.start} className="flex min-w-0 flex-1 flex-col items-center gap-1" title={`${monthLabel(item.start)}: ${item.perHourMean.toFixed(1)}/ч`}>
              <div
                className={cn("w-full max-w-5", over ? "bg-status-attention" : "bg-vena/70")}
                style={{ height }}
              />
              <span className="truncate font-mono text-[9px] text-faint">{monthLabel(item.start)}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function AlarmLoadStrip() {
  const kpis = useAlarmKpis()
  if (workflowMode !== "api" || kpis.isPending || kpis.isError || !kpis.data?.recent) return null
  const recent = kpis.data.recent
  return (
    <section aria-label="Нагрузка тревог ISA-18.2" className="mx-6 mt-4 border border-border bg-elevated px-4 py-3">
      <p className="text-[12px] text-faint">Нагрузка тревог · ISA-18.2</p>
      <p className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-[13px]">
        <span>
          <span className="font-mono text-[18px] tabular-nums">{recent.perHourMean.toFixed(1)}</span>
          <span className="ml-1 text-muted-foreground">/ч · норма {kpis.data.manageablePerHour}</span>
        </span>
        <span className="text-muted-foreground">
          лавины {recent.activationsInFloods == null ? "—" : `${Math.round(recent.activationsInFloods * 100)} %`}
        </span>
        <span className="text-muted-foreground">
          дребезг: {recent.chatteringTop.slice(0, 3).map((item) => item.name ?? item.channelId).join(", ") || "—"}
        </span>
      </p>
      <AlarmMonthsBars months={kpis.data.months} manageable={kpis.data.manageablePerHour} />
    </section>
  )
}

function AlarmsTable({ alarms }: { alarms: AlarmAssessment[] }) {
  const [onlyFlagged, setOnlyFlagged] = React.useState(true)
  const rows = onlyFlagged ? alarms.filter((alarm) => alarm.needsVerification) : alarms
  const flagged = alarms.filter((alarm) => alarm.needsVerification).length
  const maintenance = alarms.filter((alarm) => alarm.maintenance).length
  return (
    <>
      <AlarmLoadStrip />
      <section aria-label="Сводка по тревогам" className="mx-6 mt-5 grid grid-cols-1 border border-border sm:grid-cols-4">
        <Metric label="Тревоги, 30 дней" value={alarms.length} hint="Тревоги дыма, газа и температуры" />
        <Metric label="Серии ППР" value={maintenance} hint="Проверки извещателей в рабочее время" />
        <Metric label="Сначала проверить" value={flagged} hint="Низкая вероятность подтверждения" />
        <Metric
          label="Доля"
          value={alarms.length ? `${Math.round((flagged / alarms.length) * 100)}%` : "—"}
          hint="Доля тревог на проверку перед выездом"
        />
      </section>
      <p className="mx-6 mt-4 text-[12px] leading-relaxed text-muted-foreground">
        Вероятность — шанс, что тревога подтвердится в течение 30 минут: повтором, срабатыванием соседнего датчика или
        продолжением тревожного состояния. Метка «проверить перед выездом» стоит у тревог, которые подтверждаются реже
        обычного: в первом полугодии 2026 года среди них не подтвердились 48 % против 21 % в среднем. Серия ППР — 5 и
        более дымовых датчиков объекта за 10 минут или 3 и более газоанализатора за 30 минут в рабочее время: это
        плановая проверка, выезд не нужен. Метка — подсказка для проверки по камерам и телеметрии, а не вывод о ложности.
      </p>
      <div className="flex items-center gap-2 px-6 pt-4 pb-3 text-[12px]">
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={onlyFlagged} onChange={(event) => setOnlyFlagged(event.target.checked)} />
          Только «проверить перед выездом»
        </label>
      </div>
      <div className="mx-6 mb-8 overflow-x-auto border border-border">
        <table className="w-full min-w-[760px] text-left text-[13px]">
          <thead className="border-b border-border text-[12px] text-faint">
            <tr>
              <th className="px-4 py-2 font-medium">Время</th>
              <th className="px-4 py-2 font-medium">Датчик / локация</th>
              <th className="px-4 py-2 font-medium">Категория</th>
              <th className="px-4 py-2 text-right font-medium">Подтверждение</th>
              <th className="px-4 py-2 font-medium">Подсказка</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 300).map((alarm) => (
              <tr
                key={`${alarm.channelId}-${alarm.ts}`}
                className={cn(
                  "border-b border-border-soft align-top last:border-b-0",
                  alarm.maintenance && "text-faint"
                )}
              >
                <td className="px-4 py-2.5 font-mono text-[12px] whitespace-nowrap tabular-nums">{formatDateTime(alarm.ts)}</td>
                <td className="px-4 py-2.5">
                  <Place name={alarm.name} location={alarm.location} channelId={alarm.channelId} />
                </td>
                <td className="px-4 py-2.5">
                  <span className={cn("text-[12px]", alarm.maintenance ? "text-faint" : "text-muted-foreground")}>
                    {CATEGORY_LABEL[alarm.category] ?? alarm.sensorType}
                  </span>
                </td>
                <td className="px-4 py-2.5 text-right font-mono tabular-nums">{formatProbability(alarm.corroborationProbability)}</td>
                <td
                  className={cn(
                    "px-4 py-2.5",
                    alarm.maintenance
                      ? "text-faint"
                      : alarm.needsVerification
                        ? "text-status-attention"
                        : "text-muted-foreground"
                  )}
                >
                  {alarm.maintenance
                    ? "Серия ППР — плановая проверка, выезд не нужен"
                    : alarm.needsVerification
                      ? "Проверить по камерам перед выездом"
                      : "Типичная тревога"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 ? <p className="px-4 py-4 text-[13px] text-muted-foreground">Нет тревог.</p> : null}
      </div>
    </>
  )
}

const DIRECTION: Record<AccessRoute["direction"], string> = {
  increasing: "к большим пикетам",
  decreasing: "к меньшим пикетам",
  mixed: "с возвратами",
}

function PicketStrip({ route }: { route: AccessRoute }) {
  const pickets = route.steps
    .filter((step, index) => index === 0 || step.picket !== route.steps[index - 1].picket)
    .map((step) => step.picket)
  if (pickets.length === 0) return null
  const min = Math.min(...pickets)
  const max = Math.max(...pickets)
  const span = Math.max(1, max - min)
  const width = 280
  const height = 28
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="mt-1 text-vena" aria-hidden>
      <line x1={8} y1={14} x2={width - 8} y2={14} stroke="currentColor" strokeOpacity={0.25} strokeWidth={1} />
      {pickets.map((picket, index) => {
        const x = 8 + ((picket - min) / span) * (width - 16)
        return (
          <g key={`${picket}-${index}`}>
            <circle cx={x} cy={14} r={3.5} fill="currentColor" />
            {index < pickets.length - 1 ? (
              <line
                x1={x}
                y1={14}
                x2={8 + ((pickets[index + 1]! - min) / span) * (width - 16)}
                y2={14}
                stroke="currentColor"
                strokeWidth={1.5}
              />
            ) : null}
          </g>
        )
      })}
    </svg>
  )
}

function RoutesTable({ routes }: { routes: AccessRoute[] }) {
  return (
    <section aria-label="Маршруты по пикетам" className="mx-6 mt-4 mb-2">
      <h2 className="text-[12px] text-faint">Маршруты по пикетам, 30 дней</h2>
      <p className="mt-1 text-[12px] text-muted-foreground">
        Срабатывания точек входа одного объекта на охране с паузами до 30 минут, упорядоченные по пикетам (шаг около 10 м).
        Ниже — схема участка по пикетам, не только таблица.
      </p>
      <div className="mt-2 overflow-x-auto border border-border">
        <table className="w-full min-w-[760px] text-left text-[13px]">
          <thead className="border-b border-border text-[12px] text-faint">
            <tr>
              <th className="px-4 py-2 font-medium">Начало</th>
              <th className="px-4 py-2 font-medium">Объект</th>
              <th className="px-4 py-2 font-medium">Схема пикетов</th>
              <th className="px-4 py-2 text-right font-medium">Путь</th>
              <th className="px-4 py-2 font-medium">Направление</th>
            </tr>
          </thead>
          <tbody>
            {routes.map((route) => (
              <tr key={`${route.object}-${route.start}`} className="border-b border-border-soft align-top last:border-b-0">
                <td className="px-4 py-2.5 font-mono text-[12px] whitespace-nowrap tabular-nums">{formatDateTime(route.start)}</td>
                <td className="px-4 py-2.5">{route.object}</td>
                <td className="px-4 py-2.5">
                  <div className="font-mono text-[12px]">
                    {route.steps
                      .filter((step, index) => index === 0 || step.picket !== route.steps[index - 1].picket)
                      .map((step) => `ПК${step.picket}`)
                      .join(" → ")}
                  </div>
                  <PicketStrip route={route} />
                </td>
                <td className="px-4 py-2.5 text-right font-mono tabular-nums">
                  {route.distanceM} м{route.speedMPerMin ? ` · ${route.speedMPerMin} м/мин` : ""}
                </td>
                <td className="px-4 py-2.5 text-muted-foreground">
                  {DIRECTION[route.direction]}
                  {route.night ? ", ночью" : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {routes.length === 0 ? <p className="px-4 py-4 text-[13px] text-muted-foreground">Маршрутов нет.</p> : null}
      </div>
    </section>
  )
}

function AccessTable({ events }: { events: AccessEvent[] }) {
  const objects = new Set(events.map((event) => event.object)).size
  return (
    <>
      <section aria-label="Сводка по доступу" className="mx-6 mt-5 grid grid-cols-1 border border-border sm:grid-cols-3">
        <Metric label="К проверке, 30 дней" value={events.length} hint="Срабатывания точек входа на охране" />
        <Metric label="Объекты" value={objects} hint="Объекты с событиями" />
        <Metric label="Ночью" value={events.filter((event) => event.night).length} hint="22:00–06:00" />
      </section>
      <p className="mx-6 mt-4 text-[12px] leading-relaxed text-muted-foreground">
        Открытие двери или люка и срабатывание датчика стекла, пока объект стоит на охране. Индекс 0–1 ранжирует события
        по редкости для этого датчика в этот час недели, типу точки входа, ночному времени и цепочке срабатываний. Это
        очередь для проверки диспетчером, а не вероятность проникновения.
      </p>
      <div className="mx-6 mt-4 mb-8 overflow-x-auto border border-border">
        <table className="w-full min-w-[760px] text-left text-[13px]">
          <thead className="border-b border-border text-[12px] text-faint">
            <tr>
              <th className="px-4 py-2 font-medium">Время</th>
              <th className="px-4 py-2 font-medium">Точка входа / локация</th>
              <th className="px-4 py-2 font-medium">Тип</th>
              <th className="px-4 py-2 text-right font-medium">Индекс</th>
              <th className="px-4 py-2 font-medium">Признаки</th>
            </tr>
          </thead>
          <tbody>
            {events.map((event) => (
              <tr key={`${event.channelId}-${event.ts}`} className="border-b border-border-soft align-top last:border-b-0">
                <td className="px-4 py-2.5 font-mono text-[12px] whitespace-nowrap tabular-nums">{formatDateTime(event.ts)}</td>
                <td className="px-4 py-2.5">
                  <Place name={event.name} location={event.location} channelId={event.channelId} />
                </td>
                <td className="px-4 py-2.5">{event.sensorType}</td>
                <td className="px-4 py-2.5 text-right font-mono tabular-nums">{event.accessIndex.toFixed(2)}</td>
                <td className="px-4 py-2.5 text-muted-foreground">
                  {[event.night ? "ночью" : null, event.chain ? "цепочка срабатываний" : null].filter(Boolean).join(", ") ||
                    "редкое время для датчика"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {events.length === 0 ? <p className="px-4 py-4 text-[13px] text-muted-foreground">Событий нет.</p> : null}
      </div>
    </>
  )
}

export function AlarmsPage() {
  const [view, setView] = React.useState<View>("alarms")
  const alarms = useAlarms()
  const access = useAccessEvents()
  const routes = useAccessRoutes()
  const query = view === "alarms" ? alarms : access

  if (workflowMode !== "api") {
    return (
      <div className="flex size-full items-center justify-center p-6">
        <StateMessage title="Алармы требуют API" description="Оценки тревог и доступа приходят из снимка моделей через API." />
      </div>
    )
  }

  return (
    <div className="flex size-full min-h-0 flex-col">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-4 border-b border-border px-6 py-4">
        <div className="flex items-baseline gap-4">
          <h1 className="text-[26px] font-semibold tracking-[-0.01em]">Алармы</h1>
          <span className="font-mono text-[12px] text-faint">поддержка проверки</span>
          <a href="/pulse" className="text-[13px] text-vena underline-offset-4 hover:underline">
            К пульсу →
          </a>
          <a href="/effect" className="text-[13px] text-vena underline-offset-4 hover:underline">
            Эффект →
          </a>
        </div>
        <Segmented label="Вид алармов" options={VIEWS} value={view} onChange={setView} />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {query.isPending ? (
          <p className="px-6 py-6 text-[13px] text-muted-foreground">Загрузка…</p>
        ) : query.isError ? (
          <div className="p-6">
            <StateMessage title="Данные недоступны" description="Бэкенд не ответил или снимок прогнозов недоступен." />
          </div>
        ) : view === "alarms" ? (
          <AlarmsTable alarms={alarms.data ?? []} />
        ) : (
          <>
            <RoutesTable routes={routes.data ?? []} />
            <AccessTable events={access.data ?? []} />
          </>
        )}
      </div>
    </div>
  )
}
