import { afterEach, describe, expect, it, vi } from "vitest"

import { getAssetPrediction, getBackendSituations, getDashboardPredictions, getPredictionSummary, getPredictions, getSnapshotStatus } from "./service"
import { invalidateHorizonPages } from "@/shared/api/horizon-pages"

function mockFetch(handler: (url: string) => { status?: number; body: unknown }) {
  const calls: string[] = []
  vi.stubGlobal("fetch", async (url: string) => {
    calls.push(url)
    const { status = 200, body } = handler(url)
    return { ok: status < 400, status, statusText: "", json: async () => body } as Response
  })
  return calls
}

const prediction = {
  id: "snap-1:pump_72h:333742",
  asset_id: "333742",
  device_type: "pump",
  model_id: "pump_72h",
  model_version: "2026-09-16",
  prediction_time: "2026-06-30T23:59:06Z",
  horizon_hours: 72,
  score: 0.9932,
  score_type: "risk_score",
  risk_level: "attention",
  model_risk_level: "high",
  score_delta: null,
  factors: [{ key: "events_7d", label: "Events, 7d", value: 409 }],
  sensor_type: "Состояние насоса",
  system_type: "Водоотведение",
  last_event_at: "2026-06-30T23:00:00Z",
}

afterEach(() => {
  vi.unstubAllGlobals()
  invalidateHorizonPages()
})

describe("prediction service", () => {
  const status = {
    available: true,
    snapshot_id: "snap-1",
    prediction_time: prediction.prediction_time,
    age_seconds: 1,
    stale: false,
    prediction_count: 501,
    models: [],
    detail: "",
  }

  it("loads every dashboard page with the selected horizon", async () => {
    const first = Array.from({ length: 5000 }, (_, i) => ({ ...prediction, id: `prediction-${i}` }))
    const calls = mockFetch((url) => ({
      body: url.endsWith("/snapshot") ? status : url.includes("offset=5000") ? [{ ...prediction, id: "last" }] : first,
    }))
    const result = await getDashboardPredictions(72)
    expect(result).toHaveLength(5001)
    expect(calls.filter((url) => !url.endsWith("/snapshot"))).toEqual([
      expect.stringContaining("horizon=72&sort=risk_desc&limit=5000&offset=0"),
      expect.stringContaining("horizon=72&sort=risk_desc&limit=5000&offset=5000"),
    ])
  })

  it("groups power-supply predictions under the power asset type", async () => {
    const phase = { ...prediction, id: "snap-1:phase_24h:179172", device_type: "phase", model_id: "phase_24h", horizon_hours: 24 }
    mockFetch((url) => ({ body: url.endsWith("/snapshot") ? status : [phase] }))
    const [result] = await getDashboardPredictions(24)
    expect(result.deviceType).toBe("power")
  })

  it("rejects a failed page instead of returning partial counts", async () => {
    const first = Array.from({ length: 5000 }, (_, i) => ({ ...prediction, id: `prediction-${i}` }))
    mockFetch((url) =>
      url.endsWith("/snapshot") ? { body: status } : url.includes("offset=5000") ? { status: 503, body: {} } : { body: first }
    )
    await expect(getDashboardPredictions(72)).rejects.toMatchObject({ status: 503 })
  })

  it("rejects mixed horizons and malformed scores", async () => {
    mockFetch((url) => ({ body: url.endsWith("/snapshot") ? status : [prediction] }))
    await expect(getDashboardPredictions(24)).rejects.toThrow("Inconsistent")
    mockFetch((url) => ({ body: url.endsWith("/snapshot") ? status : [{ ...prediction, score: 120 }] }))
    await expect(getDashboardPredictions(72)).rejects.toThrow()
  })

  it("rejects a snapshot replaced while pages were loading", async () => {
    let reads = 0
    mockFetch((url) => ({
      body: url.endsWith("/snapshot") ? { ...status, snapshot_id: ++reads === 1 ? "snap-1" : "snap-2" } : [prediction],
    }))
    await expect(getDashboardPredictions(72)).rejects.toThrow("Snapshot changed")
  })
  it("loads a lightweight prediction summary without paging", async () => {
    mockFetch(() => ({
      body: {
        horizon_hours: 24,
        total: 12,
        counts: { critical: 2, attention: 3, observe: 4, normal: 3 },
        top_critical: [{ ...prediction, id: "c1", risk_level: "critical", horizon_hours: 24 }],
        top_attention: [{ ...prediction, id: "a1", risk_level: "attention", horizon_hours: 24 }],
      },
    }))
    const summary = await getPredictionSummary(24, 5)
    expect(summary.total).toBe(12)
    expect(summary.counts.critical).toBe(2)
    expect(summary.topCritical[0].id).toBe("c1")
    expect(summary.topAttention[0].id).toBe("a1")
  })

  it("maps a backend prediction without inventing a probability", async () => {
    mockFetch(() => ({ body: [prediction] }))

    const [item] = await getPredictions({ limit: 1 })

    expect(item.assetId).toBe("333742")
    expect(item.scoreType).toBe("risk_score")
    expect(item.riskLevel).toBe("attention")
    expect(item.modelRiskLevel).toBe("high")
    expect(item.score).toBeCloseTo(0.9932)
    expect(item.factors[0].label).toBe("Events, 7d")
  })

  it("passes sorting and risk filters to the API", async () => {
    const calls = mockFetch(() => ({ body: [] }))

    await getPredictions({ sort: "delta_desc", riskLevel: "critical", limit: 5 })

    expect(calls[0]).toContain("sort=delta_desc")
    expect(calls[0]).toContain("risk_level=critical")
    expect(calls[0]).toContain("limit=5")
  })

  it("propagates an unavailable snapshot instead of falling back to demo data", async () => {
    mockFetch(() => ({ status: 503, body: { detail: "prediction snapshot is not available" } }))

    await expect(getPredictions()).rejects.toMatchObject({ status: 503 })
  })

  it("reports snapshot freshness", async () => {
    mockFetch(() => ({
      body: {
        available: true,
        snapshot_id: "snap-1",
        prediction_time: "2026-06-30T23:59:06Z",
        age_seconds: 7_200_000,
        stale: true,
        prediction_count: 5405,
        models: [{ model_id: "pump_72h", model_version: "2026-09-16", horizon_hours: 72, calibrated: false }],
        detail: "",
      },
    }))

    const status = await getSnapshotStatus()

    expect(status.stale).toBe(true)
    expect(status.predictionCount).toBe(5405)
    expect(status.models[0].calibrated).toBe(false)
  })

  it("maps backend situations with their linkage", async () => {
    mockFetch(() => ({
      body: [
        {
          id: "situation-1",
          type: "risk",
          severity: "attention",
          title: "333742",
          summary: "pump_72h score 0.993",
          asset_ids: ["333742"],
          pattern_id: null,
          risk_score: 0.993,
          risk_delta: null,
          forecast_horizon: 72,
          primary_reason: "Events, 7d 409",
          status: "new",
          updated_at: "2026-06-30T23:59:06Z",
          open_action_id: null,
          notification_id: "N-1",
        },
      ],
    }))

    const [situation] = await getBackendSituations()

    expect(situation.assetIds).toEqual(["333742"])
    expect(situation.notificationId).toBe("N-1")
    expect(situation.forecastHorizon).toBe(72)
  })

  it("returns null when an asset has no prediction", async () => {
    mockFetch(() => ({ status: 404, body: { detail: "prediction not found for asset" } }))

    await expect(getAssetPrediction("unknown")).resolves.toBeNull()
  })
})
