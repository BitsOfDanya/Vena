"use client"

import { useQuery } from "@tanstack/react-query"
import * as React from "react"

import { useAssetTree, useSectionHealthHistory, type ObjectNode } from "@/entities/analytics"
import { apiFetch } from "@/shared/api/http"
import { useElementSize } from "@/shared/lib/hooks/use-element-size"
import { formatDateTime } from "@/shared/lib/time"
import { cn } from "@/shared/lib/utils"
import { LoadingBar } from "@/shared/ui/state-message"

type EventFeed = {
  latest_at: string | null
  from: string | null
  has_more: boolean
  items: { event_id: string; ts: string; value: string; alarm: boolean }[]
}

const HOURS = 72
const MONTHS = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]

function Panel({ title, note, children }: { title: string; note: string; children: React.ReactNode }) {
  return (
    <section className="border border-border bg-elevated">
      <header className="flex flex-wrap items-baseline justify-between gap-2 border-b border-border px-4 py-2.5">
        <h2 className="text-[14.5px] font-semibold">{title}</h2>
        <span className="text-[12px] text-muted-foreground">{note}</span>
      </header>
      {children}
    </section>
  )
}

function HealthChart({ points }: { points: { day: string; value: number }[] }) {
  const [ref, size] = useElementSize<HTMLDivElement>()
  const [hover, setHover] = React.useState<number | null>(null)
  const width = Math.max(size.width, 320)
  const height = 220
  const left = 36
  const right = 12
  const top = 12
  const bottom = 26
  const plotW = width - left - right
  const plotH = height - top - bottom
  const x = (index: number) => left + (points.length > 1 ? (index / (points.length - 1)) * plotW : plotW / 2)
  const y = (value: number) => top + (1 - value / 100) * plotH
  const path = points.map((point, index) => `${index ? "L" : "M"}${x(index).toFixed(1)},${y(point.value).toFixed(1)}`).join(" ")
  const smooth = points.map((_, index) => {
    const window = points.slice(Math.max(0, index - 6), index + 1)
    return window.reduce((total, point) => total + point.value, 0) / window.length
  })
  const trend = smooth.map((value, index) => `${index ? "L" : "M"}${x(index).toFixed(1)},${y(value).toFixed(1)}`).join(" ")
  const months = points
    .map((point, index) => ({ index, month: Number(point.day.slice(5, 7)), day: Number(point.day.slice(8, 10)) }))
    .filter((item) => item.day === 1)
  const active = hover === null ? points.length - 1 : hover
  const current = points[active]

  return (
    <div ref={ref} className="relative">
      <svg
        width={width}
        height={height}
        className="block"
        onMouseMove={(event) => {
          const box = event.currentTarget.getBoundingClientRect()
          const ratio = (event.clientX - box.left - left) / plotW
          setHover(Math.max(0, Math.min(points.length - 1, Math.round(ratio * (points.length - 1)))))
        }}
        onMouseLeave={() => setHover(null)}
      >
        <rect x={left} y={y(40)} width={plotW} height={y(0) - y(40)} fill="var(--status-critical)" fillOpacity="0.07" />
        <rect x={left} y={y(70)} width={plotW} height={y(40) - y(70)} fill="var(--status-attention)" fillOpacity="0.07" />
        {[0, 40, 70, 100].map((value) => (
          <g key={value}>
            <line x1={left} x2={left + plotW} y1={y(value)} y2={y(value)} stroke="var(--grid)" />
            <text x={left - 6} y={y(value) + 3.5} textAnchor="end" fontSize="10.5" fill="var(--muted-foreground)" fontFamily="var(--font-plex-mono)">
              {value}
            </text>
          </g>
        ))}
        {months.map((item) => (
          <g key={item.index}>
            <line x1={x(item.index)} x2={x(item.index)} y1={top} y2={top + plotH} stroke="var(--grid)" />
            <text x={x(item.index) + 3} y={height - 8} fontSize="10.5" fill="var(--muted-foreground)" fontFamily="var(--font-plex-mono)">
              {MONTHS[item.month - 1]}
            </text>
          </g>
        ))}
        <path d={path} fill="none" stroke="var(--vena)" strokeOpacity="0.35" strokeWidth="1" />
        <path d={trend} fill="none" stroke="var(--vena)" strokeWidth="2.2" />
        {current ? (
          <g>
            <line x1={x(active)} x2={x(active)} y1={top} y2={top + plotH} stroke="var(--foreground)" strokeOpacity="0.35" strokeDasharray="3 3" />
            <rect x={x(active) - 3.5} y={y(current.value) - 3.5} width="7" height="7" fill="var(--vena)" />
          </g>
        ) : null}
      </svg>
      {current ? (
        <p className="absolute top-2 right-3 border border-border bg-elevated px-2 py-1 font-mono text-[12px]">
          {current.day.split("-").reverse().join(".")} ·{" "}
          <span className={cn(current.value < 40 ? "text-status-critical" : current.value < 70 ? "text-status-attention" : "text-status-normal")}>
            {current.value}
          </span>{" "}
          · 7 дн. {Math.round(smooth[active] ?? current.value)}
        </p>
      ) : null}
    </div>
  )
}

