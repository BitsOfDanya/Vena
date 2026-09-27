"use client"

import * as React from "react"
import { useQueryClient } from "@tanstack/react-query"

import { loginWithApiKey } from "@/entities/system"
import { useAuthSession } from "@/features/auth"
import { getStoredApiKey } from "@/shared/api/auth-storage"
import { ApiError } from "@/shared/api/http"
import { Button } from "@/shared/ui/button"
import { Input } from "@/shared/ui/input"

import { SettingsSection, SettingsShell } from "./settings-shell"

export function SettingsSecurityPage() {
  const { me, authEnabled, signOut, refresh } = useAuthSession()
  const queryClient = useQueryClient()
  const [draft, setDraft] = React.useState(() => getStoredApiKey() ?? "")
  const [error, setError] = React.useState<string | null>(null)
  const [pending, setPending] = React.useState(false)

  return (
    <SettingsShell title="Security" descriptor="API key · RBAC">
      <SettingsSection
        title="Session"
        description={
          authEnabled
            ? "Ключ проверяется через POST /auth/login и уходит в X-API-Key на каждый запрос."
            : "Сейчас VENA_AUTH_ENABLED=false — API открыт. Включите auth в окружении backend."
        }
      >
        <div className="space-y-3 border border-border bg-elevated px-5 py-4">
          <label className="block text-[13px] text-muted-foreground" htmlFor="api-key">
            API key
          </label>
          <Input
            id="api-key"
            type="password"
            autoComplete="off"
            value={draft}
            onChange={(event) => {
              setDraft(event.target.value)
              setError(null)
            }}
            placeholder="vena-admin"
            className="font-mono text-xs"
            disabled={!authEnabled}
          />
          {error ? <p className="text-[12px] text-status-critical">{error}</p> : null}
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              disabled={!authEnabled || pending || !draft.trim()}
              onClick={() => {
                void (async () => {
                  setPending(true)
                  setError(null)
                  try {
                    await loginWithApiKey(draft.trim())
                    await queryClient.invalidateQueries()
                    await refresh()
                  } catch (err) {
                    setError(err instanceof ApiError ? err.detail : "Неверный ключ")
                  } finally {
                    setPending(false)
                  }
                })()
              }}
            >
              {pending ? "Saving…" : "Save key"}
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={!authEnabled}
              onClick={() => {
                void (async () => {
                  setDraft("")
                  await signOut()
                })()
              }}
            >
              Sign out
            </Button>
          </div>
        </div>
      </SettingsSection>

      <SettingsSection title="Principal">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 border border-border bg-elevated px-5 py-4 text-[14px]">
          <div>
            <dt className="text-[12px] text-faint uppercase">Subject</dt>
            <dd className="mt-0.5 font-mono text-[13px]">{me?.subject ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-[12px] text-faint uppercase">Role</dt>
            <dd className="mt-0.5 font-mono text-[13px]">{me?.role ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-[12px] text-faint uppercase">Auth method</dt>
            <dd className="mt-0.5 font-mono text-[13px]">{me?.auth_method ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-[12px] text-faint uppercase">LDAP / AD</dt>
            <dd className="mt-0.5 text-[13px] text-muted-foreground">Не подключено (следующий этап)</dd>
          </div>
        </dl>
      </SettingsSection>
    </SettingsShell>
  )
}
