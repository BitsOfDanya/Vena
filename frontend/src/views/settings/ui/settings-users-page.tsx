"use client"
import * as React from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useAuthSession } from "@/features/auth"
import { apiFetch, ApiError } from "@/shared/api/http"
import { Button } from "@/shared/ui/button"
import { Input } from "@/shared/ui/input"
import { SettingsShell, SettingsSection } from "./settings-shell"

type Role = "viewer" | "dispatcher" | "admin"
type User = { id: string; username: string; email: string; role: Role; is_active: boolean; auth_provider: string }
const roles: Record<Role, string> = { viewer: "Наблюдатель", dispatcher: "Диспетчер", admin: "Администратор" }
export function SettingsUsersPage() {
  const { me } = useAuthSession()
  const admin = me?.role === "admin"
  const queryClient = useQueryClient()
  const [page, setPage] = React.useState(0)
  const users = useQuery({ queryKey: ["users", page], queryFn: () => apiFetch<{ total: number; items: User[] }>(`/api/v1/users?offset=${page * 100}`), enabled: admin })
  const [busy, setBusy] = React.useState(false)
  const [error, setError] = React.useState("")
  const [message, setMessage] = React.useState("")
  const [target, setTarget] = React.useState<User | null>(null)
  async function change(path: string, body: object, method: string) {
    setBusy(true); setError(""); setMessage("")
    try { await apiFetch(path, { method, body: JSON.stringify(body) }); await queryClient.invalidateQueries({ queryKey: ["users"] }); setMessage("Изменения сохранены."); return true }
    catch (err) { setError(err instanceof ApiError ? err.detail : "Не удалось сохранить изменения."); return false }
    finally { setBusy(false) }
  }
  return <SettingsShell title="Пользователи" descriptor="Управление доступом">
    {!admin ? <p>Раздел доступен администратору.</p> : <>
      <SettingsSection title="Создать пользователя"><form className="space-y-3 border border-border bg-elevated p-4" onSubmit={async event => {
        event.preventDefault(); const form = event.currentTarget
        if (await change("/api/v1/users", Object.fromEntries(new FormData(form).entries()), "POST")) form.reset()
      }}>
        <label className="block text-sm">Логин<Input name="username" required pattern="[a-zA-Z0-9_.-]+" maxLength={64} autoComplete="off" /></label>
        <label className="block text-sm">Email<Input name="email" type="email" required autoComplete="off" /></label>
        <label className="block text-sm">Пароль · минимум 10 символов<Input name="password" type="password" required minLength={10} maxLength={1024} autoComplete="new-password" /></label>
        <label className="block text-sm">Роль<select name="role" className="ml-3 border border-border p-2 bg-background" defaultValue="viewer">{Object.entries(roles).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <Button disabled={busy} type="submit">Создать пользователя</Button>
      </form></SettingsSection>
      {error && <p role="alert" className="text-status-critical">{error}</p>}
      {message && <p role="status" className="text-sm">{message}</p>}
      <SettingsSection title="Учётные записи" description="Блокировка, смена роли и сброс пароля отзывают действующие сессии.">
        {users.isError && <p role="alert">Не удалось получить список пользователей.</p>}
        <div className="overflow-x-auto border border-border"><table className="w-full text-sm text-left"><thead><tr>{["Пользователь", "Роль", "Состояние", "Действия"].map(label => <th className="p-2" key={label}>{label}</th>)}</tr></thead><tbody>
          {users.data?.items.map(user => <tr key={user.id} className="border-t border-border-soft"><td className="p-2">{user.username}<div className="text-xs text-muted-foreground">{user.email} · {user.auth_provider === "ldap" ? "LDAP / AD" : "Локальная"}</div></td>
            <td className="p-2"><select aria-label={`Роль ${user.username}`} value={user.role} disabled={busy || user.username === me?.subject || user.auth_provider === "ldap"} className="border border-border p-1 bg-background" onChange={event => void change(`/api/v1/users/${user.id}`, { role: event.target.value }, "PATCH")}>{Object.entries(roles).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></td>
            <td className="p-2">{user.is_active ? "Активен" : "Заблокирован"}</td><td className="p-2"><div className="flex flex-wrap gap-2"><Button size="sm" variant="outline" disabled={busy || user.username === me?.subject} onClick={() => void change(`/api/v1/users/${user.id}`, { is_active: !user.is_active }, "PATCH")}>{user.is_active ? "Заблокировать" : "Разблокировать"}</Button>
              {user.auth_provider === "local" && <Button size="sm" variant="outline" disabled={busy} onClick={() => setTarget(user)}>Сбросить пароль</Button>}</div></td></tr>)}
        </tbody></table></div>
        <div className="flex gap-3"><Button variant="outline" disabled={!page} onClick={() => setPage(page - 1)}>Назад</Button><Button variant="outline" disabled={(page + 1) * 100 >= (users.data?.total ?? 0)} onClick={() => setPage(page + 1)}>Далее</Button></div>
      </SettingsSection>
      {target && <SettingsSection title={`Сброс пароля: ${target.username}`}><form className="space-y-3 border border-border p-4" onSubmit={async event => { event.preventDefault(); const data = new FormData(event.currentTarget); if (await change(`/api/v1/users/${target.id}/password`, { password: data.get("password") }, "POST")) setTarget(null) }}>
        <label className="block text-sm">Новый пароль<Input name="password" type="password" required minLength={10} maxLength={1024} autoComplete="new-password" /></label>
        <div className="flex gap-3"><Button type="submit" disabled={busy}>Сохранить пароль</Button><Button type="button" variant="outline" onClick={() => setTarget(null)}>Отмена</Button></div>
      </form></SettingsSection>}
    </>}
  </SettingsShell>
}
