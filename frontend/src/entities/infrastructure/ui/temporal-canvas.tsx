"use client"

import * as React from "react"

import { useElementSize } from "@/shared/lib/hooks/use-element-size"
import { linePath, type Point } from "@/shared/lib/svg"
import { HOUR, formatDateTime } from "@/shared/lib/time"
import { cn } from "@/shared/lib/utils"

import { RISK_HIGH, RISK_MEDIUM } from "../lib/risk"
import type { RiskSnapshot, SensorEvent, StateSegment, TemporalBundle } from "../model/types"
import { GlyphShape, glyphKind } from "./event-glyph"

export type Layers = { state: boolean; events: boolean; alarms: boolean; failures: boolean; risk: boolean }

export const DEFAULT_LAYERS: Layers = { state: true, events: true, alarms: true, failures: true, risk: true }
export const ZOOM_STEPS = [12, 24, 48, 72]

const LEFT = 92
const RIGHT = 18
const HEADER = 20
const AXIS = 30
const ROW_GAP = 6

type Tooltip = { x: number; y: number; time: number; lines: string[] }

function clamp(value: number, low: number, high: number) {
  return Math.min(high, Math.max(low, value))
}

function nearest<T>(items: T[], time: number, key: (item: T) => number) {
  let best: T | null = null
  let distance = Infinity
  for (const item of items) {
    const gap = Math.abs(key(item) - time)
    if (gap < distance) {
      distance = gap
      best = item
    }
  }
  return best
}

