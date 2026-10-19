import { z } from "zod"

import { formatCount } from "@/shared/lib/plural"

import type { ObjectLevelModel, ObjectLevelReport } from "../model/types"
import { scenarioTitle } from "./dispatcher-copy"

const value = z.number().nullable().optional()
const text = z.string().nullable().optional()

const ObjectLevelSchema = z.object({
  period: text,
  unit: text,
  generated_at: text,
  models: z
    .array(
      z.object({
        id: z.string(),
        label: text,
        scenario: text,
        horizon_hours: value,
        objects_per_day: value,
        base_rate: value,
        avg_precision: value,
        roc_auc: value,
        top_k: z.record(z.string(), z.number().nullable()).nullable().optional(),
        recall_at_precision_0_7: value,
        precision_at_recall_0_5: value,
        curve: z
          .array(z.object({ top_k: z.number(), precision: value, recall: value, alerts_per_day: value }))
          .nullable()
          .optional(),
      })
    )
    .nullable()
    .optional(),
})

export function parseObjectLevel(raw: unknown): ObjectLevelReport {
  const data = ObjectLevelSchema.parse(raw)
  return {
    period: data.period ?? null,
    unit: data.unit ?? null,
    generatedAt: data.generated_at ?? null,
    models: (data.models ?? []).map((item) => ({
      id: item.id,
      label: item.label ?? scenarioTitle(item.scenario ?? item.id),
      scenario: item.scenario ?? "equipment",
      horizonHours: item.horizon_hours ?? null,
      objectsPerDay: item.objects_per_day ?? null,
      baseRate: item.base_rate ?? null,
      avgPrecision: item.avg_precision ?? null,
      rocAuc: item.roc_auc ?? null,
      topK: item.top_k ?? {},
      recallAtPrecision70: item.recall_at_precision_0_7 ?? null,
      precisionAtRecall50: item.precision_at_recall_0_5 ?? null,
      curve: (item.curve ?? []).map((point) => ({
        topK: point.top_k,
        precision: point.precision ?? null,
        recall: point.recall ?? null,
        alertsPerDay: point.alerts_per_day ?? null,
      })),
    })),
  }
}

export function formatShare(share: number | null | undefined, digits = 0) {
  if (share == null) return "—"
  const scale = 10 ** digits
  return `${formatCount(Math.round(share * 100 * scale) / scale)}%`
}

export function listPrecision(model: ObjectLevelModel, size: number) {
  const direct = model.topK[String(size)]
  if (direct != null) return direct
  return model.curve.find((point) => point.topK === size)?.precision ?? null
}

export function liftOverRandom(model: ObjectLevelModel, size = 3) {
  const precision = listPrecision(model, size)
  if (precision == null || !model.baseRate) return null
  return precision / model.baseRate
}

export type PaybackInput = {
  size: number
  precision: number | null
  cost: number
  loss: number
  share: number
}

export type Payback = { breakEven: number | null; yearlyEffect: number | null }

export function payback({ size, precision, cost, loss, share }: PaybackInput): Payback {
  const prevented = loss * share
  return {
    breakEven: prevented > 0 ? cost / prevented : null,
    yearlyEffect: precision == null ? null : 365 * (size * precision * share * loss - size * cost),
  }
}

export function paybackVerdict(precision: number | null, result: Payback) {
  if (precision == null || result.yearlyEffect == null) return "Для этого сценария нет точности списка такого размера."
  if (result.breakEven == null) return "Укажите ущерб от инцидента и долю предотвращаемых случаев."
  if (result.breakEven >= 1) return "Не окупается даже при безошибочном списке: проверка дороже предотвращённого ущерба."
  const pair = `точность списка ${formatShare(precision, 1)}, порог ${formatShare(result.breakEven, 1)}`
  if (Math.abs(result.yearlyEffect) < 1) return `Выходит в ноль: ${pair}.`
  if (result.yearlyEffect > 0) return `Окупается: ${pair}. Каждая проверка в среднем приносит больше, чем стоит.`
  return `Не окупается: ${pair}. Сократите список или снизьте стоимость проверки.`
}
