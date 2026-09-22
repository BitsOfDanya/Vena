import { describe, expect, it } from "vitest"

import { HOUR, MINUTE } from "@/shared/lib/time"

import { DEMO_NOW, getDataset } from "../data/demo"
import { getAsset, getForecast, getNetwork, getPulse, getRiskHistory } from "./service"

const view = { now: DEMO_NOW, horizon: 72 as const }

describe("demo dataset", () => {
  it("is deterministic across builds", () => {
    const first = getDataset()
    expect(first.assets.length).toBeGreaterThan(120)
    expect(getDataset()).toBe(first)
    expect(first.events.length).toBeGreaterThan(5000)
  })

  it("matches the documented status distribution at NOW", async () => {
    const network = await getNetwork(view)
    const count = (status: string) => network.nodes.filter((node) => node.status === status).length
    expect(count("critical")).toBe(3)
    expect(count("attention")).toBe(12)
    expect(count("offline")).toBe(6)
    const pump = network.nodes.find((node) => node.id === "P-0142")
    expect(pump?.risk).toBe(68)
  })

  it("never labels a logical grouping as a physical connection", async () => {
    const network = await getNetwork(view)
    expect(network.edges.every((edge) => edge.relationType !== "physical")).toBe(true)
    expect(network.edges.some((edge) => edge.relationType === "logical")).toBe(true)
  })

  it("keeps every node inside the canvas", async () => {
    const network = await getNetwork(view)
    for (const node of network.nodes) {
      expect(node.x).toBeGreaterThan(0)
      expect(node.x).toBeLessThan(network.width)
      expect(node.y).toBeGreaterThan(0)
      expect(node.y).toBeLessThan(network.height)
    }
  })
})

describe("time-consistent views", () => {
  it("does not expose events or risk after the requested moment", async () => {
    const at = Date.UTC(2026, 8, 17, 6, 40)
    const detail = await getAsset("P-0142", { now: at, horizon: 72 })
    expect(detail?.recent.every((event) => event.timestamp <= at)).toBe(true)
    const history = await getRiskHistory("P-0142", at - 24 * HOUR, at, 72)
    expect(history.every((point) => point.timestamp <= at)).toBe(true)
    const pulse = await getPulse({ now: at, windowHours: 6 })
    expect(pulse.recent.every((event) => event.timestamp <= at)).toBe(true)
    expect(pulse.lanes.every((lane) => lane.events.every((event) => event.timestamp <= at))).toBe(true)
  })

  it("keeps the replay failure invisible until its timestamp", async () => {
    const episode = getDataset().episode
    const before = await getPulse({ now: Date.UTC(2026, 8, 17, 10, 20), windowHours: 12 })
    expect(before.recent.some((event) => event.state === "Неисправен" && event.assetId === episode.assetId)).toBe(false)
    const after = await getPulse({ now: episode.end, windowHours: 12 })
    expect(after.recent.some((event) => event.type === "failure" && event.assetId === episode.assetId)).toBe(true)
  })

  it("derives the forecast only from history at NOW", async () => {
    const at = Date.UTC(2026, 8, 17, 5, 0)
    const forecast = await getForecast("P-0142", at, 72)
    expect(forecast[0].timestamp).toBe(at)
    expect(forecast[forecast.length - 1].timestamp).toBe(at + 72 * HOUR)
    expect(forecast.every((point) => point.low <= point.mid && point.mid <= point.high)).toBe(true)
    const later = await getForecast("P-0142", Date.UTC(2026, 8, 17, 10, 0), 72)
    expect(later[0].mid).toBeGreaterThan(forecast[0].mid)
  })

  it("reports the risk change since the previous full hour boundary", async () => {
    const detail = await getAsset("P-0142", view)
    expect(detail?.delta).toBe(17)
    expect(detail?.deltaSince).toBe(Date.UTC(2026, 8, 21, 15, 0))
    expect(detail?.factorGroups.reduce((sum, group) => sum + group.points, 0)).toBe(68)
  })
})

describe("pulse", () => {
  it("finds the correlated pump cluster ending at NOW", async () => {
    const pulse = await getPulse({ now: DEMO_NOW, windowHours: 6 })
    const cluster = pulse.clusters.filter((item) => item.systemType === "pump").at(-1)
    expect(cluster).toBeDefined()
    expect(cluster?.transitions).toBeGreaterThanOrEqual(7)
    expect(DEMO_NOW - (cluster?.end ?? 0)).toBeLessThan(10 * MINUTE)
    expect(pulse.counts.critical).toBe(3)
    expect(pulse.counts.newIncidents).toBe(1)
    expect(pulse.systemState).toBe("degraded")
  })

  it("groups clusters from different systems into numbered patterns", async () => {
    const pulse = await getPulse({ now: DEMO_NOW, windowHours: 6 })
    expect(pulse.patterns.length).toBeGreaterThan(0)
    for (const pattern of pulse.patterns) {
      expect(pattern.systems.length).toBeGreaterThanOrEqual(2)
      expect(pattern.number).toBeGreaterThan(0)
      expect(pattern.end).toBeLessThanOrEqual(DEMO_NOW)
    }
  })

  it("never reveals events after the requested time", async () => {
    const earlier = DEMO_NOW - 3 * HOUR
    const pulse = await getPulse({ now: earlier, windowHours: 6 })
    const stamps = pulse.lanes.flatMap((lane) => [...lane.events.map((event) => event.timestamp), ...lane.sustained.map((item) => item.to)])
    expect(Math.max(...stamps)).toBeLessThanOrEqual(earlier)
  })
})
