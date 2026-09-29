"use client"

import { SEASONALITY_LABEL, useSeasonality } from "@/entities/analytics"
import { cn } from "@/shared/lib/utils"

import { cellShade, seasonalIndex } from "../model/seasonality"

const MONTHS = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]

export function SeasonalityPanel() {
  const seasonality = useSeasonality()
  if (seasonality.isError || (!seasonality.isPending && !seasonality.data?.rows.length)) return null

  const weather = seasonality.data?.weather ?? {}
  const rainCorrelation = weather["precipitation_lag0d"]

  return (
    <section aria-label="Сезонность" className="mx-6 mb-6 border border-border bg-elevated">
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-border-soft px-5 py-3">
        <div>
          <h2 className="text-[11px] tracking-[0.08em] uppercase">Сезонность</h2>
          <p className="mt-1 text-[12px] text-muted-foreground">
            Частота начала эпизодов по месяцам относительно среднего месяца сценария, 2019–2025. 1.0× — обычный месяц.
          </p>
        </div>
        {rainCorrelation !== undefined ? (
          <p className="text-[12px] text-muted-foreground">
            Связь затоплений с осадками: <span className="font-mono tabular-nums">r = {rainCorrelation.toFixed(2)}</span>
          </p>
        ) : null}
      </div>
      {seasonality.isPending ? (
        <p className="px-5 py-4 text-[13px] text-muted-foreground">Загрузка…</p>
      ) : (
        <div className="overflow-x-auto px-5 py-4">
          <table className="w-full min-w-[720px] border-separate border-spacing-[2px] text-[12px]">
            <thead>
              <tr>
                <th className="w-48 pr-3 text-left font-medium text-faint" scope="col">
                  Сценарий
                </th>
                {MONTHS.map((month) => (
                  <th key={month} scope="col" className="text-center font-medium text-faint">
                    {month}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {seasonality.data?.rows.map((row) => {
                const label = SEASONALITY_LABEL[row.scenario] ?? row.scenario
                return (
                  <tr key={row.scenario}>
                    <th scope="row" className="pr-3 text-left font-normal text-foreground">
                      {label}
                    </th>
                    {seasonalIndex(row).map((index, month) => {
                      const shade = cellShade(index)
                      return (
                        <td
                          key={month}
                          title={`${label}, ${MONTHS[month]}: ${index.toFixed(2)}× среднего, ${row.months[month].toFixed(2)} на 100 каналов в месяц`}
                          className={cn(
                            "h-8 rounded-[4px] text-center font-mono tabular-nums",
                            shade > 50 ? "text-elevated" : "text-foreground"
                          )}
                          style={{ backgroundColor: `color-mix(in oklab, var(--vena) ${shade}%, var(--elevated))` }}
                        >
                          {index.toFixed(1)}
                        </td>
                      )
                    })}
                  </tr>
                )
              })}
            </tbody>
          </table>
          <div className="mt-3 flex items-center gap-2 text-[11px] text-muted-foreground" aria-hidden>
            <span>реже</span>
            {[0.5, 0.75, 1, 1.25, 1.5].map((index) => (
              <span
                key={index}
                className="h-3 w-6 rounded-[3px]"
                style={{ backgroundColor: `color-mix(in oklab, var(--vena) ${cellShade(index)}%, var(--elevated))` }}
              />
            ))}
            <span>чаще среднего</span>
          </div>
        </div>
      )}
    </section>
  )
}
