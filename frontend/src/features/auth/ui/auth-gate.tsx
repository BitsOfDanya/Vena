"use client"

import * as React from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"

import { loginWithPassword, logoutSession, resolveSession, type AuthMe } from "@/entities/system"
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
    queryKey: ["system", "auth-session"], queryFn: resolveSession,
    retry: false, staleTime: 30_000, refetchInterval: 60_000,
  })
  const [login, setLogin] = React.useState("")
  const [method, setMethod] = React.useState<"password" | "ldap">("password")
  const [password, setPassword] = React.useState("")
  const [error, setError] = React.useState<string | null>(null)
  const [pending, setPending] = React.useState(false)

  React.useEffect(() => {
    try { localStorage.removeItem("vena.apiKey.v1") } catch {}
    const expired = () => { void queryClient.invalidateQueries({ queryKey: ["system", "auth-session"] }) }
    window.addEventListener("vena:unauthorized", expired)
    return () => window.removeEventListener("vena:unauthorized", expired)
  }, [queryClient])

  const refresh = React.useCallback(async () => {
    await queryClient.cancelQueries()
    queryClient.removeQueries({ predicate: (query) => query.queryKey[1] !== "auth-session" })
    await queryClient.invalidateQueries({ queryKey: ["system", "auth-session"] })
  }, [queryClient])
  const signOut = React.useCallback(async () => {
    await logoutSession()
    await refresh()
  }, [refresh])

  if (session.isPending) return <div className="flex min-h-svh items-center justify-center"><LoadingBar /></div>
  if (session.isError) return (
    <div className="flex min-h-svh items-center justify-center p-8">
      <StateMessage title="Сервис входа временно недоступен" description="Попробуйте подключиться ещё раз."
        action={<Button variant="outline" onClick={() => session.refetch()}>Повторить</Button>} />
    </div>
  )
  const data = session.data
  if (data.needsLogin) return (
    <div className="flex min-h-svh items-center justify-center bg-background px-6">
      <form className="w-full max-w-md border border-border bg-elevated p-8" onSubmit={async (event) => {
        event.preventDefault()
        if (pending || !login.trim() || !password) return
        setPending(true)
        setError(null)
        try {
          await loginWithPassword(login.trim(), password, method)
          setPassword("")
          await refresh()
        } catch (err) {
          setError(err instanceof ApiError && err.status === 429
            ? "Слишком много попыток. Попробуйте через несколько минут."
            : err instanceof ApiError && err.status === 401
              ? "Неверный email, логин или пароль."
              : "Не удалось войти. Попробуйте ещё раз.")
        } finally { setPending(false) }
      }}>
        <div className="mb-6 flex items-center gap-3">
          <VenaMark className="text-vena" />
          <div><p className="text-[12px] font-medium tracking-[0.14em] text-faint uppercase">VENA</p>
            <h1 className="text-[22px] font-semibold">Вход в систему</h1></div>
        </div>
        {data.status.ldap_available && <label className="mb-4 block text-sm">Способ входа
          <select className="mt-2 w-full border border-border bg-background p-2" value={method}
            onChange={(event) => { setMethod(event.target.value as "password" | "ldap"); setError(null) }}>
            <option value="password">Локальная учётная запись</option><option value="ldap">Корпоративный LDAP / AD</option>
          </select></label>}
        <label className="mb-2 block text-sm text-muted-foreground" htmlFor="vena-login">Email или логин</label>
        <Input id="vena-login" autoComplete="username" required maxLength={254} value={login}
          onChange={(e) => { setLogin(e.target.value); setError(null) }} placeholder="user1" />
        <label className="mt-4 mb-2 block text-sm text-muted-foreground" htmlFor="vena-password">Пароль</label>
        <Input id="vena-password" type="password" autoComplete="current-password" required maxLength={1024}
          value={password} onChange={(e) => { setPassword(e.target.value); setError(null) }} />
        {error && <p role="alert" className="mt-3 text-sm text-status-critical">{error}</p>}
        <Button type="submit" className="mt-6 w-full" disabled={pending || !login.trim() || !password}>
          {pending ? "Вход…" : "Войти"}
        </Button>
        <div className="mt-6 border-t border-border-soft pt-4 text-[13px] text-muted-foreground">
          <p className="font-medium text-foreground">Доступ для жюри</p>
          <p className="mt-1">
            Логин <span className="font-mono text-foreground">user1</span>
            {" · "}
            пароль <span className="font-mono text-foreground">0987654321</span>
          </p>
          <p className="mt-1 text-[12px] text-faint">user1 — администратор. user2–user20 / тот же пароль — диспетчеры.</p>
          <p className="mt-3 border-t border-border-soft pt-3 text-[12px] leading-relaxed text-muted-foreground">
            После входа: <span className="text-foreground">Пульс</span> → карточка инцидента →{" "}
            <span className="text-foreground">Создать работу</span>. Для руководства:{" "}
            <span className="text-foreground">Дашборд</span> и <span className="text-foreground">Эффект</span>.
          </p>
        </div>
      </form>
    </div>
  )
  return <AuthContext.Provider value={{ me: data.me, authEnabled: data.status.auth_enabled, signOut, refresh }}>
    {children}
  </AuthContext.Provider>
}
