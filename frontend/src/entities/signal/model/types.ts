export type AlarmAssessment = {
  channelId: string
  ts: number
  sensorType: string
  /** Calibrated probability that the alarm is confirmed within 30 minutes. */
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
  /** Triage index for verification, not a probability of intrusion. */
  accessIndex: number
  night: boolean
  chain: boolean
  location: string | null
  name: string | null
}
