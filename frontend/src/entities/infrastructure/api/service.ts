import { HOUR, MINUTE } from "@/shared/lib/time"

import {
  DEMO_NOW,
  DATA_START,
  STEP,
  eventsBetween,
  getDataset,
  isOffline,
  scoreAt,
  type AssetRecord,
} from "../data/demo"
import { CANVAS_HEIGHT, CANVAS_WIDTH } from "../lib/layout"
import { TYPE_LABEL, isWatch, levelFromScore, statusFromScore } from "../lib/risk"
import { lowerBound } from "../lib/prng"
import type {
  Asset,
  AssetDetail,
  AssetType,
  FactorGroup,
  ForecastHorizon,
  ForecastPoint,
  NetworkModel,
  PulseCluster,
  PulseData,
  PulseEvent,
  PulseLane,
  PulsePattern,
  PulseSustained,
  ReplayEpisode,
  RiskFactor,
  RiskSnapshot,
  SensorEvent,
  PulseSummary,
  Situation,
  StateSegment,
  TemporalBundle,
} from "../model/types"

type View = { now: number; horizon: ForecastHorizon }

const SEVERITY_WEIGHT = { info: 1, warning: 3, critical: 6 } as const
const PULSE_TYPES: AssetType[] = ["pump", "fan", "smoke", "power"]

function scaledScore(record: AssetRecord, at: number, horizon: ForecastHorizon) {
  const score = scoreAt(record, at)
  return horizon === 72 ? Math.round(score) : Math.round(Math.max(1, score * 0.82 - 1))
}

function lastEventAt(record: AssetRecord, at: number) {
  const list = getDataset().eventsByAsset.get(record.id) ?? []
  const index = lowerBound(list, at + 1, (event) => event.timestamp) - 1
  return index >= 0 ? list[index].timestamp : null
}

function toAsset(record: AssetRecord, view: View): Asset {
  const score = scaledScore(record, view.now, view.horizon)
  const offline = isOffline(record, view.now)
  return {
    id: record.id,
    name: record.name,
    type: record.type,
    group: record.group,
    channelId: record.channelId,
    status: offline ? "offline" : statusFromScore(score),
    riskLevel: levelFromScore(score),
    riskScore: score,
    scoreType: "risk_score",
    forecastHorizon: view.horizon,
    lastEventAt: lastEventAt(record, view.now),
  }
}

export async function getAssets(view: View): Promise<Asset[]> {
  return getDataset().assets.map((record) => toAsset(record, view))
}

export async function searchAssets(query: string, view: View, limit = 12): Promise<Asset[]> {
  const needle = query.trim().toLowerCase()
  const dataset = getDataset()
  const matches = dataset.assets.filter((record) => {
    if (!needle) return true
    return (
      record.id.toLowerCase().includes(needle) ||
      record.channelId.includes(needle) ||
      record.group.toLowerCase().includes(needle) ||
      record.type.includes(needle)
    )
  })
  return matches
    .map((record) => toAsset(record, view))
    .sort((left, right) => right.riskScore - left.riskScore)
    .slice(0, limit)
}

export async function getNetwork(view: View): Promise<NetworkModel> {
  const dataset = getDataset()
  const nodes = dataset.assets.map((record) => {
    const asset = toAsset(record, view)
    const position = dataset.layout.positions.get(record.id) ?? { x: 0, y: 0 }
    return {
      id: record.id,
      assetId: record.id,
      group: record.group,
      type: record.type,
      status: asset.status,
      risk: asset.riskScore,
      x: position.x,
      y: position.y,
    }
  })
  const risk = new Map(nodes.map((node) => [node.id, node.risk]))
  const groups = dataset.groups.map((group) => {
    const origin = dataset.layout.groupOrigins.get(group.id) ?? { x: 0, y: 0 }
    const members = nodes.filter((node) => node.group === group.id)
    return {
      id: group.id,
      name: group.name,
      system: group.system,
      x: origin.x,
      y: origin.y,
      maxRisk: Math.max(0, ...members.map((node) => risk.get(node.id) ?? 0)),
    }
  })
  return {
    nodes,
    edges: [...dataset.layout.edges, ...dataset.interGroupEdges],
    groups,
    width: CANVAS_WIDTH,
    height: CANVAS_HEIGHT,
  }
}