export function TemporalCanvas({
  now,
  halfSpanHours,
  bundles,
  layers,
  onZoom,
  onSelectAsset,
  selectedAssetId,
}: {
  now: number
  halfSpanHours: number
  bundles: TemporalBundle[]
  layers: Layers
  onZoom?: (halfSpanHours: number) => void
  onSelectAsset?: (id: string) => void
  selectedAssetId?: string | null
}) {
  const [ref, size] = useElementSize<HTMLDivElement>()
  const [tooltip, setTooltip] = React.useState<Tooltip | null>(null)
  const width = Math.max(size.width, 360)
  const compact = bundles.length > 1
  const plotWidth = width - LEFT - RIGHT
  const centerX = LEFT + plotWidth / 2
  const span = halfSpanHours * HOUR
  const x = (time: number) => centerX + ((time - now) / span) * (plotWidth / 2)

  const tracks = React.useMemo(() => {
    const list: { key: keyof Layers; label: string; height: number }[] = []
    if (layers.state) list.push({ key: "state", label: "State", height: compact ? 16 : 24 })
    if (layers.events) list.push({ key: "events", label: "Events", height: compact ? 22 : 32 })
    if (layers.alarms && !compact) list.push({ key: "alarms", label: "Alarms", height: 26 })
    if (layers.failures && !compact) list.push({ key: "failures", label: "Failures", height: 26 })
    if (layers.risk) list.push({ key: "risk", label: "Risk", height: compact ? 56 : clamp(size.height - HEADER - AXIS - 170, 110, 300) })
    return list
  }, [layers, compact, size.height])

  const blockHeight = tracks.reduce((sum, track) => sum + track.height + ROW_GAP, 0) + HEADER
  const totalHeight = Math.max(size.height, HEADER + bundles.length * blockHeight + AXIS)

  React.useEffect(() => {
    const element = ref.current
    if (!element || !onZoom) return
    function onWheel(event: WheelEvent) {
      if (!event.ctrlKey && !event.metaKey) return
      event.preventDefault()
      const index = ZOOM_STEPS.indexOf(halfSpanHours)
      const next = clamp(index + (event.deltaY > 0 ? 1 : -1), 0, ZOOM_STEPS.length - 1)
      if (next !== index) onZoom!(ZOOM_STEPS[next])
    }
    element.addEventListener("wheel", onWheel, { passive: false })
    return () => element.removeEventListener("wheel", onWheel)
  }, [ref, onZoom, halfSpanHours])

  const tickEvery = halfSpanHours <= 12 ? 3 : halfSpanHours <= 24 ? 6 : 12
  const ticks: number[] = []
  for (let offset = -Math.floor(halfSpanHours / tickEvery) * tickEvery; offset <= halfSpanHours; offset += tickEvery) ticks.push(offset)

  const bottom = HEADER + bundles.length * blockHeight
  const future = { left: centerX, width: width - RIGHT - centerX }

  function onMove(event: React.PointerEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect()
    const px = event.clientX - rect.left
    const py = event.clientY - rect.top
    if (px < LEFT || px > width - RIGHT) return setTooltip(null)
    const time = now + ((px - centerX) / (plotWidth / 2)) * span
    const blockIndex = clamp(Math.floor((py - HEADER) / blockHeight), 0, bundles.length - 1)
    const bundle = bundles[blockIndex]
    if (!bundle) return setTooltip(null)
    const lines = [`${formatDateTime(time)}`]
    if (time <= now) {
      const point = nearest(bundle.history, time, (item) => item.timestamp)
      if (point) lines.push(`${bundle.asset.id} · risk ${Math.round(point.score)}/100`)
      const segment = bundle.states.find((item) => item.from <= time && item.to >= time)
      if (segment) lines.push(`State: ${segment.label}`)
    } else {
      const point = nearest(bundle.forecast, time, (item) => item.timestamp)
      if (point) lines.push(`${bundle.asset.id} · expected risk ${Math.round(point.low)}–${Math.round(point.high)}`)
    }
    setTooltip({ x: px, y: py, time, lines })
  }

  return (
    <div ref={ref} className="relative size-full min-h-[280px] overflow-y-auto overflow-x-hidden">
      <svg
        width={width}
        height={totalHeight}
        role="img"
        aria-label="Timeline: history on the left of NOW, forecast on the right"
        className="block select-none"
        onPointerMove={onMove}
        onPointerLeave={() => setTooltip(null)}
      >
        <defs>
          <pattern id="forecast-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="6" className="stroke-vena" strokeWidth="1" />
          </pattern>
          <pattern id="forecast-band" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)">
            <line x1="0" y1="0" x2="0" y2="4" className="stroke-vena" strokeWidth="1" opacity="0.5" />
          </pattern>
          <pattern id="offline-hatch" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="5" className="stroke-status-offline" strokeWidth="1.2" />
          </pattern>
        </defs>

        <rect x={future.left} y={HEADER - 4} width={future.width} height={bundles.length * blockHeight} className="fill-vena/[0.06]" />
        <text x={LEFT + 6} y={12} className="fill-faint text-[11px] font-medium uppercase tracking-[0.1em]">
          Past
        </text>
        <text x={width - RIGHT - 6} y={12} textAnchor="end" className="fill-faint text-[11px] font-medium uppercase tracking-[0.1em]">
          Future · forecast
        </text>

        {ticks.map((offset) => (
          <g key={offset}>
            <line x1={x(now + offset * HOUR)} x2={x(now + offset * HOUR)} y1={HEADER - 4} y2={bottom} className="stroke-grid" strokeWidth={1} strokeDasharray="1 3" />
            <text x={x(now + offset * HOUR)} y={bottom + 16} textAnchor="middle" className="fill-faint font-mono text-[11px] tabular-nums">
              {offset === 0 ? "" : offset > 0 ? `+${offset}h` : `${offset}h`}
            </text>
          </g>
        ))}

        {bundles.map((bundle, index) => {
          const top = HEADER + index * blockHeight
          let cursor = top + 14
          const selected = bundle.asset.id === selectedAssetId
          return (
            <g key={bundle.asset.id}>
              <g
                role={onSelectAsset ? "button" : undefined}
                tabIndex={onSelectAsset ? 0 : undefined}
                className={cn(onSelectAsset && "cursor-pointer outline-none [&:focus-visible>text]:fill-vena")}
                onClick={() => onSelectAsset?.(bundle.asset.id)}
                onKeyDown={(event) => {
                  if (onSelectAsset && (event.key === "Enter" || event.key === " ")) {
                    event.preventDefault()
                    onSelectAsset(bundle.asset.id)
                  }
                }}
              >
                <text x={10} y={top + 4} className={cn("font-mono text-[13px] tabular-nums", selected ? "fill-vena" : "fill-foreground")}>
                  {bundle.asset.id}
                </text>
              </g>
              {tracks.map((track) => {
                const y = cursor
                cursor += track.height + ROW_GAP
                return (
                  <g key={track.key}>
                    <text x={LEFT - 10} y={y + Math.min(track.height, 16) / 2 + 3} textAnchor="end" className="fill-muted-foreground text-[11px] font-medium uppercase tracking-[0.08em]">
                      {track.label}
                    </text>
                    <line x1={LEFT} x2={width - RIGHT} y1={y + track.height} y2={y + track.height} className="stroke-border" strokeWidth={1} />
                    {track.key === "state" ? <StateTrack segments={bundle.states} x={x} y={y} height={track.height} now={now} /> : null}
                    {track.key === "events" ? <EventTrack events={bundle.events} x={x} y={y} height={track.height} compact={compact} now={now} /> : null}
                    {track.key === "alarms" ? <MarkerTrack events={bundle.events.filter((event) => event.type === "alarm" || event.type === "signal")} x={x} y={y} height={track.height} now={now} /> : null}
                    {track.key === "failures" ? <FailureTrack events={bundle.events.filter((event) => event.type === "failure")} x={x} y={y} height={track.height} now={now} /> : null}
                    {track.key === "risk" ? <RiskTrack history={bundle.history} forecast={bundle.forecast} x={x} y={y} height={track.height} now={now} /> : null}
                  </g>
                )
              })}
            </g>
          )
        })}

        <line x1={centerX} x2={centerX} y1={HEADER - 8} y2={bottom + 4} className="stroke-foreground" strokeWidth={1.6} />
        <rect x={centerX - 24} y={bottom + 5} width={48} height={17} rx={2} className="fill-foreground" />
        <text x={centerX} y={bottom + 17} textAnchor="middle" className="fill-background text-[10px] font-semibold uppercase tracking-[0.14em]">
          Now
        </text>
        {tooltip ? <line x1={tooltip.x} x2={tooltip.x} y1={HEADER - 4} y2={bottom} className="stroke-muted-foreground/60" strokeWidth={1} strokeDasharray="2 3" /> : null}
      </svg>
      {tooltip ? (
        <div
          role="tooltip"
          className="pointer-events-none absolute z-10 rounded-md border bg-popover px-2.5 py-1.5 font-mono text-[11px] leading-5 shadow-md"
          style={{ left: clamp(tooltip.x + 12, 4, width - 200), top: clamp(tooltip.y + 10, 4, totalHeight - 70) }}
        >
          {tooltip.lines.map((line, index) => (
            <p key={line} className={index === 0 ? "text-muted-foreground tabular-nums" : "tabular-nums"}>
              {line}
            </p>
          ))}
        </div>
      ) : null}
    </div>
  )
}

