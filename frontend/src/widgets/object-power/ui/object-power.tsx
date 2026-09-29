"use client"

import * as React from "react"

import { useAssetTree, type ChannelNode, type ObjectNode } from "@/entities/analytics"
import { LoadingBar, StateMessage } from "@/shared/ui/state-message"
import { ObjectList } from "@/widgets/object-schema"

type FeederKind = "pumps" | "fans" | "lighting" | "tech" | "reserve" | "other"

type Column = {
  key: string
  title: string
  subtitle: string
  head: ChannelNode
  members: ChannelNode[]
  consumerTitle: string
  consumers: ChannelNode[]
}

const KIND_LABEL: Record<FeederKind, string> = {
  pumps: "насосная станция",
  fans: "вентиляция",
  lighting: "освещение",
  tech: "технические средства",
  reserve: "резерв",
  other: "прочая нагрузка",
}

const GROUPED: FeederKind[] = ["lighting", "tech", "reserve", "other"]
const MAX_INPUTS = 4
const MAX_CONSUMERS = 6
const COLUMN = 136
const BOX_W = 116
const TOP = 20
const INPUT_H = 44
const BUS_Y = 100
const FEEDER_Y = 132
const FEEDER_H = 60
const CONSUMER_Y = 230

function compact(name: string | null) {
  return (name ?? "").replace(/\s+/g, " ").trim()
}

function classify(channel: ChannelNode): { input: boolean; kind: FeederKind; station: string | null } {
  const name = compact(channel.name).toUpperCase()
  if (/ВВОД|ЩАП|АВР|ДП\b/.test(name)) return { input: true, kind: "other", station: null }
  const station = name.match(/^ФАНС\s*-?\s*(\d+)/)
  if (station) return { input: false, kind: "pumps", station: `АНС${station[1]}` }
  if (/^ФВ/.test(name)) return { input: false, kind: "fans", station: null }
  if (/^(ФАО|ФРО|РО\d|ГРО|ГРУППА)/.test(name)) return { input: false, kind: "lighting", station: null }
  if (/^ФТС/.test(name)) return { input: false, kind: "tech", station: null }
  if (/^ФРЕЗ/.test(name)) return { input: false, kind: "reserve", station: null }
  return { input: false, kind: "other", station: null }
}

function stationOf(channel: ChannelNode) {
  const match = compact(channel.name).toUpperCase().match(/АНС\s*-?\s*(\d+)/)
  return match ? `АНС${match[1]}` : null
}

function score(channel: ChannelNode) {
  return channel.probability ?? -1
}

function worst(channels: ChannelNode[]) {
  return [...channels].sort((left, right) => score(right) - score(left))[0]
}

function nearest(target: ChannelNode, feeders: ChannelNode[]) {
  if (feeders.length === 1 || target.picketM === null) return feeders[0]
  const placed = feeders.filter((feeder) => feeder.picketM !== null)
  if (placed.length === 0) return feeders[0]
  return placed.reduce((best, feeder) =>
    Math.abs((feeder.picketM as number) - (target.picketM as number)) < Math.abs((best.picketM as number) - (target.picketM as number)) ? feeder : best
  )
}

