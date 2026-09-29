"use client"

import * as React from "react"

import { useAssetTree, type ChannelNode, type ObjectNode } from "@/entities/analytics"
import { SCENARIO_LABEL, type PredictionScenario } from "@/entities/prediction"
import { useElementSize } from "@/shared/lib/hooks/use-element-size"
import { cn } from "@/shared/lib/utils"
import { LoadingBar, StateMessage } from "@/shared/ui/state-message"
import type { RiskFilter, SystemFilter } from "@/widgets/network-toolbar"

const LABEL_WIDTH = 170
const UNPLACED_WIDTH = 56
const SUB_HEIGHT = 16
const SUB_ROWS = 4
const GAP = 14
const PICKET_METERS = 10
const AXIS_HEIGHT = 44
const PROFILE_HEIGHT = 30
const PAD_RIGHT = 24
const PROFILE_BINS = 60

const SYSTEM_SCENARIO: Record<Exclude<SystemFilter, "all">, string[]> = {
  pump: ["flooding"],
  fan: ["ventilation"],
  smoke: ["fire"],
  power: ["power_loss"],
  other: ["equipment"],
}

const LEVEL_COLOR: Record<string, string> = {
  critical: "var(--status-critical)",
  attention: "var(--status-attention)",
}

function levelColor(level: string) {
  return LEVEL_COLOR[level] ?? "var(--status-normal)"
}

export function hiTone(index: number | null) {
  if (index === null) return "text-faint"
  if (index < 40) return "text-status-critical"
  if (index < 70) return "text-status-attention"
  return "text-status-normal"
}

function scenarioText(scenario: string) {
  return SCENARIO_LABEL[scenario as PredictionScenario] ?? scenario
}

function sectionTitle(label: string | null, group: string) {
  const text = label ?? group
  const parts = text.split(" · ")
  return parts.length > 1 ? parts.slice(1).join(" · ") : text
}

function keep(channel: ChannelNode, system: SystemFilter, risk: RiskFilter, needle: string) {
  if (system !== "all" && !SYSTEM_SCENARIO[system].includes(channel.scenario)) return false
  if (risk === "attention" && channel.riskLevel !== "attention" && channel.riskLevel !== "critical") return false
  if (risk === "critical" && channel.riskLevel !== "critical") return false
  if (needle && !channel.assetId.includes(needle) && !(channel.name?.toLowerCase().includes(needle) ?? false)) return false
  return true
}

function Glyph({ scenario, x, y, r, fill }: { scenario: string; x: number; y: number; r: number; fill: string }) {
  if (scenario === "flooding") {
    return <path d={`M${x - r},${y - r * 0.8} L${x + r},${y - r * 0.8} L${x},${y + r} Z`} fill={fill} />
  }
  if (scenario === "ventilation") {
    return <rect x={x - r * 0.85} y={y - r * 0.85} width={r * 1.7} height={r * 1.7} fill={fill} />
  }
  if (scenario === "power_loss") {
    return <path d={`M${x},${y - r} L${x + r},${y} L${x},${y + r} L${x - r},${y} Z`} fill={fill} />
  }
  return <circle cx={x} cy={y} r={r * 0.9} fill={fill} />
}

const LEGEND = [
  { scenario: "flooding", label: "насосы, подтопление" },
  { scenario: "ventilation", label: "вентиляция" },
  { scenario: "power_loss", label: "электропитание" },
  { scenario: "fire", label: "дым, пожар" },
]

function Legend() {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-muted-foreground">
      {LEGEND.map((item) => (
        <span key={item.scenario} className="inline-flex items-center gap-1.5">
          <svg width="12" height="12" aria-hidden>
            <Glyph scenario={item.scenario} x={6} y={6} r={5} fill="var(--muted-foreground)" />
          </svg>
          {item.label}
        </span>
      ))}
      <span className="inline-flex items-center gap-1.5">
        <span aria-hidden className="size-2.5 bg-status-critical" /> критично
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span aria-hidden className="size-2.5 bg-status-attention" /> внимание
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span aria-hidden className="size-2.5 bg-status-normal opacity-50" /> норма
      </span>
    </div>
  )
}

