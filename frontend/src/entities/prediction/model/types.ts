export type PredictionRiskLevel = "critical" | "attention" | "observe" | "normal"
export type PredictionScoreType = "risk_score" | "calibrated_probability"

/** Incident scenario a device model forecasts; `equipment` covers unknown devices. */
export type PredictionScenario = "flooding" | "fire" | "power_loss" | "ventilation" | "equipment"

/** Feature that raised this forecast the most, with its log-odds contribution. */
export type PredictionDriver = {
  feature: string
  label: string
  value: number | null
  contribution: number
}

export type PredictionFactor = {
  key: string
  label: string
  value: number
}

export type Prediction = {
  id: string
  assetId: string
  deviceType: string
  modelId: string
  modelVersion: string | null
  predictionTime: number
  horizonHours: number | null
  score: number
  scoreType: PredictionScoreType
  riskLevel: PredictionRiskLevel
  modelRiskLevel: string
  scoreDelta: number | null
  factors: PredictionFactor[]
  sensorType: string | null
  systemType: string | null
  lastEventAt: number | null
  scenario: PredictionScenario
  location: string | null
  locationTag: string | null
  drivers: PredictionDriver[]
}

export type SnapshotStatus = {
  available: boolean
  snapshotId: string | null
  predictionTime: number | null
  ageSeconds: number | null
  stale: boolean
  predictionCount: number
  models: { modelId: string; modelVersion: string | null; horizonHours: number | null; calibrated: boolean }[]
  /** Last stream batch: events, channels rescored and seconds from the API to the published snapshot. */
  stream: { events: number; channelsRescored: number; publishedAt: number; latencySeconds: number } | null
  detail: string
}

export type BackendSituation = {
  id: string
  type: "risk" | "pattern" | "action"
  severity: "critical" | "attention"
  title: string
  summary: string
  assetIds: string[]
  patternId: string | null
  riskScore: number | null
  riskDelta: number | null
  forecastHorizon: number | null
  primaryReason: string
  status: "new" | "acknowledged" | "action_created" | "resolved"
  updatedAt: number
  openActionId: string | null
  notificationId: string | null
  scenario: PredictionScenario | null
  location: string | null
  assetCount: number
  incidentProbability: number | null
}