function build(object: ObjectNode) {
  const channels = object.sections.flatMap((section) => section.channels)
  const phases = channels.filter((channel) => channel.sensorType === "Состояние фазы" || channel.scenario === "power_loss")
  const inputs = phases.filter((channel) => classify(channel).input).sort((left, right) => score(right) - score(left))
  const feeders = phases.filter((channel) => !classify(channel).input)
  const byKind = (kind: FeederKind) =>
    feeders.filter((channel) => classify(channel).kind === kind).sort((left, right) => compact(left.name).localeCompare(compact(right.name), "ru"))
  const pumpFeeders = byKind("pumps")
  const fanFeeders = byKind("fans")
  const pumps = channels.filter((channel) => channel.sensorType === "Состояние насоса" || channel.scenario === "flooding")
  const fans = channels.filter((channel) => channel.sensorType === "Состояние вентилятора" || channel.scenario === "ventilation")

  const owner = new Map<string, string>()
  for (const pump of pumps) {
    const station = stationOf(pump)
    const exact = pumpFeeders.find((feeder) => classify(feeder).station === station)
    const feeder = exact ?? (pumpFeeders.length ? nearest(pump, pumpFeeders) : undefined)
    if (feeder) owner.set(pump.assetId, feeder.assetId)
  }
  for (const fan of fans) {
    const feeder = fanFeeders.length ? nearest(fan, fanFeeders) : undefined
    if (feeder) owner.set(fan.assetId, feeder.assetId)
  }

  const single = (feeder: ChannelNode, consumerTitle: string, pool: ChannelNode[]): Column => ({
    key: feeder.assetId,
    title: compact(feeder.name).split(" ")[0] || feeder.assetId,
    subtitle: KIND_LABEL[classify(feeder).kind],
    head: feeder,
    members: [feeder],
    consumerTitle,
    consumers: pool.filter((item) => owner.get(item.assetId) === feeder.assetId).sort((left, right) => score(right) - score(left)),
  })

  const columns: Column[] = [
    ...pumpFeeders.map((feeder) => single(feeder, classify(feeder).station ?? "насосы", pumps)),
    ...fanFeeders.map((feeder) => single(feeder, "вентиляторы", fans)),
    ...GROUPED.flatMap((kind) => {
      const members = byKind(kind)
      if (members.length === 0) return []
      return [
        {
          key: kind,
          title: members.length === 1 ? compact(members[0].name).split(" ")[0] : `${members.length} фидеров`,
          subtitle: KIND_LABEL[kind],
          head: worst(members),
          members,
          consumerTitle: KIND_LABEL[kind],
          consumers: [],
        },
      ]
    }),
  ]
  const orphans = [...pumps, ...fans].filter((channel) => !owner.has(channel.assetId))
  return { inputs, columns, orphans }
}

function fill(channel: ChannelNode | null) {
  if (!channel || channel.probability === null) return "var(--elevated)"
  if (channel.riskLevel === "critical") return "color-mix(in oklab, var(--status-critical) 20%, var(--elevated))"
  if (channel.riskLevel === "attention") return "color-mix(in oklab, var(--status-attention) 20%, var(--elevated))"
  return "var(--elevated)"
}

function stroke(channel: ChannelNode | null) {
  if (channel?.riskLevel === "critical") return "var(--status-critical)"
  if (channel?.riskLevel === "attention") return "var(--status-attention)"
  return "var(--input)"
}

function pct(channel: ChannelNode | null) {
  return channel?.probability == null ? "—" : `${Math.round(channel.probability * 100)}%`
}

