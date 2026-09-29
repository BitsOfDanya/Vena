"use client"

import * as React from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useAuthSession } from "@/features/auth"
import { apiFetch, ApiError } from "@/shared/api/http"
import { Button } from "@/shared/ui/button"
import { Input } from "@/shared/ui/input"
import { SettingsSection } from "./settings-shell"

type Run = { id: string; kind: string; status: string; started_at: string; detail: string; rows?: number; accepted?: number; created?: number; updated?: number; unchanged?: number; rejected?: number; errors?: { row: number; message: string }[] }
type RegistryRow = { asset_id: string; name: string; object_id: string; equipment_type: string; status: string }
type IntegrationStatus = { equipment_count: number; journal_events: number; pending_publications: number; sync_configured: boolean; ldap_configured: boolean; upload_configured: boolean; data_source: string; prediction_count: number; worker: { state?: string; detail?: string }; runs: Run[] }
const sourceLabel: Record<string, string> = { journal: "Реальный журнал", demo: "Демонстрационный снимок", unknown: "Источник не подтверждён" }
const statusLabel: Record<string, string> = { success: "Применено", validated: "Проверено", failed: "Ошибка", running: "Выполняется" }

export function DataImportPanel() {
  const { me } = useAuthSession()
  const admin = me?.role === "admin"
  const queryClient = useQueryClient()
  const status = useQuery({ queryKey: ["integrations"], queryFn: () => apiFetch<IntegrationStatus>("/api/v1/integrations/status"), refetchInterval: 10_000 })
  const [page, setPage] = React.useState(0)
  const registry = useQuery({ queryKey: ["equipment", page], queryFn: () => apiFetch<{ total: number; items: RegistryRow[] }>(`/api/v1/equipment?offset=${page * 50}&limit=50`) })
  const [kind, setKind] = React.useState("channels")
  const [file, setFile] = React.useState<File | null>(null)
  const [run, setRun] = React.useState<Run | null>(null)
  const [busy, setBusy] = React.useState(false)
  const [error, setError] = React.useState("")
  async function perform(task: () => Promise<void>) {
    setBusy(true); setError("")
    try { await task(); await queryClient.invalidateQueries() }
    catch (err) { setError(err instanceof ApiError ? err.detail : "Не удалось выполнить операцию. Попробуйте снова.") }
    finally { setBusy(false) }
  }
  return <>
    <SettingsSection title="Данные стенда">
      {status.isError ? <p role="alert">Не удалось получить состояние интеграций.</p> : <div className="border border-border bg-elevated p-4 text-sm space-y-2">
        <p>{sourceLabel[status.data?.data_source ?? "unknown"]} · прогнозов: {status.data?.prediction_count ?? 0}</p>
        <p>{status.data?.worker.detail}</p>
        <p>Каналов в реестре: {status.data?.equipment_count ?? 0} · событий загружено: {status.data?.journal_events ?? 0}</p>
        {!!status.data?.pending_publications && <p>Передача данных в обработку: {status.data.pending_publications} задач. Большой журнал может обрабатываться несколько минут.</p>}
        <p>LDAP / AD: {status.data?.ldap_configured ? "Настроен" : "Ожидает параметров корпоративного каталога"}</p>
        <p>Учётная система: {status.data?.sync_configured ? "Синхронизация по расписанию включена" : "Подключение не настроено"}</p>
        {admin && <Button disabled={busy || !status.data?.sync_configured} variant="outline" onClick={() => perform(async () => { const result = await apiFetch<Run>("/api/v1/equipment/sync", { method: "POST" }); setRun(result); if (result.status === "failed") setError(result.detail) })}>Синхронизировать реестр</Button>}
      </div>}
    </SettingsSection>
    {admin && <SettingsSection title="Загрузка CSV / XLSX" description="Сначала загрузите справочник с колонкой ид_объект, затем журнал. Файл применяется целиком после проверки. CSV — UTF-8, до 256 МБ и 1 000 000 строк; XLSX — один лист без формул.">
      <form className="space-y-3 border border-border bg-elevated p-4" onSubmit={(event) => { event.preventDefault(); if (!file) return; void perform(async () => { const body = new FormData(); body.append("file", file); setRun(await apiFetch<Run>(`/api/v1/imports?kind=${kind}`, { method: "POST", body })) }) }}>
        <label className="block text-sm">Тип данных<select className="ml-3 border border-border bg-background p-2" disabled={busy} value={kind} onChange={(event) => { setKind(event.target.value); setRun(null) }}><option value="channels">Справочник каналов</option><option value="journal">Журнал событий</option></select></label>
        <label className="block text-sm" htmlFor="data-file">Файл CSV или XLSX</label>
        <Input id="data-file" type="file" accept=".csv,.xlsx" disabled={busy} onChange={(event) => { setFile(event.target.files?.[0] ?? null); setRun(null) }} />
        <div className="flex flex-wrap gap-3"><Button type="submit" disabled={!file || busy || !status.data?.upload_configured}>{busy ? "Обработка…" : "Загрузить и проверить"}</Button>
          <Button type="button" variant="outline" disabled={busy} onClick={() => perform(async () => {
            const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1/imports/template/${kind}.xlsx`, { credentials: "include" }); if (!response.ok) throw new Error(); const url = URL.createObjectURL(await response.blob()); const a = document.createElement("a"); a.href = url; a.download = `${kind}.xlsx`; a.click(); URL.revokeObjectURL(url)
          })}>Скачать шаблон</Button></div>
      </form>
      {run && <div className="border border-border bg-elevated p-4 text-sm space-y-2" role="status">
        <p>{statusLabel[run.status] ?? run.status} · строк: {run.rows ?? 0} · принято: {run.accepted ?? 0} · ошибок: {Math.max(run.rejected ?? 0, run.errors?.length ?? 0)}</p>
        <p>{run.detail}</p>
        {run.status === "success" && <p>Добавлено: {run.created ?? 0} · обновлено: {run.updated ?? 0} · без изменений: {run.unchanged ?? 0}</p>}
        {run.errors?.map((item, index) => <p key={index} className="text-status-critical">{item.row ? `Строка ${item.row}: ` : ""}{item.message}</p>)}
        {run.status === "validated" && <Button disabled={busy} onClick={() => perform(async () => { setRun(await apiFetch<Run>(`/api/v1/imports/${run.id}/apply`, { method: "POST" })) })}>Применить загрузку</Button>}
      </div>}
    </SettingsSection>}
    {error && <p role="alert" className="text-status-critical text-sm">{error}</p>}
    <SettingsSection title="Реестр оборудования" description="Сопоставление по идентификатору канала. Отсутствие записи в новом файле не удаляет оборудование.">
      <div className="overflow-x-auto border border-border"><table className="w-full text-left text-sm"><thead><tr>{["Канал", "Название", "Объект", "Тип"].map(label => <th key={label} className="p-2">{label}</th>)}</tr></thead><tbody>{registry.data?.items.map(row => <tr key={row.asset_id} className="border-t border-border-soft"><td className="p-2">{row.asset_id}</td><td className="p-2">{row.name}</td><td className="p-2">{row.object_id}</td><td className="p-2">{row.equipment_type}</td></tr>)}</tbody></table></div>
      {registry.isError && <p role="alert">Не удалось загрузить реестр.</p>}
      {registry.data?.total === 0 && <p className="text-sm text-muted-foreground">Справочник ещё не загружен.</p>}
      <div className="flex gap-3"><Button variant="outline" disabled={!page} onClick={() => setPage(page - 1)}>Назад</Button><Button variant="outline" disabled={(page + 1) * 50 >= (registry.data?.total ?? 0)} onClick={() => setPage(page + 1)}>Далее</Button></div>
    </SettingsSection>
    <SettingsSection title="История загрузок и синхронизации"><ul className="text-sm space-y-2">{status.data?.runs.map(item => <li key={item.id}>{new Date(item.started_at).toLocaleString("ru-RU")} · {item.kind === "channels" ? "Справочник" : item.kind === "journal" ? "Журнал" : "Синхронизация"} · {statusLabel[item.status]} · принято {item.accepted ?? 0}</li>)}</ul></SettingsSection>
  </>
}
