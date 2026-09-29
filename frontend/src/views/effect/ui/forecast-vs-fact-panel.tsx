"use client"

import * as React from "react"

import { useEventTypes, type EventTypeStats } from "@/entities/analytics"
import { cn } from "@/shared/lib/utils"
import { LoadingBar, StateMessage } from "@/shared/ui/state-message"

function DualSeriesChart({
  title,
  backtest,
  forecast,
}: {
  title: string
  backtest: EventTypeStats["backtest"]
  forecast: EventTypeStats["forecast"]
}) {
  const points = React.useMemo(() => {
    const actual = backtest.map((row) => ({ day: row.day, actual: row.actual, forecast: row.forecast }))
    const future = forecast.map((row) => ({ day: row.day, actual: null as number | null, forecast: row.expected }))
    return [...actual, ...future]
  }, [backtest, forecast])

  if (points.length === 0) {
    return <p className="px-4 py-6 text-[13px] text-muted-foreground">Нет ряда «прогноз / факт» для этого типа.</p>
  }

  const values = points.flatMap((point) => [point.actual ?? 0, point.forecast])
  const max = Math.max(1, ...values)
  const height = 120
  const width = Math.max(320, points.length * 4)
  const step = width / Math.max(1, points.length - 1)

  const forecastPath = points
    .map((point, index) => {
      const x = index * step
      const y = height - (point.forecast / max) * (height - 8) - 4
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(" ")

  const actualSegments: string[] = []
  let segment = ""
  points.forEach((point, index) => {
    if (point.actual === null) {
      if (segment) {
        actualSegments.push(segment)
        segment = ""
      }
      return
    }
    const x = index * step
    const y = height - (point.actual / max) * (height - 8) - 4
    segment += `${segment ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)} `
  })
  if (segment) actualSegments.push(segment)

  const sample = points.filter((_, index) => index % Math.max(1, Math.floor(points.length / 6)) === 0 || index === points.length - 1)

  return (
    <div className="px-4 py-3">
      <p className="text-[13px] font-medium">{title}</p>
      <div className="mt-3 overflow-x-auto">
        <svg width={width} height={height + 24} viewBox={`0 0 ${width} ${height + 24}`} role="img" aria-label={`${title}: прогноз против факта`}>
          <path d={forecastPath} fill="none" stroke="currentColor" className="text-vena" strokeWidth="1.5" />
          {actualSegments.map((d) => (
            <path key={d} d={d.trim()} fill="none" stroke="currentColor" className="text-foreground" strokeWidth="1.5" />
          ))}
          {sample.map((point) => {
            const index = points.indexOf(point)
            return (
              <text
                key={point.day}
                x={index * step}
                y={height + 16}
                textAnchor="middle"
                className="fill-muted-foreground font-mono text-[9px]"
              >
                {point.day.slice(5)}
              </text>
            )
          })}
        </svg>
      </div>
      <p className="mt-1 flex flex-wrap gap-x-4 text-[11px] text-muted-foreground">
        <span>
          <span className="mr-1 inline-block size-2 bg-foreground align-middle" /> факт (янв–июнь 2026)
        </span>
        <span>
          <span className="mr-1 inline-block size-2 bg-vena align-middle" /> прогноз (+14 дн.)
        </span>
      </p>
    </div>
  )
}

export function ForecastVsFactPanel({ className }: { className?: string }) {
  const eventTypes = useEventTypes()
  const withSeries = (eventTypes.data ?? []).filter((item) => item.backtest.length > 0 || item.forecast.length > 0)
  const [selected, setSelected] = React.useState<string>("")

  const current = withSeries.find((item) => item.eventType === selected) ?? withSeries[0]

  if (eventTypes.isPending) return <LoadingBar className={cn("min-h-40", className)} />
  if (eventTypes.isError) {
    return (
      <StateMessage
        className={className}
        title="Прогноз против факта недоступен"
        description="Не удалось загрузить /analytics/event-types."
      />
    )
  }
  if (withSeries.length === 0) {
    return (
      <p className={cn("px-4 py-6 text-[13px] text-muted-foreground", className)}>
        Ряды backtest/forecast ещё не посчитаны для типов инцидентов.
      </p>
    )
  }

  return (
    <section className={cn("border border-border bg-elevated", className)}>
      <div className="border-b border-border-soft px-4 py-3">
        <h2 className="text-[12px] font-medium tracking-[0.12em] uppercase">Прогноз против факта</h2>
        <p className="mt-1 text-[12px] text-muted-foreground">
          Критерий жюри: прогноз на следующий день vs сколько случилось (янв–июнь 2026) и прогноз на 14 дней.
        </p>
      </div>
      <div className="border-b border-border-soft px-4 py-2">
        <label className="flex flex-wrap items-center gap-2 text-[12px] text-muted-foreground">
          Тип инцидента
          <select
            className="h-8 min-w-[16rem] border border-border bg-surface px-2 text-[13px] text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring/60"
            value={current?.eventType ?? selected}
            onChange={(event) => setSelected(event.target.value)}
          >
            {withSeries.map((item) => (
              <option key={item.eventType} value={item.eventType}>
                {item.title}
              </option>
            ))}
          </select>
        </label>
      </div>
      {current ? (
        <>
          <DualSeriesChart title={current.title} backtest={current.backtest} forecast={current.forecast} />
          <div className="grid gap-3 border-t border-border-soft px-4 py-3 sm:grid-cols-3">
            <div>
              <p className="text-[11px] tracking-[0.08em] text-faint uppercase">След. 7 дней</p>
              <p className="mt-1 font-mono text-[18px] tabular-nums">
                {current.next7Days ? current.next7Days.expected.toFixed(1) : "—"}
              </p>
              {current.next7Days?.low != null && current.next7Days.high != null ? (
                <p className="text-[12px] text-muted-foreground">
                  коридор {current.next7Days.low.toFixed(1)}–{current.next7Days.high.toFixed(1)}
                </p>
              ) : null}
            </div>
            <div>
              <p className="text-[11px] tracking-[0.08em] text-faint uppercase">Ошибка недели</p>
              <p className="mt-1 font-mono text-[18px] tabular-nums">
                {current.weekError === null ? "—" : current.weekError.toFixed(2)}
              </p>
              {current.weekErrorBaseline !== null ? (
                <p className="text-[12px] text-muted-foreground">база {current.weekErrorBaseline.toFixed(2)}</p>
              ) : null}
            </div>
            <div>
              <p className="text-[11px] tracking-[0.08em] text-faint uppercase">Эпизоды</p>
              <p className="mt-1 font-mono text-[18px] tabular-nums">
                {current.episodes30d ?? "—"}
                <span className="ml-1 text-[12px] text-muted-foreground">/ 30д</span>
              </p>
              <p className="text-[12px] text-muted-foreground">{current.episodes365d ?? "—"} / год</p>
            </div>
          </div>
        </>
      ) : null}
    </section>
  )
}
