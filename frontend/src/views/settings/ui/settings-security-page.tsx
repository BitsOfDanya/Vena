"use client"

import * as React from "react"
import { changePassword } from "@/entities/system"
import { useAuthSession } from "@/features/auth"
import { ApiError } from "@/shared/api/http"
import { Button } from "@/shared/ui/button"
import { Input } from "@/shared/ui/input"
import { SettingsSection, SettingsShell } from "./settings-shell"

export function SettingsSecurityPage() {
  const { me, authEnabled, signOut, refresh } = useAuthSession()
  const [current, setCurrent] = React.useState("")
  const [next, setNext] = React.useState("")
  const [confirmation, setConfirmation] = React.useState("")
  const [pending, setPending] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  return (
    <SettingsShell title="Безопасность" descriptor="Учётная запись">
      <SettingsSection title="Текущий пользователь">
        <dl className="grid grid-cols-2 gap-4 border border-border bg-elevated p-5">
          <div><dt>Логин</dt><dd>{me?.subject}</dd></div>
          <div><dt>Email</dt><dd>{me?.email ?? "—"}</dd></div>
          <div><dt>Роль</dt><dd>{{ admin: "Администратор", dispatcher: "Диспетчер", viewer: "Наблюдатель" }[me?.role ?? "viewer"]}</dd></div>
        </dl>
        <Button className="mt-4" variant="outline" disabled={!authEnabled} onClick={async () => {
          try { await signOut() } catch { setError("Не удалось выйти. Попробуйте ещё раз.") }
        }}>Выйти</Button>
      </SettingsSection>
      {me?.auth_method === "ldap" ? <p>Пароль корпоративной учётной записи меняется в LDAP / AD.</p> : <SettingsSection title="Сменить пароль" description="После смены пароля нужно войти заново на всех устройствах.">
        <form className="space-y-4 border border-border bg-elevated p-5" onSubmit={async (event) => {
          event.preventDefault()
          if (pending) return
          if (next !== confirmation) { setError("Пароли не совпадают."); return }
          setPending(true); setError(null)
          try { await changePassword(current, next); await refresh() }
          catch (err) { setError(err instanceof ApiError && err.status === 400
            ? "Текущий пароль неверен." : "Не удалось сменить пароль. Попробуйте позже.") }
          finally { setPending(false) }
        }}>
          <label className="block" htmlFor="current-password">Текущий пароль</label>
          <Input id="current-password" type="password" autoComplete="current-password" required
            value={current} onChange={(e) => setCurrent(e.target.value)} />
          <label className="block" htmlFor="new-password">Новый пароль · минимум 10 символов</label>
          <Input id="new-password" type="password" autoComplete="new-password" minLength={10} maxLength={1024} required
            value={next} onChange={(e) => setNext(e.target.value)} />
          <label className="block" htmlFor="confirm-password">Повторите новый пароль</label>
          <Input id="confirm-password" type="password" autoComplete="new-password" required
            value={confirmation} onChange={(e) => setConfirmation(e.target.value)} />
          {error && <p role="alert" className="text-sm text-status-critical">{error}</p>}
          <Button type="submit" disabled={!authEnabled || pending}>{pending ? "Сохранение…" : "Сменить пароль"}</Button>
        </form>
      </SettingsSection>}
    </SettingsShell>
  )
}
