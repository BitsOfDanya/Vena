"use client"

import Link from "next/link"
import { useQuery } from "@tanstack/react-query"
import { useAuthSession } from "@/features/auth"
import { apiFetch } from "@/shared/api/http"
import { Button } from "@/shared/ui/button"
import { cn } from "@/shared/lib/utils"

type EventFeed = {
  latest_at: string | null
  from: string | null
  has_more: boolean
  items: { event_id: string; channel_id: string; name: string; object_id: string | null; ts: string; value: string; alarm: boolean }[]
}

export function RecentEvents({ hours, onSelect }: { hours: number; onSelect: (id: string) => void }) {
  const { me } = useAuthSession()
  const events = useQuery({ queryKey: ["recent-events", hours], queryFn: () => apiFetch<EventFeed>(`/api/v1/events/recent?hours=${hours}`), refetchInterval: 10_000 })
  const latest = events.data?.latest_at
  return <section aria-label="События журнала" className="flex min-h-0 flex-1 flex-col border-t border-border-soft px-6 py-3">
    <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
      <div><h2 className="text-[13px] font-medium tracking-[0.1em] text-muted-foreground uppercase">События журнала</h2>
        <p className="mt-1 text-[12px] text-faint">{latest ? `Последние ${hours} ч журнала · данные по ${new Date(latest).toLocaleString("ru-RU", { timeZone: "Europe/Moscow" })}` : "Исторический журнал и входящий поток СМВУ"}</p></div>
      {me?.role === "admin" && <Button size="sm" variant="outline" asChild><Link href="/settings/integrations">Загрузить CSV / XLSX</Link></Button>}
    </div>
    {events.isPending ? <p className="text-sm text-muted-foreground">Загрузка событий…</p> : events.isError ? <p role="alert" className="text-sm text-status-critical">Не удалось получить события. <button className="underline" onClick={() => void events.refetch()}>Повторить</button></p> : !events.data?.items.length ? <p className="py-4 text-sm text-muted-foreground">События ещё не загружены. Добавьте справочник каналов и журнал в разделе «Интеграции».</p> : <div className="min-h-0 overflow-auto border border-border-soft">
      <table className="w-full text-left text-[13px]"><thead className="sticky top-0 bg-surface text-[11px] text-muted-foreground"><tr>{["Время, МСК", "Объект", "Канал", "Состояние"].map(label => <th key={label} className="px-3 py-2 font-medium">{label}</th>)}</tr></thead><tbody>{events.data.items.map(event => <tr key={event.event_id} className="border-t border-border-soft hover:bg-elevated">
        <td className="whitespace-nowrap px-3 py-2 font-mono text-[12px]">{new Date(event.ts).toLocaleString("ru-RU", { timeZone: "Europe/Moscow" })}</td>
        <td className="px-3 py-2">{event.object_id ?? "—"}</td>
        <td className="px-3 py-2"><button className="text-left text-vena hover:underline" onClick={() => onSelect(event.channel_id)}>{event.name}</button><span className="ml-2 font-mono text-[11px] text-faint">{event.channel_id}</span></td>
        <td className={cn("px-3 py-2", event.alarm && "text-status-attention")}><span>{event.value}</span>{event.alarm && <span className="ml-2 text-[11px]">Тревога</span>}</td>
      </tr>)}</tbody></table>
      {events.data.has_more && <p className="border-t border-border-soft p-3 text-xs text-muted-foreground">Показаны последние {events.data.items.length} событий выбранного периода.</p>}
    </div>}
  </section>
}
