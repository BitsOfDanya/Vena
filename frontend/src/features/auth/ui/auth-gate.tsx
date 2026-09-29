"use client"

import * as React from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"

import { loginWithPassword, logoutSession, resolveSession, type AuthMe } from "@/entities/system"
import { ApiError } from "@/shared/api/http"
import { Button } from "@/shared/ui/button"
import { Input } from "@/shared/ui/input"
import { LoadingBar, StateMessage } from "@/shared/ui/state-message"
import { VenaMark } from "@/shared/ui/vena-mark"

import { LoginShowcase } from "./login-showcase"

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
    <div className="grid min-h-svh bg-background lg:grid-cols-[minmax(0,1.45fr)_minmax(420px,0.8fr)]">
      <aside className="relative hidden overflow-hidden bg-[#0f1d1b] lg:block">
        <LoginShowcase />
      </aside>
      <main className="flex flex-col items-center justify-center px-5 py-10 sm:px-10">
        <div className="mb-8 flex items-center gap-3 lg:hidden">
          <VenaMark tile className="size-10" />
          <div className="leading-tight">
            <p className="font-mono text-[19px] font-medium tracking-[0.3em]">VENA</p>
            <p className="text-[12px] text-muted-foreground">прогноз аварий инженерных коллекторов</p>
          </div>
        </div>
        <form
          className="w-full max-w-[400px] border border-border bg-elevated p-7 sm:p-8"
          onSubmit={async (event) => {
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
          }}
        >
          <h1 className="text-[22px] font-semibold">Вход в систему</h1>
          <p className="mt-1 text-[14px] text-muted-foreground">Рабочее место диспетчера и руководителя</p>
          {data.status.ldap_available && (
            <div role="radiogroup" aria-label="Способ входа" className="mt-6 grid grid-cols-2 gap-1 rounded-md bg-surface p-1">
              {([["password", "Учётная запись"], ["ldap", "LDAP / AD"]] as const).map(([value, label]) => (
                <button key={value} type="button" role="radio" aria-checked={method === value}
                  onClick={() => { setMethod(value); setError(null) }}
                  className={method === value
                    ? "h-8 rounded-[5px] bg-elevated text-[13px] font-medium shadow-sm"
                    : "h-8 rounded-[5px] text-[13px] text-muted-foreground hover:text-foreground"}>
                  {label}
                </button>
              ))}
            </div>
          )}
          <label className="mt-6 mb-1.5 block text-[13px] font-medium" htmlFor="vena-login">Email или логин</label>
          <Input id="vena-login" className="h-10" autoComplete="username" required maxLength={254} value={login}
            onChange={(e) => { setLogin(e.target.value); setError(null) }} placeholder="user1" />
          <label className="mt-4 mb-1.5 block text-[13px] font-medium" htmlFor="vena-password">Пароль</label>
          <Input id="vena-password" className="h-10" type="password" autoComplete="current-password" required maxLength={1024}
            value={password} onChange={(e) => { setPassword(e.target.value); setError(null) }} />
          {error && <p role="alert" className="mt-3 text-[13px] text-status-critical">{error}</p>}
          <Button type="submit" className="mt-6 h-10 w-full text-[14px]" disabled={pending || !login.trim() || !password}>
            {pending ? "Вход…" : "Войти"}
          </Button>
        </form>
        <div className="mt-4 w-full max-w-[400px] border-l-2 border-brass bg-elevated px-5 py-4 text-[13px] text-muted-foreground">
          <p className="font-medium text-foreground">Доступ для жюри</p>
          <p className="mt-1">
            Логин <span className="font-mono text-foreground">user1</span> · пароль{" "}
            <span className="font-mono text-foreground">0987654321</span> — администратор
          </p>
          <p className="mt-0.5 text-[12px] text-faint">user2–user20 с тем же паролем — диспетчеры</p>
        </div>
        <ul className="mt-6 w-full max-w-[400px] border-t border-l border-border text-[13px] lg:hidden">
          {[
            "Риск отказа насосов, вентиляции, питания и дымовых датчиков за 13–48 часов",
            "5 каналов на день, которые действительно стоит проверить",
            "Причина, последствие и первый шаг в каждой карточке",
            "Все модели проверены на январе–июне 2026",
          ].map((item) => (
            <li key={item} className="flex gap-2.5 border-r border-b border-border bg-elevated px-4 py-2.5">
              <span aria-hidden className="mt-1.5 size-1.5 shrink-0 bg-vena" />
              {item}
            </li>
          ))}
        </ul>
        <p className="mt-4 font-mono text-[11px] text-faint lg:hidden">КОМАНДА 5BIT · ЛЦТ 2026</p>
      </main>
    </div>
  )
  return <AuthContext.Provider value={{ me: data.me, authEnabled: data.status.auth_enabled, signOut, refresh }}>
    {children}
  </AuthContext.Provider>
}
