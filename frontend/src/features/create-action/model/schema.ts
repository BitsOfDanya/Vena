import * as z from "zod"

export const createActionSchema = z.object({
  assetId: z.string().min(1, "Выберите объект"),
  reason: z.string().trim().min(3, "Опишите причину").max(240),
  kind: z.enum(["inspect", "electrical diagnostic", "service", "verify"]),
  priority: z.enum(["high", "medium", "low"]),
  recommendedAt: z.string().min(1, "Укажите рекомендуемую дату"),
  assignee: z.string().min(1, "Выберите исполнителя"),
  note: z.string().max(500),
})

export type CreateActionValues = z.infer<typeof createActionSchema>