type TrackProps = { x: (time: number) => number; y: number; height: number; now: number }

function StateTrack({ segments, x, y, height, now }: TrackProps & { segments: StateSegment[] }) {
  const barHeight = Math.min(10, height - 6)
  const barY = y + (height - barHeight) / 2
  return (
    <>
      {segments.map((segment) => {
        const from = x(segment.from)
        const to = x(Math.min(segment.to, now))
        const barWidth = Math.max(1, to - from)
        return (
          <g key={`${segment.from}-${segment.state}`}>
            <rect
              x={from}
              y={barY}
              width={barWidth}
              height={barHeight}
              className={cn(
                segment.state === "normal" && "fill-status-normal/35",
                segment.state === "abnormal" && "fill-status-critical/75",
                segment.state === "offline" && "fill-status-offline/20"
              )}
              fill={segment.state === "offline" ? "url(#offline-hatch)" : undefined}
            />
            {barWidth > 70 && height > 20 ? (
              <text x={from + 5} y={barY + barHeight - 2} className="fill-foreground/80 font-mono text-[9px]">
                {segment.label}
              </text>
            ) : null}
          </g>
        )
      })}
    </>
  )
}

function EventTrack({ events, x, y, height, compact, now }: TrackProps & { events: SensorEvent[]; compact: boolean }) {
  const center = y + height / 2
  return (
    <>
      {events
        .filter((event) => event.timestamp <= now && event.type !== "alarm" && event.type !== "failure" && event.type !== "signal")
        .map((event) => {
          return <GlyphShape key={event.id} kind={glyphKind(event)} x={x(event.timestamp)} y={center} size={glyphKind(event) === "event" ? 6 : 8} />
        })}
      {compact
        ? events
            .filter((event) => event.timestamp <= now && (event.type === "alarm" || event.type === "signal" || event.type === "failure"))
            .map((event) => <Marker key={event.id} event={event} cx={x(event.timestamp)} cy={center} />)
        : null}
    </>
  )
}

function Marker({ event, cx, cy }: { event: SensorEvent; cx: number; cy: number }) {
  if (event.type === "failure") {
    return (
      <g className="stroke-status-critical" strokeWidth={1.6} strokeLinecap="round">
        <line x1={cx - 3.5} y1={cy - 3.5} x2={cx + 3.5} y2={cy + 3.5} />
        <line x1={cx - 3.5} y1={cy + 3.5} x2={cx + 3.5} y2={cy - 3.5} />
      </g>
    )
  }
  if (event.type === "signal") {
    return <path d={`M${cx} ${cy - 4.5} L${cx + 4.2} ${cy + 3.2} L${cx - 4.2} ${cy + 3.2} Z`} className={event.severity === "critical" ? "fill-vena" : "fill-vena/40 stroke-vena"} strokeWidth={1} />
  }
  return <path d={`M${cx} ${cy - 4.2} L${cx + 4.2} ${cy} L${cx} ${cy + 4.2} L${cx - 4.2} ${cy} Z`} className={event.severity === "critical" ? "fill-status-critical" : "fill-status-attention"} />
}

