"use client"

import { SEASONALITY_LABEL, useSeasonality, useWeatherReport } from "@/entities/analytics"
import { cn } from "@/shared/lib/utils"

import { cellShade, seasonalIndex } from "../model/seasonality"

const MONTHS = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]

const DAY_RU = new Intl.DateTimeFormat("ru-RU", {
  weekday: "short",
  day: "numeric",
  month: "short",
  timeZone: "Europe/Moscow",
})

function formatForecastDay(day: string) {
  const stamp = Date.parse(`${day}T12:00:00Z`)
  if (Number.isNaN(stamp)) return day
  return DAY_RU.format(stamp)
}

function WeatherForecastStrip({ bordered = true, showCorrelation = true }: { bordered?: boolean; showCorrelation?: boolean }) {
  const weather = useWeatherReport()
  if (weather.isPending) {
    return (
      <p className={cn("px-5 py-3 text-[13px] text-muted-foreground", bordered && "border-t border-border-soft")}>
        Прогноз осадков загружается…
      </p>
    )
  }
  if (weather.isError || !weather.data?.forecast.length) return null

  const days = weather.data.forecast.slice(0, 7)
  const maxRain = Math.max(
    1,
    ...days.map((item) => (item.precipitationMm === null ? 0 : item.precipitationMm))
  )
  const rainCorrelation = weather.data.floodingVsWeather["precipitation_lag0d"]

  return (
    <div className={cn("px-5 py-4", bordered && "border-t border-border-soft")}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h3 className="text-[12px] text-muted-foreground">Прогноз осадков · 7 дней</h3>
          <p className="mt-1 text-[12px] text-muted-foreground">
            Для сценария подтопления · источник {weather.data.source}
          </p>
        </div>
        {showCorrelation && rainCorrelation !== undefined ? (
          <p className="text-[12px] text-muted-foreground">
            Связь затоплений с осадками: <span className="font-mono tabular-nums">r = {rainCorrelation.toFixed(2)}</span>
          </p>
        ) : null}
      </div>
      <ul
        className="mt-3 grid gap-2"
        style={{ gridTemplateColumns: `repeat(${Math.max(days.length, 1)}, minmax(0, 1fr))` }}
      >
        {days.map((item) => {
          const rain = item.precipitationMm
          const height = rain === null ? 4 : Math.max(4, Math.round((rain / maxRain) * 40))
          return (
            <li key={item.day} className="min-w-0 text-center">
              <div className="flex h-11 items-end justify-center">
                <div
                  className={cn("w-full max-w-8", rain !== null && rain >= 5 ? "bg-vena" : "bg-vena/40")}
                  style={{ height }}
                  title={
                    rain === null
                      ? `${item.day}: нет данных`
                      : `${item.day}: ${rain.toFixed(1)} мм${item.thaw ? ", оттепель" : ""}`
                  }
                />
              </div>
              <p className="mt-1 truncate font-mono text-[11px] tabular-nums">
                {rain === null ? "—" : rain.toFixed(1)}
              </p>
              <p className="truncate text-[11px] text-faint">{formatForecastDay(item.day)}</p>
              {item.thaw ? <p className="truncate text-[10px] text-status-attention">оттепель</p> : null}
            </li>
          )
        })}
      </ul>
      <p className="mt-2 text-[11px] text-muted-foreground">мм осадков в сутки</p>
    </div>
  )
}

export function SeasonalityPanel() {
  const seasonality = useSeasonality()
  const weather = useWeatherReport()
  const seasonalityEmpty = seasonality.isError || (!seasonality.isPending && !seasonality.data?.rows.length)
  const weatherEmpty = weather.isError || (!weather.isPending && !weather.data?.forecast.length)

  if (seasonalityEmpty && weatherEmpty && !weather.isPending) return null

  if (seasonalityEmpty) {
    return (
      <section aria-label="Погода и сезонность" className="mx-6 mb-6 border border-border bg-elevated">
        <WeatherForecastStrip bordered={false} />
      </section>
    )
  }

  const seasonWeather = seasonality.data?.weather ?? {}
  const rainCorrelation = seasonWeather["precipitation_lag0d"]

  return (
    <section aria-label="Сезонность" className="mx-6 mb-6 border border-border bg-elevated">
      <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-border-soft px-5 py-3">
        <div>
          <h2 className="text-[12px]">Сезонность</h2>
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
      <WeatherForecastStrip showCorrelation={false} />
    </section>
  )
}
