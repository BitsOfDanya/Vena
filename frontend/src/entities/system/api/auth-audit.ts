import { z } from "zod"

import { apiFetch, ApiError } from "@/shared/api/http"
import { getStoredApiKey, setStoredApiKey } from "@/shared/api/auth-storage"

const MeSchema = z.object({
  subject: z.string(),
  role: z.enum(["admin", "dispatcher", "viewer"]),
  auth_method: z.string(),
})

const StatusSchema = z.object({
  auth_enabled: z.boolean(),
  methods: z.array(z.string()),
  keys_configured: z.boolean(),
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

export async function loginWithApiKey(apiKey: string): Promise<AuthMe> {
  const me = MeSchema.parse(
    await apiFetch<unknown>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ api_key: apiKey }),
    })
  )
  setStoredApiKey(apiKey)
  return me
}

export async function logoutSession(): Promise<void> {
  setStoredApiKey(null)
  try {
    await apiFetch("/api/v1/auth/logout", { method: "POST" })
  } catch {
    // client-side clear is enough for API-key auth
  }
}

export async function resolveSession(): Promise<{ status: AuthStatus; me: AuthMe | null; needsLogin: boolean }> {
  const status = await getAuthStatus()
  if (!status.auth_enabled) {
    try {
      const me = await getAuthMe()
      return { status, me, needsLogin: false }
    } catch {
      return { status, me: null, needsLogin: false }
    }
  }
  if (!status.keys_configured) {
    return { status, me: null, needsLogin: true }
  }
  if (!getStoredApiKey()) {
    return { status, me: null, needsLogin: true }
  }
  try {
    const me = await getAuthMe()
    return { status, me, needsLogin: false }
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      setStoredApiKey(null)
      return { status, me: null, needsLogin: true }
    }
    throw error
  }
}

export async function listAuditLog(limit = 100): Promise<AuditEntry[]> {
  const raw = await apiFetch<unknown>(`/api/v1/audit?limit=${limit}`)
  return z.array(AuditEntrySchema).parse(raw)
}