function factorsFor(record: AssetRecord, now: number, score: number) {
  const dataset = getDataset()
  const events = dataset.eventsByAsset.get(record.id) ?? []
  const recent = eventsBetween(events, now - 6 * HOUR, now).filter((event) => event.severity !== "info").length
  const previous = eventsBetween(events, now - 30 * HOUR, now - 6 * HOUR).filter((event) => event.severity !== "info").length
  const baseline = Math.max(previous / 4, 0.5)
  const rateChange = Math.round(((recent - baseline) / baseline) * 100)
  const failures = eventsBetween(events, now - 7 * 24 * HOUR, now).filter((event) => event.type === "failure")
  const lastFailure = failures.length > 0 ? failures[failures.length - 1].timestamp : null
  const sinceFailure = lastFailure === null ? null : (now - lastFailure) / (24 * HOUR)
  const segments = dataset.states.get(record.id) ?? []
  const abnormalNow = segments.some((segment) => segment.state === "abnormal" && segment.from <= now && segment.to >= now)
  const abnormalRecent = segments.filter((segment) => segment.state === "abnormal" && segment.to >= now - 6 * HOUR && segment.from <= now).length

  const factors: RiskFactor[] = [
    {
      key: "event-rate",
      label: "Event rate",
      value: `${rateChange >= 0 ? "+" : ""}${rateChange}%`,
      direction: rateChange > 10 ? "up" : rateChange < -10 ? "down" : "flat",
      basis: "rule_based",
    },
    {
      key: "recurrence",
      label: "Recurrence",
      value: failures.length >= 2 ? "high" : failures.length === 1 ? "medium" : "low",
      direction: failures.length >= 2 ? "up" : "flat",
      basis: "rule_based",
    },
    {
      key: "last-failure",
      label: "Last failure",
      value: sinceFailure === null ? "none in 7 d" : `${sinceFailure.toFixed(1)} d`,
      direction: sinceFailure !== null && sinceFailure < 3 ? "up" : "flat",
      basis: "rule_based",
    },
    {
      key: "state-changes",
      label: "State changes",
      value: abnormalNow ? "abnormal" : abnormalRecent > 0 ? "unstable" : "stable",
      direction: abnormalNow || abnormalRecent > 0 ? "up" : "flat",
      basis: "rule_based",
    },
  ]

  const history = failures.length * 6 + (sinceFailure !== null && sinceFailure < 3 ? 6 : 0) + 1
  const activity = Math.max(1, Math.min(30, Math.round(Math.max(rateChange, 0) / 8)) + recent)
  const state = (abnormalNow ? 10 : 0) + abnormalRecent * 3 + 1
  const baselinePoints = Math.round(score * 0.25)
  const budget = Math.max(0, score - baselinePoints)
  const total = history + activity + state
  const parts = [history, activity, state].map((raw) => Math.round((raw / total) * budget))
  parts[0] += budget - parts.reduce((sum, value) => sum + value, 0)
  const groups: FactorGroup[] = [
    { key: "baseline", label: "Baseline", points: baselinePoints },
    { key: "history", label: "History", points: parts[0] },
    { key: "activity", label: "Activity", points: parts[1] },
    { key: "state", label: "State", points: parts[2] },
  ]
  return { factors, groups }
}

export async function getAsset(id: string, view: View): Promise<AssetDetail | null> {
  const record = getDataset().byId.get(id)
  if (!record) return null
  const asset = toAsset(record, view)
  const deltaSince = Math.ceil((view.now - 6 * HOUR) / HOUR) * HOUR
  const delta = asset.riskScore - scaledScore(record, deltaSince, view.horizon)
  const { factors, groups } = factorsFor(record, view.now, asset.riskScore)
  const events = getDataset().eventsByAsset.get(id) ?? []
  const recent = eventsBetween(events, view.now - 48 * HOUR, view.now)
    .filter((event) => event.severity !== "info")
    .slice(-4)
    .reverse()
  return { asset, delta, deltaSince, factors, factorGroups: groups, recent }
}

export async function getRiskHistory(id: string, from: number, to: number, horizon: ForecastHorizon): Promise<RiskSnapshot[]> {
  const record = getDataset().byId.get(id)
  if (!record) return []
  const end = Math.min(to, DEMO_NOW)
  const points: RiskSnapshot[] = []
  const first = Math.max(from, DATA_START)
  for (let at = Math.ceil(first / STEP) * STEP; at <= end; at += STEP) {
    const score = scaledScore(record, at, horizon)
    points.push({ assetId: id, timestamp: at, score, level: levelFromScore(score), horizon, scoreType: "risk_score" })
  }
  return points
}

export async function getEvents(id: string, from: number, to: number): Promise<SensorEvent[]> {
  return eventsBetween(getDataset().eventsByAsset.get(id) ?? [], from, to)
}

