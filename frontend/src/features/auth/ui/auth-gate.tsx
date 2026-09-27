"use client"

import * as React from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"

import { loginWithApiKey, logoutSession, resolveSession, type AuthMe } from "@/entities/system"
import { ApiError } from "@/shared/api/http"
import { Button } from "@/shared/ui/button"
import { Input } from "@/shared/ui/input"
import { LoadingBar, StateMessage } from "@/shared/ui/state-message"
import { VenaMark } from "@/shared/ui/vena-mark"

const AuthContext = React.createContext<{
  me: AuthMe | null
  authEnabled: boolean
  signOut: () => Promise<void>
  refresh: () => Promise<void>
} | null>(null)

export function useAuthSession() {
  const value = React.useContext(AuthContext)
  if (!value) throw new Error("useAuthSession must be used within AuthGate")
  return value
}

export function AuthGate({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient()
  const session = useQuery({
    queryKey: ["system", "auth-session"],
    queryFn: resolveSession,
    retry: false,
    staleTime: 30_000,
  })
  const [draft, setDraft] = React.useState("")
  const [error, setError] = React.useState<string | null>(null)
  const [pending, setPending] = React.useState(false)

  const signOut = React.useCallback(async () => {
    await logoutSession()
    await queryClient.invalidateQueries({ queryKey: ["system"] })
    await session.refetch()
  }, [queryClient, session])

  const refresh = React.useCallback(async () => {
    await session.refetch()
  }, [session])

  if (session.isPending) {
    return (
      <div className="flex size-full items-center justify-center">
        <LoadingBar />
      </div>
    )
  }

  if (session.isError) {
    return (
      <div className="flex size-full items-center justify-center p-8">
        <StateMessage
          title="Сервис авторизации недоступен"
          description="Не удалось получить /api/v1/auth/status. Проверьте backend."
          action={
            <Button variant="outline" size="sm" onClick={() => session.refetch()}>
              Retry
            </Button>
          }
        />
      </div>
    )
  }

  const data = session.data
  if (data?.needsLogin) {
    return (
      <div className="flex size-full items-center justify-center bg-background px-6">
        <div className="w-full max-w-md border border-border bg-elevated p-8">
          <div className="mb-6 flex items-center gap-3">
            <VenaMark className="text-vena" />
            <div>
              <p className="text-[12px] font-medium tracking-[0.14em] text-faint uppercase">VENA</p>
              <h1 className="text-[22px] font-semibold tracking-[-0.01em]">Sign in</h1>
            </div>
          </div>
          <div className="mb-6 border border-border bg-surface px-4 py-4">
            <p className="text-[11px] font-medium tracking-[0.12em] text-faint uppercase">Тестовый стенд · API keys</p>
            <ul className="mt-3 space-y-2 font-mono text-[18px] leading-snug tracking-tight text-foreground">
              <li>
                <span className="text-vena">vena-admin</span>
                <span className="ml-2 text-[13px] text-muted-foreground">admin</span>
              </li>
              <li>
                <span className="text-vena">vena-dispatch</span>
                <span className="ml-2 text-[13px] text-muted-foreground">dispatcher</span>
              </li>
              <li>
                <span className="text-vena">vena-view</span>
                <span className="ml-2 text-[13px] text-muted-foreground">viewer</span>
              </li>
            </ul>
          </div>
          {!data.status.keys_configured ? (
            <p className="mb-4 border border-status-attention/40 bg-status-attention/10 px-3 py-2 text-[12px] text-status-attention">
              Auth включён, но `VENA_API_KEYS_JSON` пуст или некорректен.
            </p>
          ) : null}
          <label className="mb-2 block text-[12px] text-muted-foreground" htmlFor="vena-api-key">
            API key
          </label>
          <Input
            id="vena-api-key"
            type="password"
            autoComplete="off"
            value={draft}
            onChange={(event) => {
              setDraft(event.target.value)
              setError(null)
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault()
                void (async () => {
                  setPending(true)
                  setError(null)
                  try {
                    await loginWithApiKey(draft.trim())
                    setDraft("")
                    await queryClient.invalidateQueries()
                    await session.refetch()
                  } catch (err) {
                    setError(err instanceof ApiError ? err.detail : "Не удалось войти")
                  } finally {
                    setPending(false)
                  }
                })()
              }
            }}
            placeholder="vena-admin"
            className="font-mono text-xs"
          />
          {error ? <p className="mt-2 text-[12px] text-status-critical">{error}</p> : null}
          <Button
            className="mt-5 w-full"
            disabled={pending || !draft.trim() || !data.status.keys_configured}
            onClick={() => {
              void (async () => {
                setPending(true)
                setError(null)
                try {
                  await loginWithApiKey(draft.trim())
                  setDraft("")
                  await queryClient.invalidateQueries()
                  await session.refetch()
                } catch (err) {
                  setError(err instanceof ApiError ? err.detail : "Не удалось войти")
                } finally {
                  setPending(false)
                }
              })()
            }}
          >
            {pending ? "Checking…" : "Continue"}
          </Button>
        </div>
      </div>
    )
  }

  return (
    <AuthContext.Provider
      value={{
        me: data?.me ?? null,
        authEnabled: Boolean(data?.status.auth_enabled),
        signOut,
        refresh,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}