function Diagram({ object, selectedId, onSelect }: { object: ObjectNode; selectedId: string | null; onSelect: (id: string) => void }) {
  const { inputs, columns, orphans } = React.useMemo(() => build(object), [object])
  const shownInputs = inputs.slice(0, MAX_INPUTS)
  const rows = Math.max(1, ...columns.map((column) => Math.min(column.consumers.length, MAX_CONSUMERS) + (column.consumers.length > MAX_CONSUMERS ? 1 : 0)))
  const busLeft = 24
  const busRight = Math.max(busLeft + 4 * COLUMN - (COLUMN - BOX_W), busLeft + columns.length * COLUMN - (COLUMN - BOX_W))
  const width = busRight + 24
  const height = CONSUMER_Y + 24 + rows * 22 + (orphans.length ? 30 : 12)
  const inputSpan = shownInputs.length ? (busRight - busLeft) / shownInputs.length : 0
  const mono = "var(--font-plex-mono)"

  return (
    <svg width={width} height={height} role="img" aria-label={`Однолинейная схема питания: ${object.label}`} className="block">
      <defs>
        <pattern id="power-grid" width="16" height="16" patternUnits="userSpaceOnUse">
          <path d="M16 0H0V16" fill="none" stroke="var(--grid)" />
        </pattern>
      </defs>
      <rect width={width} height={height} fill="url(#power-grid)" />

      {shownInputs.map((input, index) => {
        const cx = busLeft + inputSpan * index + inputSpan / 2
        const selected = input.assetId === selectedId
        return (
          <g key={input.assetId} className="cursor-pointer" onClick={() => onSelect(input.assetId)}>
            <line x1={cx} x2={cx} y1={TOP + INPUT_H} y2={BUS_Y} stroke="var(--foreground)" strokeWidth="1.5" />
            <circle cx={cx} cy={TOP + INPUT_H + 14} r="6" fill="var(--elevated)" stroke="var(--foreground)" strokeWidth="1.5" />
            <rect x={cx - 80} y={TOP} width={160} height={INPUT_H} fill={fill(input)} stroke={selected ? "var(--vena)" : stroke(input)} strokeWidth={selected ? 2 : 1} />
            <text x={cx - 72} y={TOP + 17} fontSize="11.5" fontWeight="600" fill="var(--foreground)">
              {compact(input.name).slice(0, 24)}
            </text>
            <text x={cx - 72} y={TOP + 34} fontSize="10.5" fill={stroke(input)} fontFamily={mono}>
              ВВОД · откл. {pct(input)}
            </text>
          </g>
        )
      })}
      {inputs.length > MAX_INPUTS ? (
        <text x={busRight} y={TOP - 6} textAnchor="end" fontSize="10.5" fill="var(--muted-foreground)" fontFamily={mono}>
          ПОКАЗАНЫ {MAX_INPUTS} ИЗ {inputs.length} ВВОДОВ С НАИБОЛЬШИМ РИСКОМ
        </text>
      ) : null}
      {inputs.length === 0 ? (
        <text x={busLeft} y={TOP + 26} fontSize="11.5" fill="var(--muted-foreground)">
          Вводы в справочнике не выделены — шина показана условно
        </text>
      ) : null}

      <line x1={busLeft} x2={busRight} y1={BUS_Y} y2={BUS_Y} stroke="var(--foreground)" strokeWidth="4" />
      <text x={busLeft} y={BUS_Y - 8} fontSize="10" fill="var(--muted-foreground)" fontFamily={mono}>
        ШИНА 0,4 кВ
      </text>

      {columns.map((column, index) => {
        const x = busLeft + index * COLUMN
        const cx = x + BOX_W / 2
        const selected = column.members.some((member) => member.assetId === selectedId)
        const shown = column.consumers.slice(0, MAX_CONSUMERS)
        const terminal = column.consumers.length === 0
        return (
          <g key={column.key}>
            <line x1={cx} x2={cx} y1={BUS_Y} y2={FEEDER_Y} stroke="var(--foreground)" strokeWidth="1.5" />
            <path d={`M${cx - 6},${BUS_Y + 10} L${cx + 6},${BUS_Y + 20}`} stroke="var(--foreground)" strokeWidth="1.5" />
            <g className="cursor-pointer" onClick={() => onSelect(column.head.assetId)}>
              <rect x={x} y={FEEDER_Y} width={BOX_W} height={FEEDER_H} fill={fill(column.head)} stroke={selected ? "var(--vena)" : stroke(column.head)} strokeWidth={selected ? 2 : 1} />
              <text x={x + 8} y={FEEDER_Y + 18} fontSize="12.5" fontWeight="600" fill="var(--foreground)" fontFamily={mono}>
                {column.title.slice(0, 13)}
              </text>
              <text x={x + 8} y={FEEDER_Y + 34} fontSize="10.5" fill="var(--muted-foreground)">
                {column.subtitle}
              </text>
              <text x={x + 8} y={FEEDER_Y + 51} fontSize="11" fill={stroke(column.head)} fontFamily={mono}>
                {column.members.length > 1 ? "макс. " : ""}откл. {pct(column.head)}
              </text>
            </g>
            <line
              x1={cx}
              x2={cx}
              y1={FEEDER_Y + FEEDER_H}
              y2={CONSUMER_Y - 4}
              stroke="var(--foreground)"
              strokeWidth="1.5"
              strokeDasharray={terminal ? "3 3" : undefined}
            />
            {terminal ? (
              <path d={`M${cx - 8},${CONSUMER_Y - 4} L${cx + 8},${CONSUMER_Y - 4} L${cx},${CONSUMER_Y + 6} Z`} fill="none" stroke="var(--foreground)" strokeWidth="1.5" />
            ) : null}
            <text x={x} y={CONSUMER_Y + (terminal ? 22 : 12)} fontSize="11" fontWeight="600" fill="var(--foreground)">
              {column.consumerTitle}
            </text>
            {shown.map((channel, row) => {
              const y = CONSUMER_Y + 20 + row * 22
              const active = channel.assetId === selectedId
              return (
                <g key={channel.assetId} className="cursor-pointer" onClick={() => onSelect(channel.assetId)}>
                  <rect x={x} y={y} width={BOX_W} height={18} fill={fill(channel)} stroke={active ? "var(--vena)" : stroke(channel)} strokeWidth={active ? 2 : 1} />
                  <text x={x + 6} y={y + 12.5} fontSize="10.5" fill="var(--foreground)" fontFamily={mono}>
                    {compact(channel.name).slice(0, 11)}
                  </text>
                  <text x={x + BOX_W - 6} y={y + 12.5} textAnchor="end" fontSize="10.5" fill={stroke(channel)} fontFamily={mono}>
                    {pct(channel)}
                  </text>
                </g>
              )
            })}
            {column.consumers.length > shown.length ? (
              <text x={x} y={CONSUMER_Y + 20 + shown.length * 22 + 12} fontSize="10.5" fill="var(--muted-foreground)">
                ещё {column.consumers.length - shown.length}
              </text>
            ) : null}
          </g>
        )
      })}
      {orphans.length > 0 ? (
        <text x={busLeft} y={height - 10} fontSize="11" fill="var(--muted-foreground)">
          Без фидера в справочнике: {orphans.map((channel) => compact(channel.name)).slice(0, 8).join(", ")}
          {orphans.length > 8 ? ` и ещё ${orphans.length - 8}` : ""}
        </text>
      ) : null}
    </svg>
  )
}