export async function getStateHistory(id: string, from: number, to: number): Promise<StateSegment[]> {
  const segments = getDataset().states.get(id) ?? []
  return segments
    .filter((segment) => segment.to > from && segment.from < to)
    .map((segment) => ({ ...segment, from: Math.max(segment.from, from), to: Math.min(segment.to, to) }))
}

export async function getForecast(id: string, now: number, horizon: number): Promise<ForecastPoint[]> {
  const record = getDataset().byId.get(id)
  if (!record) return []
  const current = scoreAt(record, now)
  const slope = (current - scoreAt(record, now - 6 * HOUR)) / 6
  const points: ForecastPoint[] = []
  for (let hour = 0; hour <= horizon; hour += 1) {
    const mid = Math.min(99, Math.max(1, current + slope * Math.min(hour, 18) * 0.6))
    const spread = 2 + hour * 0.35
    points.push({
      timestamp: now + hour * HOUR,
      low: Math.max(0, mid - spread),
      mid,
      high: Math.min(100, mid + spread),
    })
  }
  return points
}

export async function getReplayEpisodes(): Promise<ReplayEpisode[]> {
  return [getDataset().episode]
}

const CLUSTER_GAP = 9 * MINUTE
const PATTERN_GAP = 60 * MINUTE

function detectClusters(significant: SensorEvent[], assetType: (id: string) => AssetType): PulseCluster[] {
  const dataset = getDataset()
  const clusters: PulseCluster[] = []
  for (const type of PULSE_TYPES) {
    let group: SensorEvent[] = []
    const flush = () => {
      if (group.length >= 3) {
        const start = group[0].timestamp
        const end = group[group.length - 1].timestamp
        const ids = Array.from(new Set(group.map((event) => event.assetId)))
        const deltas = ids.map((id) => {
          const record = dataset.byId.get(id)
          return record ? scoreAt(record, end) - scoreAt(record, start - HOUR) : 0
        })
        const riskDelta = deltas.reduce((sum, value) => sum + value, 0) / Math.max(1, deltas.length)
        clusters.push({
          id: `${type}-${start}`,
          start,
          end,
          systemType: type,
          assetIds: ids,
          transitions: group.length,
          riskDelta,
          summary: riskDelta > 1 ? "Risk increased" : riskDelta < -1 ? "Risk decreased" : "Risk unchanged",
        })
      }
      group = []
    }
    for (const event of significant.filter((item) => assetType(item.assetId) === type)) {
      if (group.length > 0 && event.timestamp - group[group.length - 1].timestamp > CLUSTER_GAP) flush()
      group.push(event)
    }
    flush()
  }
  return clusters
}

function groupPatterns(clusters: PulseCluster[]) {
  const sorted = [...clusters].sort((left, right) => left.start - right.start)
  const groups: PulseCluster[][] = []
  let current: PulseCluster[] = []
  let currentEnd = 0
  for (const cluster of sorted) {
    if (current.length > 0 && cluster.start - currentEnd <= PATTERN_GAP) {
      current.push(cluster)
      currentEnd = Math.max(currentEnd, cluster.end)
    } else {
      if (current.length > 0) groups.push(current)
      current = [cluster]
      currentEnd = cluster.end
    }
  }
  if (current.length > 0) groups.push(current)
  return groups.filter((group) => new Set(group.map((cluster) => cluster.systemType)).size >= 2)
}

let globalPatterns: { start: number; end: number }[] | null = null

function patternNumber(start: number, end: number) {
  if (!globalPatterns) {
    const dataset = getDataset()
    const significant = dataset.events.filter((event) => event.severity !== "info")
    const type = (id: string) => dataset.byId.get(id)?.type ?? "other"
    globalPatterns = groupPatterns(detectClusters(significant, type)).map((group) => ({
      start: Math.min(...group.map((cluster) => cluster.start)),
      end: Math.max(...group.map((cluster) => cluster.end)),
    }))
  }
  const index = globalPatterns.findIndex((pattern) => pattern.start <= end && pattern.end >= start)
  return index + 1
}

function detectPatterns(clusters: PulseCluster[]): PulsePattern[] {
  return groupPatterns(clusters).map((group) => {
    const start = Math.min(...group.map((cluster) => cluster.start))
    const end = Math.max(...group.map((cluster) => cluster.end))
    const number = patternNumber(start, end)
    return {
      id: `pattern-${start}`,
      number,
      start,
      end,
      clusterIds: group.map((cluster) => cluster.id),
      systems: Array.from(new Set(group.map((cluster) => cluster.systemType))),
      events: group.reduce((sum, cluster) => sum + cluster.transitions, 0),
      assetIds: Array.from(new Set(group.flatMap((cluster) => cluster.assetIds))),
      riskDelta: group.reduce((sum, cluster) => sum + cluster.riskDelta, 0) / group.length,
    }
  })
}

