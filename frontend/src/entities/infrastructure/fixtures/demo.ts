import { HOUR, MINUTE } from "@/shared/lib/time"

import { layoutGroups } from "../lib/layout"
import type { AssetType, NetworkEdge, ReplayEpisode, SensorEvent, StateSegment } from "../model/types"

export const DEMO_NOW = Date.UTC(2026, 8, 21, 21)
export const DATA_START = DEMO_NOW - 7 * 24 * HOUR
export const STEP = 30 * MINUTE

export type AssetRecord = {
  id: string
  name: string
  type: AssetType
  group: string
  channelId: string
  baseScore: number
  offline: boolean
}

type Group = { id: string; name: string; system: string }
type Dataset = {
  assets: AssetRecord[]
  byId: Map<string, AssetRecord>
  groups: Group[]
  layout: ReturnType<typeof layoutGroups>
  interGroupEdges: NetworkEdge[]
  events: SensorEvent[]
  eventsByAsset: Map<string, SensorEvent[]>
  states: Map<string, StateSegment[]>
  episode: ReplayEpisode
}

const GROUPS: Group[] = Array.from({ length: 16 }, (_, index) => ({
  id: `K-${String(index + 1).padStart(2, "0")}`,
  name: `Коллектор К${index + 1}`,
  system: ["Пожарная система", "Насосная система", "Электроснабжение", "Вентиляция"][index % 4],
}))
const TYPES: AssetType[] = ["pump", "fan", "smoke", "power", "other"]

function createDataset(): Dataset {
  const assets: AssetRecord[] = Array.from({ length: 128 }, (_, index) => {
    const type = TYPES[index % TYPES.length]
    const id = index === 0 ? "P-0142" : `${type[0].toUpperCase()}-${String(index + 101).padStart(4, "0")}`
    return {
      id,
      name: `${type} ${index + 1}`,
      type,
      group: GROUPS[Math.floor(index / 8)].id,
      channelId: String(56000 + index),
      baseScore: index === 0 ? 68 : index < 3 ? 70 : index < 15 ? 45 : 18 + index % 10,
      offline: index >= 122,
    }
  })
  const layout = layoutGroups(GROUPS.map((group, groupIndex) => ({
    groupIndex, groupId: group.id,
    assets: assets.filter((asset) => asset.group === group.id).map(({ id, type }) => ({ id, type })),
  })))
  const events: SensorEvent[] = assets.flatMap((asset, assetIndex) =>
    Array.from({ length: 42 }, (_, index) => ({
      id: `${asset.id}-${index}`,
      assetId: asset.id,
      timestamp: DATA_START + index * 4 * HOUR + (assetIndex % 8) * MINUTE,
      type: assetIndex !== 0 && index % 19 === 0 ? "failure" as const : index % 5 === 0 ? "alarm" as const : "transition" as const,
      state: assetIndex !== 0 && index % 19 === 0 ? "Неисправен" : "Норма",
      severity: assetIndex !== 0 && index % 19 === 0 ? "critical" as const : index % 5 === 0 ? "warning" as const : "info" as const,
    }))
  )
  const pumpAssets = assets.filter((asset) => asset.type === "pump").slice(0, 7)
  const smokeAssets = assets.filter((asset) => asset.type === "smoke").slice(0, 3)
  for (const [index, asset] of pumpAssets.entries()) {
    events.push({ id: `cluster-pump-${index}`, assetId: asset.id, timestamp: DEMO_NOW - (8 - index) * MINUTE, type: "anomaly", state: "Отклонение", severity: "warning" })
  }
  for (const [index, asset] of smokeAssets.entries()) {
    events.push({ id: `cluster-smoke-${index}`, assetId: asset.id, timestamp: DEMO_NOW - (6 - index) * MINUTE, type: "alarm", state: "Тревога", severity: "warning" })
  }
  events.push({ id: "demo-critical-now", assetId: assets[1].id, timestamp: DEMO_NOW - 2 * MINUTE, type: "failure", state: "Неисправен", severity: "critical" })
  events.push({ id: "demo-replay-failure", assetId: assets[0].id, timestamp: Date.UTC(2026, 8, 17, 10, 30), type: "failure", state: "Неисправен", severity: "critical" })
  events.sort((left, right) => left.timestamp - right.timestamp)
  const eventsByAsset = new Map(assets.map((asset) => [asset.id, events.filter((event) => event.assetId === asset.id)]))
  const states = new Map(assets.map((asset) => [asset.id, [
    { from: DATA_START, to: DEMO_NOW, state: "normal" as const, label: "Норма" },
  ]]))
  return {
    assets, byId: new Map(assets.map((asset) => [asset.id, asset])), groups: GROUPS, layout,
    interGroupEdges: [
      { source: assets[0].id, target: assets[8].id, relationType: "logical" },
      { source: assets[8].id, target: assets[16].id, relationType: "logical" },
    ],
    events, eventsByAsset, states,
    episode: { id: "demo-episode", label: "Демонстрационный эпизод", assetId: assets[0].id, start: Date.UTC(2026, 8, 17, 9), end: Date.UTC(2026, 8, 17, 10, 30) },
  }
}

let dataset: Dataset | null = null
export function getDataset(): Dataset {
  dataset ??= createDataset()
  return dataset
}

export function eventsBetween(events: SensorEvent[], from: number, to: number): SensorEvent[] {
  return events.filter((event) => event.timestamp >= from && event.timestamp <= to)
}

export function isOffline(record: AssetRecord, _at?: number): boolean {
  return record.offline
}

export function scoreAt(record: AssetRecord, at: number): number {
  if (record.id === "P-0142") {
    const boundary = DEMO_NOW - 6 * HOUR
    const score = at <= boundary
      ? 51 + ((at - boundary) / HOUR) * 0.2
      : 51 + ((at - boundary) / (6 * HOUR)) * 17
    return Math.max(1, Math.min(99, Math.round(score)))
  }
  return record.baseScore
}