function EventStrip({ feed }: { feed: EventFeed }) {
  const [ref, size] = useElementSize<HTMLDivElement>()
  const width = Math.max(size.width, 320)
  const end = feed.latest_at ? Date.parse(feed.latest_at) : Math.max(...feed.items.map((event) => Date.parse(event.ts)))
  const start = end - HOURS * 3_600_000
  const left = 12
  const plotW = width - left * 2
  const x = (ts: number) => left + ((ts - start) / (end - start)) * plotW
  const days = Array.from({ length: HOURS / 24 + 1 }, (_, index) => start + index * 86_400_000)
  return (
    <div ref={ref}>
      <svg width={width} height={70} className="block">
        <line x1={left} x2={left + plotW} y1={34} y2={34} stroke="var(--border)" />
        {days.map((day) => (
          <g key={day}>
            <line x1={x(day)} x2={x(day)} y1={14} y2={54} stroke="var(--grid)" />
            <text x={x(day) + 3} y={66} fontSize="10.5" fill="var(--muted-foreground)" fontFamily="var(--font-plex-mono)">
              {formatDateTime(day)}
            </text>
          </g>
        ))}
        {feed.items.map((event) => {
          const px = x(Date.parse(event.ts))
          return (
            <rect
              key={event.event_id}
              x={px - 1.5}
              y={event.alarm ? 18 : 26}
              width={3}
              height={event.alarm ? 32 : 16}
              fill={event.alarm ? "var(--status-critical)" : "var(--status-attention)"}
            />
          )
        })}
      </svg>
    </div>
  )
}

function findSection(objects: ObjectNode[], assetId: string) {
  for (const object of objects) {
    for (const section of object.sections) {
      if (section.channels.some((channel) => channel.assetId === assetId)) return { object, section }
    }
  }
  return null
}

export function ChannelHistory({ assetId }: { assetId: string }) {
  const tree = useAssetTree()
  const section = findSection(tree.data ?? [], assetId)
  const history = useSectionHealthHistory(section?.section.group ?? null)
  const events = useQuery({
    queryKey: ["channel-events", assetId],
    queryFn: () => apiFetch<EventFeed>(`/api/v1/events/recent?channel_id=${encodeURIComponent(assetId)}&hours=${HOURS}&limit=300`),
    staleTime: 120_000,
  })

  return (
    <div className="grid gap-4 py-3 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <Panel
        title="Индекс здоровья участка по дням"
        note={section ? `${section.section.label ?? section.section.group} · январь–июнь 2026` : "участок не найден в реестре"}
      >
        {history.isPending && section ? (
          <LoadingBar className="min-h-40" />
        ) : (history.data?.length ?? 0) < 2 ? (
          <p className="px-4 py-6 text-[13px] text-muted-foreground">Истории индекса для этого участка нет.</p>
        ) : (
          <div className="px-2 py-2">
            <HealthChart points={history.data ?? []} />
            <p className="px-2 pb-1 text-[12px] text-muted-foreground">
              Тонкая линия — индекс за сутки, жирная — среднее за 7 дней. Ниже 40 — критично, 40–70 — внимание.
            </p>
          </div>
        )}
      </Panel>
      <Panel title="События канала в журнале" note={`тревоги и смены состояния за ${HOURS} ч`}>
        {events.isPending ? (
          <LoadingBar className="min-h-24" />
        ) : events.isError || !events.data ? (
          <p className="px-4 py-6 text-[13px] text-muted-foreground">Журнал событий недоступен.</p>
        ) : events.data.items.length === 0 ? (
          <p className="px-4 py-6 text-[13px] text-muted-foreground">
            За последние {HOURS} ч журнала у канала не было тревог и смен состояния.
          </p>
        ) : (
          <>
            <div className="px-2 pt-2">
              <EventStrip feed={events.data} />
            </div>
            <ul className="max-h-60 divide-y divide-border overflow-y-auto border-t border-border">
              {events.data.items.slice(0, 40).map((event) => (
                <li key={event.event_id} className="flex items-baseline gap-3 px-4 py-1.5 text-[13px]">
                  <span className="font-mono text-[12px] whitespace-nowrap text-muted-foreground">{formatDateTime(Date.parse(event.ts))}</span>
                  <span className={event.alarm ? "text-status-critical" : "text-status-attention"}>{event.value}</span>
                  {event.alarm ? <span className="ml-auto font-mono text-[11px] text-status-critical">ТРЕВОГА</span> : null}
                </li>
              ))}
            </ul>
          </>
        )}
      </Panel>
    </div>
  )
}
