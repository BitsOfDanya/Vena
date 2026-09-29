export type AlarmAssessment = {
  channelId: string
  ts: number
  sensorType: string
  corroborationProbability: number
  needsVerification: boolean
  location: string | null
  name: string | null
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