function MarkerTrack({ events, x, y, height, now }: TrackProps & { events: SensorEvent[] }) {
  return (
    <>
      {events
        .filter((event) => event.timestamp <= now)
        .map((event) => (
          <Marker key={event.id} event={event} cx={x(event.timestamp)} cy={y + height / 2} />
        ))}
    </>
  )
}

function FailureTrack({ events, x, y, height, now }: TrackProps & { events: SensorEvent[] }) {
  return <MarkerTrack events={events} x={x} y={y} height={height} now={now} />
}

function RiskTrack({
  history,
  forecast,
  x,
  y,
  height,
  now,
}: TrackProps & { history: RiskSnapshot[]; forecast: { timestamp: number; low: number; mid: number; high: number }[] }) {
  const values = [...history.map((point) => point.score), ...forecast.flatMap((point) => [point.low, point.high])]
  const low = values.length > 0 ? Math.min(...values) : 0
  const high = values.length > 0 ? Math.max(...values) : 100
  const domainLow = clamp(Math.floor((low - 6) / 10) * 10, 0, 80)
  const domainHigh = clamp(Math.ceil((high + 6) / 10) * 10, domainLow + 20, 100)
  const scale = (score: number) =>
    y + height - 4 - ((clamp(score, domainLow, domainHigh) - domainLow) / (domainHigh - domainLow)) * (height - 8)
  const past = history.filter((point) => point.timestamp <= now).map<Point>((point) => ({ x: x(point.timestamp), y: scale(point.score) }))
  const last = history.filter((point) => point.timestamp <= now).at(-1)
  if (past.length > 0 && last && last.timestamp < now) past.push({ x: x(now), y: scale(last.score) })
  const band = forecast.filter((point) => point.timestamp >= now)
  const upper = band.map<Point>((point) => ({ x: x(point.timestamp), y: scale(point.high) }))
  const lower = band.map<Point>((point) => ({ x: x(point.timestamp), y: scale(point.low) })).reverse()
  const mid = band.map<Point>((point) => ({ x: x(point.timestamp), y: scale(point.mid) }))
  const pastRuns: { className: string; points: Point[] }[] = []
  const observed = history.filter((point) => point.timestamp <= now)
  for (let index = 0; index < observed.length - 1; index += 1) {
    const score = (observed[index].score + observed[index + 1].score) / 2
    const className = score >= RISK_HIGH ? "stroke-status-critical" : score >= RISK_MEDIUM ? "stroke-status-attention" : "stroke-foreground/80"
    const segment = [{ x: x(observed[index].timestamp), y: scale(observed[index].score) }, { x: x(observed[index + 1].timestamp), y: scale(observed[index + 1].score) }]
    const tail = pastRuns.at(-1)
    if (tail && tail.className === className) tail.points.push(segment[1])
    else pastRuns.push({ className, points: segment })
  }
  const current = last?.score ?? 0
  const currentStatus = current >= RISK_HIGH ? "fill-status-critical" : current >= RISK_MEDIUM ? "fill-status-attention" : "fill-status-normal"

  return (
    <>
      {[RISK_MEDIUM, RISK_HIGH]
        .filter((level) => level > domainLow && level < domainHigh)
        .map((level) => (
          <g key={level}>
            <line x1={x(now) - 4000} x2={x(now) + 4000} y1={scale(level)} y2={scale(level)} className="stroke-grid" strokeWidth={1} strokeDasharray="2 4" />
            <text x={86} y={scale(level) + 3} textAnchor="end" className="fill-faint font-mono text-[10px] tabular-nums">
              {level}
            </text>
          </g>
        ))}
      {past.length > 1 ? (
        <>
          {pastRuns.map((run, index) => (
            <path key={index} d={linePath(run.points)} fill="none" className={run.className} strokeWidth={1.6} strokeLinejoin="round" />
          ))}
        </>
      ) : null}
      {upper.length > 1 ? (
        <>
          <path d={`${linePath([...upper, ...lower])} Z`} fill="url(#forecast-band)" className="stroke-vena" strokeWidth={1} strokeOpacity={0.55} />
          <path d={linePath(mid)} fill="none" className="stroke-vena" strokeWidth={1.3} strokeDasharray="5 4" />
        </>
      ) : null}
      {last ? (
        <>
          <path d={`M${x(now)} ${scale(current) - 5} l5 5 -5 5 -5 -5Z`} className={currentStatus} />
          <text x={x(now) - 8} y={scale(current) - 7} textAnchor="end" className="fill-foreground font-mono text-[11px] tabular-nums">
            {Math.round(current)}
          </text>
        </>
      ) : null}
    </>
  )
}
