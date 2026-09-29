export type AssetType = "pump" | "fan" | "smoke" | "power" | "other"
export type AssetStatus = "normal" | "attention" | "critical" | "offline"
export type RiskLevel = "low" | "medium" | "high"
export type ScoreType = "risk_score" | "calibrated_probability"
export type ForecastHorizon = 24 | 72
export type RelationType = "physical" | "logical" | "group"
export type EventType = "transition" | "state_change" | "alarm" | "anomaly" | "failure" | "signal"
export type EventSeverity = "info" | "warning" | "critical"
export type StateKind = "normal" | "abnormal" | "offline"
export type FactorDirection = "up" | "down" | "flat"
export type FactorBasis = "rule_based" | "model_contribution"

export type Asset = {
  id: string
  name: string
  type: AssetType
  group: string
  channelId: string
  status: AssetStatus
  riskLevel: RiskLevel
  riskScore: number
  scoreType: ScoreType
  forecastHorizon: ForecastHorizon
  lastEventAt: number | null
  predictionId?: string | null
  predictionModelId?: string | null
}

export type RiskSnapshot = {
  assetId: string
  timestamp: number
  score: number
  level: RiskLevel
  horizon: ForecastHorizon
  scoreType: ScoreType
}

export type SensorEvent = {
  id: string
  assetId: string
  timestamp: number
  type: EventType
  state: string
  severity: EventSeverity
}

export type RiskFactor = {
  key: string
  label: string
  value: string
  direction: FactorDirection
  basis: FactorBasis
}

export type FactorGroup = {
  key: string
  label: string
  points: number
}

export type NetworkNode = {
  id: string
  assetId: string
  group: string
  type: AssetType
  status: AssetStatus
  risk: number
  x: number
  y: number
}

export type NetworkEdge = {
  source: string
  target: string
  relationType: RelationType
}

export type NetworkGroup = {
  id: string
  name: string
  system: string
  x: number
  y: number
  maxRisk: number
}

export type NetworkModel = {
  nodes: NetworkNode[]
  edges: NetworkEdge[]
  groups: NetworkGroup[]
  width: number
  height: number
}

export type PulseCluster = {
  id: string
  start: number
  end: number
  systemType: AssetType
  assetIds: string[]
  transitions: number
  riskDelta: number
  summary: string
}

export type PulseEvent = {
  id: string
  assetId: string
  timestamp: number
  severity: EventSeverity
  type: EventType
}

export type PulseSustained = {
  assetId: string
  from: number
  to: number
  label: string
}

export type PulseLane = {
  type: AssetType
  events: PulseEvent[]
  sustained: PulseSustained[]
}

export type PulsePattern = {
  id: string
  number: number
  start: number
  end: number
  clusterIds: string[]
  systems: AssetType[]
  events: number
  assetIds: string[]
  riskDelta: number
}

export type PulseCounts = {
  critical: number
  attention: number
  watch: number
  newIncidents: number
}

export type PulseData = {
  now: number
  from: number
  windowHours: number
  lanes: PulseLane[]
  density: { timestamp: number; weight: number }[]
  systemRisk: { timestamp: number; score: number }[]
  clusters: PulseCluster[]
  patterns: PulsePattern[]
  counts: PulseCounts
  systemState: "stable" | "degraded"
  recent: SensorEvent[]
}

export type StateSegment = {
  from: number
  to: number
  state: StateKind
  label: string
}

export type ForecastPoint = {
  timestamp: number
  low: number
  mid: number
  high: number
}

export type ReplayEpisode = {
  id: string
  label: string
  assetId: string
  start: number
  end: number
}

export type AssetDetail = {
  asset: Asset
  delta: number
  deltaSince: number
  factors: RiskFactor[]
  factorGroups: FactorGroup[]
  recent: SensorEvent[]
}

export type TemporalBundle = {
  asset: Asset
  events: SensorEvent[]
  states: StateSegment[]
  history: RiskSnapshot[]
  forecast: ForecastPoint[]
}

export type SituationType = "risk" | "pattern"
export type SituationStatus = "new" | "acknowledged" | "action_created" | "resolved"

export type Situation = {
  id: string
  type: SituationType
  severity: "critical" | "warning"
  title: string
  assetIds: string[]
  patternId: string | null
  summary: string
  changedAt: number
  riskScore: number | null
  scoreText: string | null
  delta: number | null
  horizon: ForecastHorizon | null
  primaryReason: string
  status: SituationStatus
}

export type PulseSummary = {
  critical: { count: number; assets: { id: string; score: number }[] }
  rising: { count: number; top: { id: string; delta: number } | null }
  patterns: { count: number; latest: { id: string; number: number; systems: number; events: number } | null }
  shift: { since: number; critical: number; patterns: number; rising: number }
}
