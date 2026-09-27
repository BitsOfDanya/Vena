import { TYPE_LABEL, type Asset, type AssetType, type ForecastHorizon, type ScoreType } from "@/entities/infrastructure"
import { OPEN_STATUSES, STATUS_LABEL, type MaintenanceAction } from "@/entities/maintenance"
import type { Prediction, PredictionRiskLevel } from "@/entities/prediction"

export type DashboardLevel = PredictionRiskLevel | "offline"
export type DashboardRow = {
  id: string
  assetId: string
  name: string
  group: string
  type: AssetType
  level: DashboardLevel
  score: number
  scoreType: ScoreType
  horizon: ForecastHorizon
  time: number
  factors: string[]
  modelId: string | null
  predictionId: string | null
  registered: boolean
}

const rank: Record<DashboardLevel, number> = { critical: 4, attention: 3, observe: 2, normal: 1, offline: 0 }
const types = new Set(["pump", "fan", "smoke", "power", "other"])

export type DashboardSortKey = "asset" | "system" | "risk" | "score" | "horizon" | "response"
export type DashboardSort = { key: DashboardSortKey; direction: "asc" | "desc" }
const collator = new Intl.Collator("ru", { numeric: true, sensitivity: "base" })

export function responseLabels(actions: MaintenanceAction[]): Map<string, string> {
  const grouped = new Map<string, MaintenanceAction[]>()
  for (const action of actions) {
    const list = grouped.get(action.assetId) ?? []
    list.push(action)
    grouped.set(action.assetId, list)
  }
  return new Map([...grouped].map(([id, list]) => [id, `${STATUS_LABEL[list[0].status]}${list.length > 1 ? ` +${list.length - 1}` : ""}`]))
}

/** Sort the complete filtered set before pagination; unavailable scores always go last. */
export function sortDashboardRows(rows: DashboardRow[], sort: DashboardSort, responses: Map<string, string> = new Map()) {
  const direction = sort.direction === "asc" ? 1 : -1
  return [...rows].sort((left, right) => {
    let difference = 0
    switch (sort.key) {
      case "asset":
        difference = collator.compare(left.assetId, right.assetId) || collator.compare(left.group, right.group)
        break
      case "system":
        difference = collator.compare(TYPE_LABEL[left.type], TYPE_LABEL[right.type])
        break
      case "risk":
        difference = rank[left.level] - rank[right.level] || left.score - right.score
        break
      case "score":
        if ((left.level === "offline") !== (right.level === "offline")) return left.level === "offline" ? 1 : -1
        difference = left.level === "offline" ? 0 : left.score - right.score
        break
      case "horizon":
        difference = left.horizon - right.horizon
        break
      case "response":
        difference = collator.compare(responses.get(left.assetId) ?? "No open action", responses.get(right.assetId) ?? "No open action")
        break
    }
    return difference * direction || collator.compare(left.assetId, right.assetId) || collator.compare(left.id, right.id)
  })
}

export function dashboardRows(
  assets: Asset[],
  predictions: Prediction[],
  mode: "demo" | "api",
  horizon: ForecastHorizon,
  now: number
): DashboardRow[] {
  const registry = new Map(assets.map((asset) => [asset.id, asset]))
  const rows: DashboardRow[] =
    mode === "api"
      ? predictions
          .filter((item) => item.horizonHours === horizon)
          .map((item) => {
            const asset = registry.get(item.assetId)
            return {
              id: item.id,
              assetId: item.assetId,
              name: asset?.name ?? item.assetId,
              group: asset?.group ?? "Not in registry",
              type: types.has(item.deviceType) ? (item.deviceType as AssetType) : "other",
              level: item.riskLevel,
              score: item.score * 100,
              scoreType: item.scoreType,
              horizon,
              time: item.predictionTime,
              factors: item.factors.map((factor) => `${factor.label}: ${factor.value}`),
              modelId: item.modelId,
              predictionId: item.id,
              registered: Boolean(asset),
            }
          })
      : assets.map((asset) => ({
          id: `demo:${asset.id}:${horizon}`,
          assetId: asset.id,
          name: asset.name,
          group: asset.group,
          type: asset.type,
          level: asset.status,
          score: asset.riskScore,
          scoreType: asset.scoreType,
          horizon,
          time: now,
          factors: [],
          modelId: null,
          predictionId: null,
          registered: true,
        }))
  return rows.sort((a, b) => rank[b.level] - rank[a.level] || b.score - a.score || a.id.localeCompare(b.id))
}

export function filterRows(rows: DashboardRow[], query: string, system: string, level: string) {
  const needle = query.trim().toLocaleLowerCase("ru-RU")
  return rows.filter(
    (row) =>
      (system === "all" || row.type === system) &&
      (level === "all" || row.level === level) &&
      (!needle || [row.assetId, row.name, row.group, row.modelId].join(" ").toLocaleLowerCase("ru-RU").includes(needle))
  )
}

export function summarizeDashboard(rows: DashboardRow[], actions: MaintenanceAction[]) {
  const assets = new Set(rows.map((row) => row.assetId))
  const counts: Record<DashboardLevel, number> = { critical: 0, attention: 0, observe: 0, normal: 0, offline: 0 }
  for (const row of rows) counts[row.level] += 1
  const related = actions.filter((action) => assets.has(action.assetId))
  const open = related.filter((action) => OPEN_STATUSES.includes(action.status))
  const covered = new Set(open.map((action) => action.assetId))
  const atRisk = new Set(rows.filter((row) => row.level === "critical" || row.level === "attention").map((row) => row.assetId))
  return {
    counts,
    assets: assets.size,
    forecasts: rows.length,
    open,
    unassigned: [...atRisk].filter((id) => !covered.has(id)).length,
    closed: related.filter((action) => action.status === "completed" || action.status === "cancelled"),
  }
}

export function exportDashboardCsv(rows: DashboardRow[], mode: "demo" | "api") {
  const values = [
    [
      "Source",
      "Prediction",
      "Asset",
      "Group",
      "System",
      "Risk level",
      "Score",
      "Score type",
      "Horizon (h)",
      "Prediction time (UTC)",
      "Model",
    ],
    ...rows.map((row) => [
      mode,
      row.id,
      row.assetId,
      row.group,
      row.type,
      row.level,
      row.scoreType === "calibrated_probability" ? `${row.score.toFixed(2)}%` : `${row.score.toFixed(2)}/100`,
      row.scoreType,
      row.horizon,
      new Date(row.time).toISOString(),
      row.modelId ?? "demo",
    ]),
  ]
  return (
    "\ufeff" +
    values
      .map((row) =>
        row
          .map((value) => {
            const text = String(value)
            const safe = /^[\s]*[=+@-]/u.test(text) ? "'" + text : text
            return `"${safe.replaceAll('"', '""')}"`
          })
          .join(";")
      )
      .join("\r\n")
  )
}
