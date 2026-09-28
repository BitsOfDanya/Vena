import { z } from "zod"

import { apiFetch } from "@/shared/api/http"

import type { AccessEvent, AlarmAssessment } from "../model/types"

const time = z.iso.datetime({ offset: true }).or(z.iso.datetime({ local: true }))

const AlarmSchema = z.object({
  channel_id: z.string(),
  ts: time,
  sensor_type: z.string(),
  corroboration_probability: z.number().min(0).max(1),
  needs_verification: z.boolean(),
  location: z.string().nullable(),
  name: z.string().nullable(),
})

const AccessSchema = z.object({
  channel_id: z.string(),
  ts: time,
  sensor_type: z.string(),
  object: z.string(),
  access_index: z.number(),
  night: z.boolean(),
  chain: z.boolean(),
  location: z.string().nullable(),
  name: z.string().nullable(),
})

export async function getAlarms(): Promise<AlarmAssessment[]> {
  const items = z.array(AlarmSchema).parse(await apiFetch<unknown>("/api/v1/alarms?limit=20000"))
  return items.map((item) => ({
    channelId: item.channel_id,
    ts: Date.parse(item.ts),
    sensorType: item.sensor_type,
    corroborationProbability: item.corroboration_probability,
    needsVerification: item.needs_verification,
    location: item.location,
    name: item.name,
  }))
}

export async function getAccessEvents(): Promise<AccessEvent[]> {
  const items = z.array(AccessSchema).parse(await apiFetch<unknown>("/api/v1/access-events?limit=20000"))
  return items.map((item) => ({
    channelId: item.channel_id,
    ts: Date.parse(item.ts),
    sensorType: item.sensor_type,
    object: item.object,
    accessIndex: item.access_index,
    night: item.night,
    chain: item.chain,
    location: item.location,
    name: item.name,
  }))
}
