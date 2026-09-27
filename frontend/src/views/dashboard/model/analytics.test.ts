import { describe, expect, it } from "vitest"

import type { Asset } from "@/entities/infrastructure"
import type { MaintenanceAction } from "@/entities/maintenance"
import type { Prediction } from "@/entities/prediction"

import { dashboardRows, exportDashboardCsv, filterRows, summarizeDashboard } from "./analytics"

const asset: Asset = {
  id: "P-1",
  name: "Насос",
  type: "pump",
  group: "Север",
  channelId: "1",
  status: "critical",
  riskLevel: "high",
  riskScore: 90,
  scoreType: "risk_score",
  forecastHorizon: 72,
  lastEventAt: null,
}
const prediction: Prediction = {
  id: "snapshot:p1",
  assetId: "P-1",
  deviceType: "pump",
  modelId: "pump72",
  modelVersion: "v1",
  predictionTime: 1000,
  horizonHours: 72,
  score: 0.9,
  scoreType: "risk_score",
  riskLevel: "attention",
  modelRiskLevel: "high",
  scoreDelta: null,
  factors: [],
  sensorType: null,
  systemType: null,
  lastEventAt: null,
}

describe("dashboard analytics", () => {
  it("does not substitute demo assets when API predictions are absent", () => {
    expect(dashboardRows([asset], [], "api", 72, 1000)).toEqual([])
  })
  it("preserves model levels, horizons and unknown registry assets", () => {
    const rows = dashboardRows(
      [asset],
      [prediction, { ...prediction, id: "unmapped", assetId: "unknown" }, { ...prediction, id: "24h", horizonHours: 24 }],
      "api",
      72,
      1000
    )
    expect(rows).toHaveLength(2)
    expect(rows.every((row) => row.level === "attention" && row.scoreType === "risk_score")).toBe(true)
    expect(rows.find((row) => row.id === "unmapped")?.registered).toBe(false)
    expect(rows[0].score).toBe(90)
  })
  it("counts unique at-risk assets and only open actions covering them", () => {
    const rows = dashboardRows([], [prediction, { ...prediction, id: "p2" }, { ...prediction, id: "p3", assetId: "P-2" }], "api", 72, 1000)
    const actions = [
      { assetId: "P-1", status: "completed" },
      { assetId: "P-2", status: "planned" },
      { assetId: "other", status: "planned" },
    ] as MaintenanceAction[]
    const summary = summarizeDashboard(rows, actions)
    expect(summary.assets).toBe(2)
    expect(summary.forecasts).toBe(3)
    expect(summary.unassigned).toBe(1)
    expect(summary.open).toHaveLength(1)
    expect(summary.closed).toHaveLength(1)
  })
  it("combines search/system/risk filters without mutating input", () => {
    const rows = dashboardRows([asset], [], "demo", 72, 1000)
    expect(filterRows(rows, " север ", "pump", "critical")).toHaveLength(1)
    expect(filterRows(rows, "", "fan", "all")).toHaveLength(0)
    expect(rows).toHaveLength(1)
  })
  it("exports all filtered forecasts with source and escaped cells", () => {
    const rows = dashboardRows([{ ...asset, group: "=1+1", name: '"Имя"' }], [], "demo", 72, 1000)
    const csv = exportDashboardCsv(rows, "demo")
    expect(csv).toContain('"demo"')
    expect(csv).toContain('"\'=1+1"')
    expect(csv).toContain('"90.00/100"')
    expect(csv).not.toContain("90.00%")
  })
})
