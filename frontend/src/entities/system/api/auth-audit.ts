import { z } from "zod"

import { apiFetch, ApiError } from "@/shared/api/http"

const MeSchema = z.object({
  subject: z.string(),
  role: z.enum(["admin", "dispatcher", "viewer"]),
  auth_method: z.string(),
  email: z.string().nullable().optional(),
})

const StatusSchema = z.object({
  auth_enabled: z.boolean(),
  methods: z.array(z.string()),
  configured: z.boolean(),
  ldap_available: z.boolean().optional(),
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
export type AuthStatus = z.infer<typeof StatusSchema>
export type AuditEntry = z.infer<typeof AuditEntrySchema>

export async function getAuthStatus(): Promise<AuthStatus> {
  return StatusSchema.parse(await apiFetch<unknown>("/api/v1/auth/status"))
}

export async function getAuthMe(): Promise<AuthMe> {
  return MeSchema.parse(await apiFetch<unknown>("/api/v1/auth/me"))
}

export async function loginWithPassword(login: string, password: string): Promise<AuthMe> {
  const result = await apiFetch<{ user: unknown }>("/api/v1/auth/login", {
    method: "POST", body: JSON.stringify({ email: login, password }),
  })
  return MeSchema.parse(result.user)
}

export async function logoutSession(): Promise<void> {
  try {
    await apiFetch("/api/v1/auth/logout", { method: "POST" })
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 401)) throw error
  }
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  await apiFetch("/api/v1/auth/password", {
    method: "POST", body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  })
}

export async function resolveSession(): Promise<{ status: AuthStatus; me: AuthMe | null; needsLogin: boolean }> {
  const status = await getAuthStatus()
  try {
    return { status, me: await getAuthMe(), needsLogin: false }
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      return { status, me: null, needsLogin: true }
    }
    throw error
  }
}

export async function listAuditLog(limit = 100): Promise<AuditEntry[]> {
  const raw = await apiFetch<unknown>(`/api/v1/audit?limit=${limit}`)
  return z.array(AuditEntrySchema).parse(raw)
}
