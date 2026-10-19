import { z } from "zod"

import { apiFetch } from "@/shared/api/http"

import type { IncidentRegistry, ObjectRiskList } from "../model/types"

const number = z.number().nullable().optional()
const kind = z.enum(["power", "flood", "fire"])

const RegistrySchema = z.object({
  available: z.boolean(),
  detail: z.string().optional(),
  journal_end: z.string().nullable().optional(),
  restricted: z.boolean().optional(),
  kinds: z
    .array(
      z.object({
        kind,
        label: z.string(),
        rule: z.string().optional(),
        total: z.number(),
        objects: z.number(),
        per_year: z.array(z.object({ year: z.string(), count: z.number() })).optional(),
        recent_2026h1: number,
        per_day_2026h1: number,
        channels_median: number,
        top_objects: z
          .array(
            z.object({
              object_id: z.string(),
              object_name: z.string(),
              count: z.number(),
            }),
          )
          .optional(),
        temperature_confirmed: number,
        long_over_30_minutes: number,
      }),
    )
    .optional(),
  recent: z
    .array(
      z.object({
        kind,
        label: z.string(),
        object_id: z.string(),
        object_name: z.string(),
        start: z.string(),
        end: z.string().nullable().optional(),
        channels: number,
        temperature_confirmed: z.boolean().nullable().optional(),
        max_minutes: number,
      }),
    )
    .optional(),
})

const ObjectsSchema = z.object({
  available: z.boolean(),
  detail: z.string().optional(),
  prediction_time: z.string().nullable().optional(),
  restricted: z.boolean().optional(),
  models: z
    .array(
      z.object({
        model_id: z.string(),
        label: z.string(),
        scenario: z.string(),
        precision_top3: number,
        base_rate: number,
        avg_precision: number,
        period: z.string().nullable().optional(),
        rule: z.string().optional(),
        nowcast: z
          .object({
            model_id: z.string(),
            horizon_hours: z.number(),
            period: z.string().nullable().optional(),
            share_top3: number,
            rule_share_top3: number,
            objects: number,
          })
          .nullable()
          .optional(),
      }),
    )
    .optional(),
  items: z
    .array(
      z.object({
        object_id: z.string(),
        object_name: z.string(),
        scenario: z.string(),
        model_id: z.string(),
        model_label: z.string(),
        probability: z.number(),
        rank: z.number(),
        horizon_hours: number,
        history: z
          .object({
            events_1d: number,
            events_7d: number,
            events_30d: number,
            events_90d: number,
            days_since: number,
          })
          .optional(),
        channel_score: number,
        probability_6h: number,
      }),
    )
    .optional(),
})

function stamp(value: string | null | undefined) {
  if (!value) return null
  const parsed = Date.parse(value)
  return Number.isNaN(parsed) ? null : parsed
}

export function parseIncidentRegistry(raw: unknown): IncidentRegistry {
  const data = RegistrySchema.parse(raw)
  return {
    available: data.available,
    detail: data.detail ?? "",
    journalEnd: data.journal_end ?? null,
    restricted: data.restricted ?? false,
    kinds: (data.kinds ?? []).map((item) => ({
      kind: item.kind,
      label: item.label,
      rule: item.rule ?? "",
      total: item.total,
      objects: item.objects,
      perYear: item.per_year ?? [],
      recent2026h1: item.recent_2026h1 ?? null,
      perDay2026h1: item.per_day_2026h1 ?? null,
      channelsMedian: item.channels_median ?? null,
      topObjects: (item.top_objects ?? []).map((entry) => ({
        objectId: entry.object_id,
        objectName: entry.object_name,
        count: entry.count,
      })),
      temperatureConfirmed: item.temperature_confirmed ?? null,
      longOver30Minutes: item.long_over_30_minutes ?? null,
    })),
    recent: (data.recent ?? []).flatMap((item) => {
      const start = stamp(item.start)
      if (start === null) return []
      return [
        {
          kind: item.kind,
          label: item.label,
          objectId: item.object_id,
          objectName: item.object_name,
          start,
          end: stamp(item.end),
          channels: item.channels ?? null,
          temperatureConfirmed: item.temperature_confirmed ?? null,
          maxMinutes: item.max_minutes ?? null,
        },
      ]
    }),
  }
}

export function parseObjectRisks(raw: unknown): ObjectRiskList {
  const data = ObjectsSchema.parse(raw)
  return {
    available: data.available,
    detail: data.detail ?? "",
    predictionTime: stamp(data.prediction_time),
    restricted: data.restricted ?? false,
    models: (data.models ?? []).map((item) => ({
      modelId: item.model_id,
      label: item.label,
      scenario: item.scenario,
      precisionTop3: item.precision_top3 ?? null,
      baseRate: item.base_rate ?? null,
      avgPrecision: item.avg_precision ?? null,
      period: item.period ?? null,
      rule: item.rule ?? "",
      nowcast: item.nowcast
        ? {
            modelId: item.nowcast.model_id,
            horizonHours: item.nowcast.horizon_hours,
            period: item.nowcast.period ?? null,
            shareTop3: item.nowcast.share_top3 ?? null,
            ruleShareTop3: item.nowcast.rule_share_top3 ?? null,
            objects: item.nowcast.objects ?? null,
          }
        : null,
    })),
    items: (data.items ?? []).map((item) => ({
      objectId: item.object_id,
      objectName: item.object_name,
      scenario: item.scenario,
      modelId: item.model_id,
      modelLabel: item.model_label,
      probability: item.probability,
      rank: item.rank,
      horizonHours: item.horizon_hours ?? null,
      history: {
        events1d: item.history?.events_1d ?? null,
        events7d: item.history?.events_7d ?? null,
        events30d: item.history?.events_30d ?? null,
        events90d: item.history?.events_90d ?? null,
        daysSince: item.history?.days_since ?? null,
      },
      channelScore: item.channel_score ?? null,
      probability6h: item.probability_6h ?? null,
    })),
  }
}

export async function getIncidentRegistry(): Promise<IncidentRegistry> {
  return parseIncidentRegistry(await apiFetch<unknown>("/api/v1/incidents/registry"))
}

export async function getObjectRisks(): Promise<ObjectRiskList> {
  return parseObjectRisks(await apiFetch<unknown>("/api/v1/incidents/objects"))
}
