"use client"

import * as React from "react"

import {
  GlyphShape,
  TYPE_LABEL,
  type AssetType,
  type PulseCluster,
  type PulseData,
  type PulseEvent,
  type PulsePattern,
} from "@/entities/infrastructure"
import { useElementSize } from "@/shared/lib/hooks/use-element-size"
import { HOUR, MINUTE, formatClock } from "@/shared/lib/time"
import { cn } from "@/shared/lib/utils"

const LEFT = 104
const RIGHT = 28
const TOP = 26
const AXIS = 26
const LABEL_WIDTH = 230

export const LEGEND = [
  { kind: "event" as const, label: "event" },
  { kind: "transition" as const, label: "state change" },
  { kind: "attention" as const, label: "attention" },
  { kind: "critical" as const, label: "critical" },
  { kind: "sustained" as const, label: "sustained" },
]

export type PulseSelection = { kind: "cluster" | "pattern"; id: string }

type Hover = { cluster: PulseCluster; x: number; y: number }

function clamp(value: number, low: number, high: number) {
  return Math.min(high, Math.max(low, value))
}

export function patternLabel(pattern: PulsePattern) {
  return pattern.number > 0 ? String(pattern.number).padStart(3, "0") : ""
}

export function clusterTitle(cluster: PulseCluster) {
  return `${TYPE_LABEL[cluster.systemType]} system`
}

function thinOut(events: PulseEvent[], toX: (time: number) => number, minGap: number) {
  const kept: PulseEvent[] = []
  let last = -Infinity
  for (const event of events) {
    const position = toX(event.timestamp)
    if (position - last < minGap) continue
    kept.push(event)
    last = position
  }
  return kept
}

