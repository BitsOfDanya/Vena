export type AlarmAssessment = {
  channelId: string
  ts: number
  sensorType: string
  corroborationProbability: number
  needsVerification: boolean
  maintenance: boolean
  category: string
  location: string | null
  name: string | null
}

export type RouteStep = {
  ts: number
  channelId: string
  name: string | null
  picket: number
  sensorType: string
}

export type AccessRoute = {
  object: string
  start: number
  end: number
  direction: "increasing" | "decreasing" | "mixed"
  distanceM: number
  speedMPerMin: number | null
  maxIndex: number
  night: boolean
  steps: RouteStep[]
}

export type AccessEvent = {
  channelId: string
  ts: number
  sensorType: string
  object: string
  accessIndex: number
  night: boolean
  chain: boolean
  location: string | null
  name: string | null
}
