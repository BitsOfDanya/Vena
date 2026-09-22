import * as z from "zod"

export const createActionSchema = z.object({
  assetId: z.string().min(1, "Select an asset"),
  reason: z.string().trim().min(3, "Describe the reason").max(240),
  kind: z.enum(["inspect", "electrical diagnostic", "service", "verify"]),
  priority: z.enum(["high", "medium", "low"]),
  recommendedAt: z.string().min(1, "Set a recommended date"),
  assignee: z.string().min(1, "Select an assignee"),
  note: z.string().max(500),
})

export type CreateActionValues = z.infer<typeof createActionSchema>
