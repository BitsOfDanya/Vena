import { afterEach, describe, expect, it, vi } from "vitest"

import { getAssetPrediction, getBackendSituations, getPredictions, getSnapshotStatus } from "./service"

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
})

describe("prediction service", () => {
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