export async function getPulse(view: { now: number; windowHours: number }): Promise<PulseData> {
  const dataset = getDataset()
  const from = view.now - view.windowHours * HOUR
  const window = eventsBetween(dataset.events, from, view.now)
  const assetType = (id: string) => dataset.byId.get(id)?.type ?? "other"

  const binMs = 5 * MINUTE
  const bins = Math.ceil((view.now - from) / binMs)
  const raw = new Array<number>(bins).fill(0)
  for (const event of window) {
    const index = Math.min(bins - 1, Math.floor((event.timestamp - from) / binMs))
    raw[index] += SEVERITY_WEIGHT[event.severity]
  }
  const density = raw.map((_, index) => {
    const slice = raw.slice(Math.max(0, index - 1), index + 2)
    return { timestamp: from + (index + 0.5) * binMs, weight: slice.reduce((sum, value) => sum + value, 0) / slice.length }
  })

  const lanes = PULSE_TYPES.map<PulseLane>((type) => ({
    type,
    events: window
      .filter((event) => assetType(event.assetId) === type)
      .map<PulseEvent>((event) => ({ id: event.id, assetId: event.assetId, timestamp: event.timestamp, severity: event.severity, type: event.type })),
    sustained: dataset.assets
      .filter((record) => record.type === type)
      .flatMap((record) =>
        (dataset.states.get(record.id) ?? [])
          .filter((segment) => segment.state === "abnormal" && segment.from < view.now && segment.to > from && segment.to - segment.from >= 20 * MINUTE)
          .map<PulseSustained>((segment) => ({ assetId: record.id, from: Math.max(from, segment.from), to: Math.min(view.now, segment.to), label: segment.label }))
      )
      .sort((left, right) => left.from - right.from),
  }))

  const clusters = detectClusters(window.filter((event) => event.severity !== "info"), assetType)
  const patterns = detectPatterns(clusters)

  const online = dataset.assets.filter((record) => !isOffline(record, view.now))
  const scores = online.map((record) => scoreAt(record, view.now))
  const counts = {
    critical: scores.filter((score) => statusFromScore(score) === "critical").length,
    attention: scores.filter((score) => statusFromScore(score) === "attention").length,
    watch: scores.filter((score) => isWatch(score)).length,
    newIncidents: eventsBetween(dataset.events, view.now - HOUR, view.now).filter((event) => event.severity === "critical").length,
  }

  const systemRisk: { timestamp: number; score: number }[] = []
  const firstStep = Math.ceil(from / STEP) * STEP
  for (let at = firstStep; at <= view.now; at += STEP) {
    const top = dataset.assets
      .filter((record) => !isOffline(record, at))
      .map((record) => scoreAt(record, at))
      .sort((left, right) => right - left)
      .slice(0, 15)
    systemRisk.push({ timestamp: at, score: top.reduce((sum, value) => sum + value, 0) / Math.max(1, top.length) })
  }
  systemRisk.push({
    timestamp: view.now,
    score:
      scores
        .slice()
        .sort((left, right) => right - left)
        .slice(0, 15)
        .reduce((sum, value) => sum + value, 0) / 15,
  })

  return {
    now: view.now,
    from,
    windowHours: view.windowHours,
    lanes,
    density,
    systemRisk,
    clusters,
    patterns,
    counts,
    systemState: counts.critical >= 3 ? "degraded" : "stable",
    recent: window.filter((event) => event.severity !== "info").slice(-14).reverse(),
  }
}

export async function getTemporal(id: string, view: View, halfSpanHours: number): Promise<TemporalBundle | null> {
  const record = getDataset().byId.get(id)
  if (!record) return null
  const from = view.now - halfSpanHours * HOUR
  const [events, states, history, forecast] = await Promise.all([
    getEvents(id, from, view.now),
    getStateHistory(id, from, view.now),
    getRiskHistory(id, from, view.now, view.horizon),
    getForecast(id, view.now, halfSpanHours),
  ])
  return { asset: toAsset(record, view), events, states, history, forecast }
}

