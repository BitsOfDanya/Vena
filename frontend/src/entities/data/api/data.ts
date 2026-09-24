import { z } from "zod"

import { apiFetch } from "@/shared/api/http"

const summarySchema = z.object({
  objects: z.number(), channels: z.number(), events: z.number(), imports: z.number(),
  last_event_at: z.string().nullable(),
})
const activitySchema = z.object({ day: z.string(), count: z.number() })
const eventSchema = z.object({
  id: z.number(), source_record_id: z.string(), channel_id: z.string(),
  channel_type: z.string(), value_raw: z.string(), value_numeric: z.number().nullable(),
  occurred_at: z.string(),
})
const objectSchema = z.object({ id: z.string(), name: z.string(), system_name: z.string(), tag: z.string() })
const channelSchema = z.object({ id: z.string(), object_tag: z.string(), channel_type: z.string(), display_name: z.string() })

export type DataSummary = z.infer<typeof summarySchema>
export type ActivityPoint = z.infer<typeof activitySchema>
export type DataEvent = z.infer<typeof eventSchema>
export type DataObject = z.infer<typeof objectSchema>
export type DataChannel = z.infer<typeof channelSchema>

export async function getDataSummary(): Promise<DataSummary> {
  return summarySchema.parse(await apiFetch<unknown>("/api/v1/data/summary"))
}
export async function getDataActivity(): Promise<ActivityPoint[]> {
  return z.array(activitySchema).parse(await apiFetch<unknown>("/api/v1/data/activity"))
}
export async function getDataEvents(): Promise<DataEvent[]> {
  return z.array(eventSchema).parse(await apiFetch<unknown>("/api/v1/data/events?limit=100"))
}
export async function getDataObjects(): Promise<DataObject[]> {
  return z.array(objectSchema).parse(await apiFetch<unknown>("/api/v1/data/objects?limit=500"))
}
export async function getDataChannels(): Promise<DataChannel[]> {
  return z.array(channelSchema).parse(await apiFetch<unknown>("/api/v1/data/channels?limit=500"))
}
