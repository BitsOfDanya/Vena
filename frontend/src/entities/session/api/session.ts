import { z } from "zod"

import { apiFetch } from "@/shared/api/http"

export const userSchema = z.object({
  id: z.string(),
  email: z.email(),
  full_name: z.string(),
  role: z.enum(["operator", "dispatcher"]),
})

export type SessionUser = z.infer<typeof userSchema>

export async function getSession(): Promise<SessionUser> {
  return userSchema.parse(await apiFetch<unknown>("/api/v1/auth/me"))
}

export async function loginAccount(payload: { email: string; password: string }): Promise<SessionUser> {
  return userSchema.parse(
    await apiFetch<unknown>("/api/v1/auth/login", { method: "POST", body: JSON.stringify(payload) })
  )
}

export async function registerAccount(payload: {
  email: string
  full_name: string
  password: string
  role: "operator" | "dispatcher"
  invite_code: string
}): Promise<SessionUser> {
  return userSchema.parse(
    await apiFetch<unknown>("/api/v1/auth/register", { method: "POST", body: JSON.stringify(payload) })
  )
}

export async function logoutAccount(): Promise<void> {
  await apiFetch<void>("/api/v1/auth/logout", { method: "POST" })
}
