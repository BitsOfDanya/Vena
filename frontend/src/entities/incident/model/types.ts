export type IncidentKind = "power" | "flood" | "fire"

export type YearCount = { year: string; count: number }

export type ObjectCount = {
  objectId: string
  objectName: string
  count: number
}

export type IncidentKindSummary = {
  kind: IncidentKind
  label: string
  rule: string
  total: number
  objects: number
  perYear: YearCount[]
  recent2026h1: number | null
  perDay2026h1: number | null
  channelsMedian: number | null
  topObjects: ObjectCount[]
  temperatureConfirmed: number | null
  longOver30Minutes: number | null
}

export type IncidentRecord = {
  kind: IncidentKind
  label: string
  objectId: string
  objectName: string
  start: number
  end: number | null
  channels: number | null
  temperatureConfirmed: boolean | null
  maxMinutes: number | null
}

export type IncidentRegistry = {
  available: boolean
  detail: string
  journalEnd: string | null
  restricted: boolean
  kinds: IncidentKindSummary[]
  recent: IncidentRecord[]
}

export type ObjectRiskScenario = "power_loss" | "flooding" | "fire"

export type ObjectHistory = {
  events1d: number | null
  events7d: number | null
  events30d: number | null
  events90d: number | null
  daysSince: number | null
}

export type ObjectRisk = {
  objectId: string
  objectName: string
  scenario: string
  modelId: string
  modelLabel: string
  probability: number
  rank: number
  horizonHours: number | null
  history: ObjectHistory
  channelScore: number | null
  probability6h: number | null
}

export type ObjectNowcastMeta = {
  modelId: string
  horizonHours: number
  period: string | null
  shareTop3: number | null
  ruleShareTop3: number | null
  objects: number | null
}

export type ObjectModelMeta = {
  modelId: string
  label: string
  scenario: string
  precisionTop3: number | null
  baseRate: number | null
  avgPrecision: number | null
  period: string | null
  rule: string
  nowcast: ObjectNowcastMeta | null
}

export type ObjectRiskList = {
  available: boolean
  detail: string
  predictionTime: number | null
  restricted: boolean
  models: ObjectModelMeta[]
  items: ObjectRisk[]
}