export async function getSituations(view: View, limit = 4): Promise<Situation[]> {
  const dataset = getDataset()
  const pulse = await getPulse({ now: view.now, windowHours: 6 })
  const situations: Situation[] = []

  for (const pattern of pulse.patterns.slice(-2)) {
    const systems = pattern.systems.map((type) => TYPE_LABEL[type].toLowerCase()).join(", ")
    situations.push({
      id: pattern.id,
      type: "pattern",
      severity: pattern.riskDelta > 1 ? "critical" : "warning",
      title: `Pattern ${String(pattern.number).padStart(3, "0")}`,
      assetIds: pattern.assetIds,
      patternId: pattern.id,
      summary: `${pattern.events} abnormal transitions across ${pattern.systems.length} systems (${systems}).`,
      changedAt: pattern.end,
      riskScore: null,
      delta: null,
      horizon: null,
      primaryReason: "Correlated activity in independent systems",
      status: "new",
    })
  }

  const ranked = dataset.assets
    .filter((record) => !isOffline(record, view.now))
    .map((record) => ({ record, score: scaledScore(record, view.now, view.horizon) }))
    .filter((item) => statusFromScore(item.score) !== "normal")
    .sort((left, right) => right.score - left.score)
    .slice(0, limit)

  for (const item of ranked) {
    const { factors } = factorsFor(item.record, view.now, item.score)
    const rising = factors.find((factor) => factor.direction === "up")
    const delta = item.score - scaledScore(item.record, view.now - 6 * HOUR, view.horizon)
    const events = getDataset().eventsByAsset.get(item.record.id) ?? []
    const last = events.filter((event) => event.timestamp <= view.now && event.severity !== "info").at(-1)
    situations.push({
      id: `situation-${item.record.id}`,
      type: "risk",
      severity: statusFromScore(item.score) === "critical" ? "critical" : "warning",
      title: item.record.id,
      assetIds: [item.record.id],
      patternId: null,
      summary:
        delta > 0
          ? `Risk ${Math.round(item.score)}/100, +${Math.round(delta)} over the last 6 hours.`
          : `Risk ${Math.round(item.score)}/100, stable over the last 6 hours.`,
      changedAt: last?.timestamp ?? view.now,
      riskScore: item.score,
      delta: Math.round(delta),
      horizon: view.horizon,
      primaryReason: rising ? `${rising.label} ${rising.value}` : "Sustained abnormal state",
      status: "new",
    })
  }

  const order = { critical: 0, warning: 1 }
  return situations.sort((left, right) => order[left.severity] - order[right.severity] || right.changedAt - left.changedAt).slice(0, limit)
}

const SHIFT_HOURS = [8, 20]

function shiftStart(now: number) {
  const msk = now + 3 * HOUR
  const day = Math.floor(msk / (24 * HOUR)) * 24 * HOUR
  const hour = (msk - day) / HOUR
  const start = SHIFT_HOURS.filter((value) => value <= hour).pop() ?? SHIFT_HOURS[SHIFT_HOURS.length - 1]
  const base = start <= hour ? day + start * HOUR : day - 24 * HOUR + start * HOUR
  return base - 3 * HOUR
}

export async function getPulseSummary(view: View): Promise<PulseSummary> {
  const dataset = getDataset()
  const since = shiftStart(view.now)
  const online = dataset.assets.filter((record) => !isOffline(record, view.now))

  const scored = online.map((record) => {
    const score = scaledScore(record, view.now, view.horizon)
    const before = scaledScore(record, view.now - 6 * HOUR, view.horizon)
    const atShift = scaledScore(record, since, view.horizon)
    return { record, score, delta: score - before, shiftDelta: score - atShift }
  })

  const critical = scored.filter((item) => statusFromScore(item.score) === "critical").sort((left, right) => right.score - left.score)
  const rising = scored.filter((item) => item.delta >= 5).sort((left, right) => right.delta - left.delta)
  const topRising = rising[0] ?? null

  const pulse = await getPulse({ now: view.now, windowHours: 6 })
  const latest = pulse.patterns.at(-1) ?? null

  return {
    critical: {
      count: critical.length,
      assets: critical.slice(0, 2).map((item) => ({ id: item.record.id, score: Math.round(item.score) })),
    },
    rising: {
      count: rising.length,
      top: topRising ? { id: topRising.record.id, delta: Math.round(topRising.delta) } : null,
    },
    patterns: {
      count: pulse.patterns.length,
      latest: latest
        ? { id: latest.id, number: latest.number, systems: latest.systems.length, events: latest.events }
        : null,
    },
    shift: {
      since,
      critical: scored.filter(
        (item) => statusFromScore(item.score) === "critical" && statusFromScore(scaledScore(item.record, since, view.horizon)) !== "critical"
      ).length,
      patterns: pulse.patterns.filter((pattern) => pattern.start >= since).length,
      rising: scored.filter((item) => item.shiftDelta >= 5).length,
    },
  }
}
