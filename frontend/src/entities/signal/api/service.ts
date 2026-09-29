import { z } from "zod"

import { apiFetch } from "@/shared/api/http"

import type { AccessEvent, AccessRoute, AlarmAssessment } from "../model/types"

const time = z.iso.datetime({ offset: true }).or(z.iso.datetime({ local: true }))

const AlarmSchema = z.object({
  channel_id: z.string(),
  ts: time,
  sensor_type: z.string(),
  corroboration_probability: z.number().min(0).max(1),
  needs_verification: z.boolean(),
  maintenance: z.boolean().default(false),
  category: z.string().default("fire"),
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
    maintenance: item.maintenance,
    category: item.category,
    location: item.location,
    name: item.name,
  }))
}

const RouteSchema = z.object({
  object: z.string(),
  start: time,
  end: time,
  direction: z.enum(["increasing", "decreasing", "mixed"]),
  distance_m: z.number(),
  speed_m_per_min: z.number().nullable(),
  max_index: z.number(),
  night: z.boolean(),
  steps: z.array(
    z.object({ ts: time, channel_id: z.string(), name: z.string().nullable(), picket: z.number(), sensor_type: z.string() }),
  ),
})

export async function getAccessRoutes(): Promise<AccessRoute[]> {
  const items = z.array(RouteSchema).parse(await apiFetch<unknown>("/api/v1/access-routes"))
  return items.map((item) => ({
    object: item.object,
    start: Date.parse(item.start),
    end: Date.parse(item.end),
    direction: item.direction,
    distanceM: item.distance_m,
    speedMPerMin: item.speed_m_per_min,
    maxIndex: item.max_index,
    night: item.night,
    steps: item.steps.map((step) => ({
      ts: Date.parse(step.ts),
      channelId: step.channel_id,
      name: step.name,
      picket: step.picket,
      sensorType: step.sensor_type,
    })),
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
