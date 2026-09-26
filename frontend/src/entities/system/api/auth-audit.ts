import { z } from "zod"

import { apiFetch } from "@/shared/api/http"

const MeSchema = z.object({
  subject: z.string(),
  role: z.enum(["admin", "dispatcher", "viewer"]),
  auth_method: z.string(),
})

const AuditEntrySchema = z.object({
  id: z.number(),
  at: z.string(),
  actor: z.string(),
  role: z.string(),
  action: z.string(),
  resource_type: z.string(),
  resource_id: z.string(),
  detail: z.string(),
  ip: z.string().nullable().optional(),
})

export type AuthMe = z.infer<typeof MeSchema>
export type AuditEntry = z.infer<typeof AuditEntrySchema>

export async function getAuthMe(): Promise<AuthMe> {
  return MeSchema.parse(await apiFetch<unknown>("/api/v1/auth/me"))
}

export async function listAuditLog(limit = 100): Promise<AuditEntry[]> {
  const raw = await apiFetch<unknown>(`/api/v1/audit?limit=${limit}`)
  return z.array(AuditEntrySchema).parse(raw)
}
