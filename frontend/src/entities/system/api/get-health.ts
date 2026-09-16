import * as z from "zod"

import { apiFetch } from "@/shared/api/http"

export const healthSchema = z.object({
  status: z.literal("ok"),
  service: z.string(),
  version: z.string(),
})

export type Health = z.infer<typeof healthSchema>

export async function getHealth(): Promise<Health> {
  const response = await apiFetch<unknown>("/api/v1/health")
  return healthSchema.parse(response)
}