export function PulseSurface({
  data,
  selection,
  onSelect,
}: {
  data: PulseData
  selection: PulseSelection | null
  onSelect: (selection: PulseSelection) => void
}) {
  const [ref, size] = useElementSize<HTMLDivElement>()
  const [hover, setHover] = React.useState<Hover | null>(null)
  const width = Math.max(size.width, 360)
  const height = Math.max(size.height, 200)
  const compact = height < 360
  const annotation = data.patterns.length > 0 ? (compact ? 88 : 96) : 14
  const plotWidth = width - LEFT - RIGHT
  const rows = data.lanes.length
  const fixed = TOP + AXIS + annotation
  const rowHeight = clamp((height - fixed) / rows, 22, 96)
  const naturalBottom = TOP + rows * rowHeight
  const lanesBottom = rowHeight >= 96 ? Math.max(naturalBottom, height - annotation - AXIS) : naturalBottom
  const lanesTop = lanesBottom - rows * rowHeight
  const span = data.now - data.from
  const x = (time: number) => LEFT + ((time - data.from) / span) * plotWidth

  const ticks: number[] = []
  const tickEvery = data.windowHours <= 2 ? 15 * MINUTE : data.windowHours <= 8 ? HOUR : data.windowHours <= 26 ? 3 * HOUR : 6 * HOUR
  for (let tick = Math.ceil(data.from / tickEvery) * tickEvery; tick < data.now - tickEvery / 3; tick += tickEvery) ticks.push(tick)

  const laneIndex = new Map<AssetType, number>(data.lanes.map((lane, index) => [lane.type, index]))
  const laneY = (index: number) => lanesTop + index * rowHeight + rowHeight / 2
  const clusterById = new Map(data.clusters.map((cluster) => [cluster.id, cluster]))

  const patterns = data.patterns
    .map((pattern) => {
      const members = pattern.clusterIds
        .map((id) => clusterById.get(id))
        .filter((cluster): cluster is PulseCluster => Boolean(cluster))
        .map((cluster) => ({ cluster, cx: x((cluster.start + cluster.end) / 2), row: laneIndex.get(cluster.systemType) ?? 0 }))
      const spineX = members.reduce((sum, member) => sum + member.cx, 0) / Math.max(1, members.length)
      return { pattern, members, spineX, topRow: Math.min(...members.map((member) => member.row)) }
    })
    .filter((item) => item.members.length > 0)
    .sort((left, right) => left.spineX - right.spineX)

  const labelTop = lanesBottom + AXIS + 6
  const labelHeight = Math.max(30, height - labelTop - 2)
  const showRange = labelHeight >= 74

  const selectedPattern = selection?.kind === "pattern" ? selection.id : null
  const selectedCluster = selection?.kind === "cluster" ? selection.id : null

  return (
    <div ref={ref} className="relative size-full min-h-0 overflow-hidden">
      <svg
        width={width}
        height={height}
        role="img"
        aria-label="Пульс системы: состояние системы и активность событий по насосам, вентиляции, дыму и питанию"
        className="block select-none"
      >
        {ticks.map((tick) => (
          <text key={tick} x={x(tick)} y={lanesBottom + 18} textAnchor="middle" className="fill-faint font-mono text-[11px] tabular-nums">
            {formatClock(tick)}
          </text>
        ))}
        <line x1={LEFT} x2={width - RIGHT} y1={lanesBottom} y2={lanesBottom} className="stroke-border" strokeWidth={1} />

        {data.lanes.map((lane, index) => {
          const y = laneY(index)
          const significant = lane.events.filter((event) => event.severity !== "info")
          const ordinary = thinOut(
            lane.events.filter((event) => event.severity === "info"),
            x,
            7
          )
          return (
            <g key={lane.type}>
              <text x={LEFT - 16} y={y + 4} textAnchor="end" className="fill-muted-foreground text-[12px] font-medium">
                {TYPE_LABEL[lane.type]}
              </text>
              <line x1={LEFT} x2={width - RIGHT} y1={y} y2={y} className="stroke-grid" strokeWidth={1} />
              {ordinary.map((event) =>
                event.type === "transition" || event.type === "state_change" ? (
                  <path
                    key={event.id}
                    d={`M${x(event.timestamp)} ${y - 3.5} V${y + 3.5}`}
                    className="stroke-muted-foreground"
                    strokeWidth={1.1}
                    opacity={0.7}
                    fill="none"
                  />
                ) : (
                  <circle key={event.id} cx={x(event.timestamp)} cy={y} r={1.5} className="fill-faint" opacity={0.85} />
                )
              )}
              {lane.sustained.map((item) => (
                <g key={`${item.assetId}-${item.from}`}>
                  <title>{`${item.assetId} · ${item.label} · ${formatClock(item.from)}–${formatClock(item.to)}`}</title>
                  <path
                    d={`M${x(item.from)} ${y} H${Math.max(x(item.from) + 4, x(item.to))}`}
                    className="stroke-status-attention"
                    strokeWidth={3.5}
                    fill="none"
                  />
                </g>
              ))}
              {significant.map((event) => (
                <GlyphShape
                  key={event.id}
                  kind={event.severity === "critical" ? "critical" : "attention"}
                  x={x(event.timestamp)}
                  y={y}
                  size={event.severity === "critical" ? 10 : 9}
                />
              ))}
            </g>
          )
        })}

        {patterns.map((item) => {
          const active = item.pattern.id === selectedPattern
          return (
            <g key={item.pattern.id}>
              <line
                x1={item.spineX}
                x2={item.spineX}
                y1={laneY(item.topRow)}
                y2={labelTop}
                className="stroke-vena"
                strokeWidth={active ? 1.6 : 1}
              />
              {item.members.map((member) => (
                <g
                  key={member.cluster.id}
                  role="button"
                  tabIndex={0}
                  aria-label={`${clusterTitle(member.cluster)}: ${member.cluster.transitions} нетипичных переходов, ${member.cluster.summary}`}
                  aria-pressed={member.cluster.id === selectedCluster}
                  className="cursor-pointer outline-none [&:focus-visible_path]:stroke-ring"
                  onPointerEnter={(event) => setHover({ cluster: member.cluster, x: event.nativeEvent.offsetX, y: laneY(member.row) })}
                  onPointerLeave={() => setHover(null)}
                  onFocus={() => setHover({ cluster: member.cluster, x: member.cx, y: laneY(member.row) })}
                  onBlur={() => setHover(null)}
                  onClick={() => onSelect({ kind: "cluster", id: member.cluster.id })}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault()
                      onSelect({ kind: "cluster", id: member.cluster.id })
                    }
                  }}
                >
                  <line x1={member.cx} x2={item.spineX} y1={laneY(member.row)} y2={laneY(member.row)} className="stroke-vena" strokeWidth={1} />
                  <path
                    d={`M${member.cx} ${laneY(member.row) - 7} l7 7 -7 7 -7 -7Z`}
                    className={cn("stroke-vena", member.cluster.id === selectedCluster ? "fill-vena/25" : "fill-background")}
                    strokeWidth={1.6}
                  />
                  <text x={member.cx} y={laneY(member.row) - 13} textAnchor="middle" className="fill-vena font-mono text-[11px] tabular-nums">
                    {member.cluster.transitions}
                  </text>
                </g>
              ))}
            </g>
          )
        })}

        <line x1={x(data.now)} x2={x(data.now)} y1={TOP - 14} y2={lanesBottom} className="stroke-foreground" strokeWidth={1.5} />
        <text x={x(data.now) - 8} y={TOP - 6} textAnchor="end" className="fill-foreground text-[12px] font-semibold tracking-[0.1em] uppercase">
          Now
          <tspan className="fill-muted-foreground font-mono text-[11px] font-normal tracking-normal" dx={7}>
            {formatClock(data.now)}
          </tspan>
        </text>
        <text x={LEFT - 16} y={lanesBottom + 18} textAnchor="end" className="fill-faint text-[11px] tracking-[0.06em] uppercase">
          Past
        </text>
      </svg>

      {patterns.map((item) => {
        const flip = item.spineX + LABEL_WIDTH > width - RIGHT
        return (
          <button
            key={item.pattern.id}
            type="button"
            aria-pressed={item.pattern.id === selectedPattern}
            onClick={() => onSelect({ kind: "pattern", id: item.pattern.id })}
            className={cn(
              "group absolute flex flex-col gap-0.5 text-left leading-tight outline-none focus-visible:ring-2 focus-visible:ring-ring/60",
              flip ? "items-end border-r border-vena pr-3 text-right" : "border-l border-vena pl-3"
            )}
            style={{
              left: flip ? item.spineX - LABEL_WIDTH : item.spineX,
              top: labelTop,
              width: LABEL_WIDTH,
              height: labelHeight,
            }}
          >
            <span className="text-[13px] font-semibold tracking-[0.12em] text-vena uppercase">Pattern {patternLabel(item.pattern)}</span>
            <span className="font-mono text-[12px] text-muted-foreground tabular-nums">
              {item.pattern.systems.length} systems · {item.pattern.events} events
            </span>
            {showRange ? (
              <span className="font-mono text-[12px] text-faint tabular-nums">
                {formatClock(item.pattern.start)}–{formatClock(item.pattern.end)}
              </span>
            ) : null}
            <span className="text-[12px] text-foreground underline-offset-4 group-hover:underline">Inspect →</span>
          </button>
        )
      })}

      {hover ? (
        <div
          role="tooltip"
          className="pointer-events-none absolute z-10 min-w-48 border bg-elevated px-3 py-2"
          style={{ left: clamp(hover.x + 14, 8, width - 240), top: clamp(hover.y + 16, 4, height - 104) }}
        >
          <p className="font-mono text-[12px] tabular-nums">
            {formatClock(hover.cluster.start)}–{formatClock(hover.cluster.end)}
          </p>
          <p className="text-[12px] text-muted-foreground">{clusterTitle(hover.cluster)}</p>
          <p className="mt-1 text-[12px]">{hover.cluster.transitions} abnormal transitions</p>
          <p className={cn("text-[12px]", hover.cluster.riskDelta > 1 ? "text-status-attention" : "text-muted-foreground")}>
            {hover.cluster.summary}
          </p>
        </div>
      ) : null}
    </div>
  )
}