export function ObjectPower({ selectedId, onSelect }: { selectedId: string | null; onSelect: (assetId: string) => void }) {
  const tree = useAssetTree()
  const [objectId, setObjectId] = React.useState<string | null>(null)
  const objects = React.useMemo(
    () =>
      (tree.data ?? []).filter((object) =>
        object.sections.some((section) => section.channels.some((channel) => channel.sensorType === "Состояние фазы"))
      ),
    [tree.data]
  )
  const current = objects.find((object) => object.objectId === objectId) ?? objects[0] ?? null
  const summary = React.useMemo(() => (current ? build(current) : null), [current])

  return (
    <div className="flex size-full min-h-0">
      {tree.isPending ? null : <ObjectList objects={objects} selected={current?.objectId ?? null} onSelect={setObjectId} />}
      <div className="min-w-0 flex-1 overflow-auto">
        {tree.isPending ? (
          <LoadingBar />
        ) : tree.isError ? (
          <StateMessage title="Схема недоступна" description="Не удалось загрузить реестр объектов." />
        ) : !current || !summary ? (
          <StateMessage title="Нет данных о питании" description="В снимке нет каналов фаз." />
        ) : (
          <div className="space-y-3 px-4 py-3">
            <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
              <span className="text-[15px] font-semibold">{current.label}</span>
              <span className="font-mono text-[12px] text-muted-foreground">
                {summary.inputs.length} вводов · {summary.columns.reduce((total, column) => total + column.members.length, 0)} фидеров ·{" "}
                {summary.columns.reduce((total, column) => total + column.consumers.length, 0)} агрегатов под прогнозом
              </span>
            </div>
            <p className="max-w-[920px] border-l-2 border-brass pl-3 text-[12.5px] text-muted-foreground">
              Схема восстановлена по названиям каналов: ФАНС — насосная станция, ФВ — вентиляция, ФАО/ФРО/РО — освещение, ФТС —
              технические средства. Агрегат привязан к фидеру своего типа с ближайшим пикетом. 81 % отказов насосов и 86 %
              вентиляторов совпадают с отключением питания объекта, поэтому риск фидера — первое, что стоит проверить.
            </p>
            <div className="overflow-x-auto border border-border bg-elevated">
              <Diagram object={current} selectedId={selectedId} onSelect={onSelect} />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
