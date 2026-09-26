"use client"

import * as React from "react"
import { useQuery } from "@tanstack/react-query"

import { getAuthMe } from "@/entities/system"
import { getStoredApiKey, setStoredApiKey } from "@/shared/api/auth-storage"
import { Button } from "@/shared/ui/button"
import { Input } from "@/shared/ui/input"

import { SettingsSection, SettingsShell } from "./settings-shell"

export function SettingsSecurityPage() {
  const [draft, setDraft] = React.useState(() => getStoredApiKey() ?? "")
  const [saved, setSaved] = React.useState(() => getStoredApiKey() ?? "")
  const me = useQuery({
    queryKey: ["system", "auth-me", saved],
    queryFn: getAuthMe,
    retry: false,
    staleTime: 15_000,
  })

  return (
    <SettingsShell title="Security" descriptor="API key · RBAC">
      <SettingsSection
        title="Session"
        description="При включённом VENA_AUTH_ENABLED ключ уходит в заголовок X-API-Key на каждый запрос к API."
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
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Вставьте ключ из VENA_API_KEYS_JSON"
            className="font-mono text-xs"
          />
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              onClick={() => {
                const next = draft.trim()
                setStoredApiKey(next || null)
                setSaved(next)
                setDraft(next)
              }}
            >
              Save key
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setStoredApiKey(null)
                setSaved("")
                setDraft("")
              }}
            >
              Clear
            </Button>
          </div>
        </div>
      </SettingsSection>

      <SettingsSection title="Principal">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 border border-border bg-elevated px-5 py-4 text-[14px]">
          <div>
            <dt className="text-[12px] text-faint uppercase">Subject</dt>
            <dd className="mt-0.5 font-mono text-[13px]">
              {me.isError ? "unauthorized / unreachable" : (me.data?.subject ?? "…")}
            </dd>
          </div>
          <div>
            <dt className="text-[12px] text-faint uppercase">Role</dt>
            <dd className="mt-0.5 font-mono text-[13px]">{me.data?.role ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-[12px] text-faint uppercase">Auth method</dt>
            <dd className="mt-0.5 font-mono text-[13px]">{me.data?.auth_method ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-[12px] text-faint uppercase">LDAP / AD</dt>
            <dd className="mt-0.5 text-[13px] text-muted-foreground">Следующий шаг после API-key</dd>
          </div>
        </dl>
      </SettingsSection>
    </SettingsShell>
  )
}
