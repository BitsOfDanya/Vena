"use client"

import * as React from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useAuthSession } from "@/features/auth"
import { RULE_TRIGGER_LABEL, type NotificationRuleTrigger } from "@/entities/notification"
import { apiFetch, ApiError } from "@/shared/api/http"
import { Button } from "@/shared/ui/button"
import { Input } from "@/shared/ui/input"
import { SettingsSection, SettingsShell, StateTag } from "./settings-shell"

type Group = { id: string; name: string; emails: string[]; enabled: boolean }
type Rule = { id: string; trigger: NotificationRuleTrigger; severity: string; recipients: string[]; channels: string[]; cooldown_minutes: number; enabled: boolean }
type Config = { recipients: Group[]; rules: Rule[]; digest: { enabled: boolean; hour: number; minute: number; timezone: string; recipients: string[] } }
type Delivery = { id: number; recipient: string; subject: string; status: string; attempts: number; detail: string; created_at: string }
const statuses: Record<string, string> = { pending: "В очереди", sent: "Принято SMTP", failed: "Ошибка", skipped: "Пропущено" }
const errorText = (error: unknown) => error instanceof ApiError ? error.detail : "Не удалось выполнить запрос"

export function SettingsNotificationsPage() {
  const { me } = useAuthSession()
  const admin = me?.role === "admin"
  const cache = useQueryClient()
  const config = useQuery({ queryKey: ["mail-settings"], queryFn: () => apiFetch<Config>("/api/v1/settings/notifications") })
  const smtp = useQuery({ queryKey: ["smtp-status"], queryFn: () => apiFetch<{ configured: boolean; from_address: string | null }>("/api/v1/integrations/email/status") })
  const deliveries = useQuery({ queryKey: ["mail-deliveries"], queryFn: () => apiFetch<{ counts: Record<string, number>; items: Delivery[] }>("/api/v1/integrations/email/deliveries"), enabled: admin, refetchInterval: 10_000 })
  const [draft, setDraft] = React.useState<Config | null>(null)
  const data = draft ?? config.data
  const [emails, setEmails] = React.useState<Record<string, string>>({})
  const [recipient, setRecipient] = React.useState("")
  const [busy, setBusy] = React.useState(false)
  const [message, setMessage] = React.useState("")
  const [error, setError] = React.useState("")
  const changeRule = (id: string, patch: Partial<Rule>) => data && setDraft({ ...data, rules: data.rules.map(rule => rule.id === id ? { ...rule, ...patch } : rule) })

  async function save() {
    if (!data) return
    setBusy(true); setError(""); setMessage("")
    try {
      const body = { ...data, recipients: data.recipients.map(group => ({ ...group, emails: (emails[group.id] ?? group.emails.join(", ")).split(/[,;\s]+/).filter(Boolean) })) }
      const saved = await apiFetch<Config>("/api/v1/settings/notifications", { method: "PUT", body: JSON.stringify(body) })
      cache.setQueryData(["mail-settings"], saved)
      await cache.invalidateQueries({ queryKey: ["notification-settings"] })
      setDraft(null); setEmails({}); setMessage("Получатели и правила сохранены")
    } catch (e) { setError(errorText(e)) } finally { setBusy(false) }
  }

  return <SettingsShell title="Уведомления" descriptor="электронная почта · правила · доставка">
    {error && <p role="alert" className="text-status-critical">{error}</p>}
    {message && <p role="status" className="text-sm">{message}</p>}
    <SettingsSection title="Почтовый сервер" description="SMTP-пароль хранится только на сервере. Письма из очереди отправляются автоматически; временные ошибки повторяются до шести попыток.">
      {smtp.isError ? <p role="alert">Не удалось проверить почтовый сервер</p> : <div className="flex items-center gap-4 text-sm"><StateTag state={smtp.data?.configured ? "configured" : "not_configured"} /><span>{smtp.data?.from_address ?? "Отправитель не настроен"}</span></div>}
      {admin && <form className="mt-4 flex max-w-xl flex-wrap gap-3" onSubmit={async event => {
        event.preventDefault(); setBusy(true); setError(""); setMessage("")
        try { const result = await apiFetch<{ detail: string }>("/api/v1/notifications/test", { method: "POST", body: JSON.stringify({ recipient }) }); setMessage(result.detail) }
        catch (e) { setError(errorText(e)) } finally { setBusy(false) }
      }}><label className="min-w-60 flex-1 text-sm">Адрес для проверки<Input aria-label="Адрес для проверки" type="email" required value={recipient} onChange={e => setRecipient(e.target.value)} placeholder="name@company.ru" /></label><Button className="self-end" type="submit" disabled={busy || !smtp.data?.configured}>Отправить проверочное письмо</Button></form>}
    </SettingsSection>
    {config.isError ? <p role="alert">Не удалось загрузить настройки</p> : !data ? <p>Загрузка настроек…</p> : <>
      {!admin && <p className="text-sm text-muted-foreground">Изменять получателей и правила может администратор.</p>}
      <fieldset disabled={!admin || busy} className="space-y-6">
        <SettingsSection title="Получатели" description="Введите адреса через запятую. Пустая группа не получает писем. Повторяющиеся адреса в нескольких группах получают одно письмо.">
          <div className="space-y-4">{data.recipients.map(group => <div key={group.id} className="border border-border p-4">
            <label className="mb-2 flex gap-3 text-sm"><input type="checkbox" checked={group.enabled} onChange={e => setDraft({ ...data, recipients: data.recipients.map(item => item.id === group.id ? { ...item, enabled: e.target.checked } : item) })} />{group.name}</label>
            <Input aria-label={`Email: ${group.name}`} value={emails[group.id] ?? group.emails.join(", ")} onChange={e => setEmails(current => ({ ...current, [group.id]: e.target.value }))} placeholder="name@company.ru, duty@company.ru" />
          </div>)}</div>
        </SettingsSection>
        <SettingsSection title="Правила" description="Новое событие — один пакет входящего потока или одна загрузка журнала. Прошлые тревоги из импортированного архива не выдаются за текущие аварии.">
          <div className="space-y-3">{data.rules.map(rule => <div key={rule.id} className="space-y-3 border border-border p-4 text-sm">
            <div className="flex flex-wrap items-center gap-4"><strong>{RULE_TRIGGER_LABEL[rule.trigger] ?? rule.trigger}</strong><label className="ml-auto flex gap-2"><input type="checkbox" checked={rule.enabled} onChange={e => changeRule(rule.id, { enabled: e.target.checked })} />Включено</label><label className="flex gap-2"><input type="checkbox" checked={rule.channels.includes("email")} onChange={e => changeRule(rule.id, { channels: e.target.checked ? [...rule.channels, "email"] : rule.channels.filter(channel => channel !== "email") })} />По почте</label></div>
            <div className="flex flex-wrap items-center gap-4">{data.recipients.map(group => <label className="flex gap-2" key={group.id}><input type="checkbox" checked={rule.recipients.includes(group.id)} onChange={e => changeRule(rule.id, { recipients: e.target.checked ? [...rule.recipients, group.id] : rule.recipients.filter(id => id !== group.id) })} />{group.name}</label>)}<label className="ml-auto flex items-center gap-2">Пауза, мин<Input className="w-24" type="number" min={0} max={10080} value={rule.cooldown_minutes} onChange={e => changeRule(rule.id, { cooldown_minutes: Number(e.target.value) })} /></label></div>
          </div>)}</div>
        </SettingsSection>
        <SettingsSection title="Утренняя сводка" description={`Расписание: ${String(data.digest.hour).padStart(2, "0")}:${String(data.digest.minute).padStart(2, "0")} · ${data.digest.timezone}`}>
          <label className="flex gap-2 text-sm"><input type="checkbox" checked={data.digest.enabled} onChange={e => setDraft({ ...data, digest: { ...data.digest, enabled: e.target.checked } })} />Отправлять ежедневную сводку</label>
        </SettingsSection>
        {admin && <Button onClick={() => void save()}>Сохранить настройки</Button>}
      </fieldset>
    </>}
    {admin && <SettingsSection title="Доставка писем" description="Последние 50 записей. «Принято SMTP» означает приём письма почтовым сервисом; получение адресатом проверяется в Resend.">
      {deliveries.isError ? <p role="alert">Не удалось загрузить журнал доставки</p> : <><p className="mb-3 text-sm">В очереди: {deliveries.data?.counts.pending ?? 0} · Ошибок: {deliveries.data?.counts.failed ?? 0}</p><div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr>{["Время", "Получатель", "Тема", "Статус", "Попытки"].map(label => <th className="p-2" key={label}>{label}</th>)}</tr></thead><tbody>{deliveries.data?.items.map(row => <tr key={row.id} className="border-t border-border"><td className="p-2 whitespace-nowrap">{new Date(row.created_at).toLocaleString("ru-RU")}</td><td className="p-2">{row.recipient || "—"}</td><td className="p-2">{row.subject || "—"}</td><td className="p-2">{statuses[row.status] ?? row.status}<p className="text-xs text-muted-foreground">{row.detail}</p></td><td className="p-2">{row.attempts}</td></tr>)}</tbody></table>{!deliveries.data?.items.length && <p className="p-3 text-sm text-muted-foreground">Отправок пока нет</p>}</div></>}
    </SettingsSection>}
  </SettingsShell>
}
