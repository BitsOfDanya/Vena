export type SeasonalityRow = { scenario: string; months: number[] }

export type Seasonality = { rows: SeasonalityRow[]; weather: Record<string, number> }

export const SEASONALITY_LABEL: Record<string, string> = {
  flooding: "Затопление камер",
  pump_fault: "Отказ насоса",
  ventilation_fault: "Отказ вентилятора",
  smoke_sensor_fault: "Неисправность датчика дыма",
  smoke_detected: "Обнаружение дыма",
  power_loss: "Потеря питания",
}

export type ProspectiveModel = {
  forecasts: number
  eventRate: number
  meanProbability: number
  brier: number
  alerts: number
  alertPrecision: number | null
  episodes: number
  episodesWarned: number
  episodeRecall: number | null
}

export type Prospective = { start: number; now: number; models: Record<string, ProspectiveModel> }

export type ModelEffect = {
  modelId: string
  level: string
  episodeRecall: number | null
  alertPrecision: number | null
  medianLeadTimeHours: number | null
  alertsPerDay: number | null
}

export type EffectReport = {
  channelsAtRisk: number
  incidents: number
  leadTime: ModelEffect[]
  alarms30d: number
  alarmsToVerify: number
  alarmFilterShare: number | null
  accessEvents30d: number
  forecastsInJournal: number
  decided: number
  confirmed: number
  rejected: number
  dispatchesAvoided: number
}

export type ChannelNode = {
  assetId: string
  name: string | null
  sensorType: string | null
  scenario: string
  modelId: string
  probability: number
  riskLevel: string
}

export type SectionNode = {
  group: string
  label: string | null
  healthIndex: number | null
  mainScenario: string | null
  riskByScenario: Record<string, number>
  channels: ChannelNode[]
}

export type ObjectNode = {
  objectId: string
  label: string
  healthIndex: number | null
  sections: SectionNode[]
}

export type EventTypeStats = {
  eventType: string
  title: string
  scenario: string
  channelsAtRisk: Record<string, number>
  episodes30d: number | null
  episodes365d: number | null
  next7DaysExpected: number | null
}
