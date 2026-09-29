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
  probability: number | null
  riskLevel: string
  picketM: number | null
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

export type ForecastDay = { day: string; expected: number }
export type BacktestDay = { day: string; actual: number; forecast: number }

export type EventTypeStats = {
  eventType: string
  title: string
  scenario: string
  models: string[]
  channelsAtRisk: Record<string, number>
  episodes30d: number | null
  episodes365d: number | null
  forecast: ForecastDay[]
  next7Days: { expected: number; low: number | null; high: number | null } | null
  weekError: number | null
  weekErrorBaseline: number | null
  backtest: BacktestDay[]
}

export type HealthPoint = { day: string; value: number }

export type MlModelHeldOut = {
  period: string
  baseRate: number | null
  avgPrecision: number | null
  rocAuc: number | null
  precisionTop5PerDay: number | null
  ece: number | null
}

export type MlModelLeadTime = {
  episodeRecall: number | null
  alertPrecisionDedup: number | null
  medianLeadTimeHours: number | null
  alertsPerDay: number | null
}

export type MlModel = {
  name: string
  scenario: string
  sensor: string | null
  target: string | null
  horizonHours: number
  recipe: string | null
  features: number | null
  trainYears: string | null
  version: string | null
  heldOut: MlModelHeldOut | null
  leadTime: MlModelLeadTime | null
  dailyTopK: Record<string, number> | null
}

export type AlarmChannelStat = {
  channelId: string
  name: string | null
  activations: number
}

export type AlarmKpisRecent = {
  start: string | null
  end: string | null
  activations: number
  perHourMean: number
  perHourP95: number | null
  floodShareOfTime: number | null
  activationsInFloods: number | null
  top10Share: number | null
  chatteringTop: AlarmChannelStat[]
  maintenanceShare: number | null
}

export type AlarmKpisMonth = {
  start: string
  end: string
  perHourMean: number
  activationsInFloods: number | null
}

export type AlarmKpis = {
  acceptablePerHour: number
  manageablePerHour: number
  recent: AlarmKpisRecent | null
  months: AlarmKpisMonth[]
}

export type InspectionPlanItem = {
  assetId: string
  name: string | null
  location: string | null
  modelId: string
  predictionId: string
  probability: number
  riskLevel: string
  reason: string | null
}

export type InspectionPlan = {
  modelId: string
  count: number
  skippedRecent: string[]
  items: InspectionPlanItem[]
}

export type TodaysInspectionPlan = {
  pumps: InspectionPlan
  fans: InspectionPlan
}

export type WeatherDay = {
  day: string
  precipitationMm: number | null
  thaw: boolean | null
}

export type WeatherReport = {
  source: string
  forecast: WeatherDay[]
  floodingVsWeather: Record<string, number>
}