export function ObjectList({
  objects,
  selected,
  onSelect,
}: {
  objects: ObjectNode[]
  selected: string | null
  onSelect: (id: string) => void
}) {
  return (
    <ul className="h-full w-60 shrink-0 overflow-auto border-r border-border py-2">
      {objects.map((object) => {
        const channels = object.sections.flatMap((section) => section.channels)
        const critical = channels.filter((channel) => channel.riskLevel === "critical").length
        const attention = channels.filter((channel) => channel.riskLevel === "attention").length
        return (
          <li key={object.objectId}>
            <button
              type="button"
              onClick={() => onSelect(object.objectId)}
              className={cn(
                "flex w-full items-baseline gap-2 px-4 py-1.5 text-left text-[13px] outline-none hover:bg-surface focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/60",
                selected === object.objectId && "bg-surface font-medium"
              )}
            >
              <span className="min-w-0 truncate">{object.label}</span>
              {critical ? <span className="font-mono text-[11px] text-status-critical">{critical}</span> : null}
              {attention ? <span className="font-mono text-[11px] text-status-attention">{attention}</span> : null}
              <span className={cn("ml-auto font-mono text-[12px] tabular-nums", hiTone(object.healthIndex))}>
                {object.healthIndex ?? "—"}
              </span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}

type Placed = { channel: ChannelNode; section: string; x: number; y: number }

const LANES = [
  { scenario: "flooding", label: "Насосы, подтопление" },
  { scenario: "ventilation", label: "Вентиляция" },
  { scenario: "power_loss", label: "Электропитание" },
  { scenario: "fire", label: "Дым, пожар" },
  { scenario: "equipment", label: "Оборудование" },
]

function laneOf(scenario: string) {
  return LANES.some((lane) => lane.scenario === scenario) ? scenario : "equipment"
}

function pack(items: { key: string; x: number }[], gap: number) {
  const rows: number[] = []
  const slot = new Map<string, number>()
  for (const item of [...items].sort((left, right) => left.x - right.x)) {
    let row = rows.findIndex((last) => item.x - last >= gap)
    if (row === -1 && rows.length < SUB_ROWS) row = rows.length
    if (row === -1) row = rows.indexOf(Math.min(...rows))
    rows[row] = item.x
    slot.set(item.key, row)
  }
  return { slot, count: Math.max(rows.length, 1) }
}

function Schema({
  object,
  channels,
  width,
  selectedId,
  onSelect,
}: {
  object: ObjectNode
  channels: { channel: ChannelNode; section: string }[]
  width: number
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  const [hover, setHover] = React.useState<Placed | null>(null)
  const located = channels.filter((item) => item.channel.picketM !== null)
  const pickets = located.map((item) => item.channel.picketM as number)
  const low = pickets.length ? Math.min(...pickets) : 0
  const span = Math.max((pickets.length ? Math.max(...pickets) : 100) - low, 50)
  const plotLeft = LABEL_WIDTH + UNPLACED_WIDTH
  const plotWidth = Math.max(width - plotLeft - PAD_RIGHT, 200)
  const scaleX = (meters: number) => plotLeft + ((meters - low) / span) * plotWidth
  const xOf = (channel: ChannelNode, order: number) =>
    channel.picketM === null ? LABEL_WIDTH + 10 + (order % 4) * 11 : scaleX(channel.picketM)

  const lanes = LANES.map((lane) => {
    const members = channels.filter((item) => laneOf(item.channel.scenario) === lane.scenario)
    const unplaced = members.filter((item) => item.channel.picketM === null)
    const positioned = members.map((item) => {
      const order = unplaced.indexOf(item)
      return { ...item, x: xOf(item.channel, order), packX: order === -1 ? scaleX(item.channel.picketM as number) : -1e6 + (order % 4) * 100 }
    })
    const packed = pack(
      positioned.map((item) => ({ key: item.channel.assetId, x: item.packX })),
      GAP
    )
    return { ...lane, positioned, packed }
  }).filter((lane) => lane.positioned.length > 0)

  let top = AXIS_HEIGHT + PROFILE_HEIGHT
  const placed: Placed[] = []
  const bands: ((typeof lanes)[number] & { top: number; height: number })[] = []
  for (const lane of lanes) {
    const laneHeight = lane.packed.count * SUB_HEIGHT + 16
    for (const item of lane.positioned) {
      const row = lane.packed.slot.get(item.channel.assetId) ?? 0
      placed.push({ channel: item.channel, section: item.section, x: item.x, y: top + 8 + row * SUB_HEIGHT + SUB_HEIGHT / 2 })
    }
    bands.push({ ...lane, top, height: laneHeight })
    top += laneHeight
  }
  const height = top + 8

  const rawStep = span / 8
  const magnitude = 10 ** Math.floor(Math.log10(Math.max(rawStep, 1)))
  const step = [1, 2, 5, 10].map((unit) => unit * magnitude).find((unit) => unit >= rawStep) ?? magnitude * 10
  const ticks: number[] = []
  for (let meters = Math.ceil(low / step) * step; meters <= low + span; meters += step) ticks.push(meters)
  const bins = Array.from({ length: PROFILE_BINS }, () => 0)
  for (const item of located) {
    const bin = Math.min(PROFILE_BINS - 1, Math.floor((((item.channel.picketM as number) - low) / span) * PROFILE_BINS))
    bins[bin] = Math.max(bins[bin], item.channel.probability ?? 0)
  }
  const binWidth = plotWidth / PROFILE_BINS

  return (
    <div className="relative">
      <svg width={width} height={height} role="img" aria-label={`Линейная схема: ${object.label}`}>
        <text x={16} y={AXIS_HEIGHT - 12} className="fill-muted-foreground text-[11px]">
          трасса объекта по пикетам
        </text>
        <text x={LABEL_WIDTH + UNPLACED_WIDTH / 2 - 6} y={AXIS_HEIGHT - 16} textAnchor="middle" className="fill-faint text-[10px]">
          без ПК
        </text>
        {ticks.map((meters) => (
          <g key={meters}>
            <line x1={scaleX(meters)} x2={scaleX(meters)} y1={AXIS_HEIGHT - 8} y2={height} stroke="var(--grid)" strokeOpacity={0.45} />
            {scaleX(meters) < width - 36 ? (
              <text x={scaleX(meters)} y={AXIS_HEIGHT - 16} textAnchor="middle" className="fill-muted-foreground font-mono text-[10px]">
                ПК{Math.round(meters / PICKET_METERS)}
              </text>
            ) : null}
          </g>
        ))}
        <line x1={plotLeft} x2={plotLeft + plotWidth} y1={AXIS_HEIGHT - 4} y2={AXIS_HEIGHT - 4} stroke="var(--vena)" strokeWidth={6} strokeOpacity={0.35} />
        <text x={16} y={AXIS_HEIGHT + PROFILE_HEIGHT / 2 + 4} className="fill-muted-foreground text-[11px]">
          наибольший риск на участке
        </text>
        {bins.map((value, index) =>
          value > 0 ? (
            <rect
              key={index}
              x={plotLeft + index * binWidth + 0.5}
              y={AXIS_HEIGHT + PROFILE_HEIGHT - 6 - value * (PROFILE_HEIGHT - 10)}
              width={Math.max(binWidth - 1, 1)}
              height={value * (PROFILE_HEIGHT - 10)}
              fill={value >= 0.5 ? "var(--status-critical)" : value >= 0.2 ? "var(--status-attention)" : "var(--status-normal)"}
              fillOpacity={0.7}
            />
          ) : null
        )}
        {bands.map((band, index) => {
          const worst = Math.max(...band.positioned.map((item) => item.channel.probability ?? 0))
          return (
            <g key={band.scenario}>
              {index % 2 === 0 ? <rect x={0} y={band.top} width={width} height={band.height} fill="var(--surface)" fillOpacity={0.6} /> : null}
              <line x1={0} x2={width} y1={band.top} y2={band.top} stroke="var(--border)" />
              <text x={16} y={band.top + 18} className="fill-foreground text-[12px]">
                {band.label}
              </text>
              <text x={16} y={band.top + 33} className="fill-muted-foreground text-[11px]">
                {band.positioned.length} кан. · макс. {Math.round(worst * 100)}%
              </text>
            </g>
          )
        })}
        {placed.map((item) => {
          const r = 3.5 + Math.min(item.channel.probability ?? 0, 1) * 3.5
          const active = item.channel.assetId === selectedId
          return (
            <g
              key={item.channel.assetId}
              role="button"
              tabIndex={0}
              aria-label={`${item.channel.name ?? item.channel.assetId}: ${item.channel.probability === null ? "нет прогноза" : `${Math.round(item.channel.probability * 100)}%`}`}
              className="cursor-pointer outline-none"
              onClick={() => onSelect(item.channel.assetId)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") onSelect(item.channel.assetId)
              }}
              onMouseEnter={() => setHover(item)}
              onMouseLeave={() => setHover(null)}
              opacity={item.channel.riskLevel === "critical" || item.channel.riskLevel === "attention" ? 1 : item.channel.probability === null ? 0.3 : 0.5}
            >
              {active ? <circle cx={item.x} cy={item.y} r={r + 4} fill="none" stroke="var(--vena)" strokeWidth={2} /> : null}
              <Glyph scenario={item.channel.scenario} x={item.x} y={item.y} r={r} fill={levelColor(item.channel.riskLevel)} />
            </g>
          )
        })}
      </svg>
      {hover ? (
        <div
          className="pointer-events-none absolute z-10 w-64 rounded-md border bg-popover px-3 py-2 text-[12px] shadow-sm"
          style={{ left: Math.min(hover.x + 12, width - 270), top: hover.y + 12 }}
        >
          <p className="font-medium">{hover.channel.name ?? hover.channel.assetId}</p>
          <p className="text-muted-foreground">
            {hover.channel.probability === null
              ? "Нет прогноза модели"
              : `${scenarioText(hover.channel.scenario)} · ${Math.round(hover.channel.probability * 100)}% за ${hover.channel.modelId.includes("72") ? "72" : "24"} ч`}
          </p>
          <p className="font-mono text-[11px] text-faint">
            канал {hover.channel.assetId} · шкаф {hover.section}
          </p>
        </div>
      ) : null}
    </div>
  )
}

export function ObjectSchema({
  query,
  selectedId,
  onSelect,
  system = "all",
  risk = "all",
}: {
  query: string
  selectedId: string | null
  onSelect: (assetId: string) => void
  system?: SystemFilter
  risk?: RiskFilter
}) {
  const tree = useAssetTree()
  const [containerRef, size] = useElementSize<HTMLDivElement>()
  const [objectId, setObjectId] = React.useState<string | null>(null)
  const needle = query.trim().toLowerCase()

  const objects = React.useMemo(
    () =>
      (tree.data ?? []).filter((object) =>
        object.sections.some((section) => section.channels.some((channel) => keep(channel, system, risk, needle)))
      ),
    [tree.data, system, risk, needle]
  )
  const ownerOfSelected = selectedId
    ? objects.find((object) => object.sections.some((section) => section.channels.some((channel) => channel.assetId === selectedId)))
    : undefined
  const current =
    objects.find((object) => object.objectId === objectId) ?? ownerOfSelected ?? objects[0] ?? null
  const channels = (current?.sections ?? []).flatMap((section) =>
    section.channels
      .filter((channel) => keep(channel, system, risk, needle))
      .map((channel) => ({ channel, section: sectionTitle(section.label, section.group) }))
  )
  const sections = new Set(channels.map((item) => item.section)).size
  const placed = channels.filter((item) => item.channel.picketM !== null).length

  return (
    <div className="flex size-full min-h-0">
      {tree.isPending ? null : (
        <ObjectList objects={objects} selected={current?.objectId ?? null} onSelect={setObjectId} />
      )}
      <div ref={containerRef} className="min-w-0 flex-1 overflow-auto">
        {tree.isPending ? (
          <LoadingBar />
        ) : tree.isError ? (
          <StateMessage title="Схема недоступна" description="Не удалось загрузить реестр объектов из снимка прогнозов." />
        ) : !current ? (
          <StateMessage title="Нет объектов" description="Под текущий фильтр не попал ни один канал." />
        ) : (
          <div className="space-y-3 px-4 py-3">
            <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
              <span className="text-[15px] font-semibold">{current.label}</span>
              <span className={cn("font-mono text-[13px]", hiTone(current.healthIndex))}>
                индекс здоровья {current.healthIndex ?? "—"}
              </span>
              <span className="text-[12px] text-muted-foreground">
                {channels.length} каналов с прогнозом · {sections} шкафов · {placed} с привязкой к пикету
              </span>
            </div>
            <Legend />
            <p className="text-[12px] text-muted-foreground">
              Датчики расставлены по пикету из названия (ПК = 10 м), полосы — инженерные системы. Цвет — уровень риска модели,
              размер значка — вероятность события; клик открывает карточку канала.
            </p>
            <Schema object={current} channels={channels} width={Math.max(size.width, 640)} selectedId={selectedId} onSelect={onSelect} />
          </div>
        )}
      </div>
    </div>
  )
}
