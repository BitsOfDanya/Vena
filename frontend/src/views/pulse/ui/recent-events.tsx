"use client"

import { useQuery } from "@tanstack/react-query"
import Link from "next/link"

import { useAuthSession } from "@/features/auth"
import { apiFetch } from "@/shared/api/http"
import { cn } from "@/shared/lib/utils"

type EventFeed = {
  latest_at: string | null
  from: string | null
  has_more: boolean
  items: { event_id: string; channel_id: string; name: string; object_id: string | null; ts: string; value: string; alarm: boolean }[]
}

const TIME = new Intl.DateTimeFormat("ru-RU", { timeZone: "Europe/Moscow", hour: "2-digit", minute: "2-digit" })
const DAY = new Intl.DateTimeFormat("ru-RU", { timeZone: "Europe/Moscow", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" })

export function RecentEvents({ hours, onSelect }: { hours: number; onSelect: (id: string) => void }) {
  const { me } = useAuthSession()
  const events = useQuery({
    queryKey: ["recent-events", hours],
    queryFn: () => apiFetch<EventFeed>(`/api/v1/events/recent?hours=${hours}&limit=60`),
    refetchInterval: 30_000,
  })
  const latest = events.data?.latest_at

  return (
    <section aria-label="События журнала" className="flex min-h-0 flex-col rounded-lg border border-border bg-elevated shadow-[var(--shadow-card)]">
      <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
        <div>
          <h2 className="text-[16px] font-semibold">События журнала</h2>
          <p className="mt-0.5 text-[12.5px] text-muted-foreground">
            {latest ? `Тревоги и смены состояния за ${hours} ч до ${DAY.format(new Date(latest))}` : "Тревоги и смены состояния СМВУ"}
          </p>
        </div>
        {me?.role === "admin" ? (
          <Link href="/settings/integrations" className="shrink-0 text-[12.5px] font-medium text-vena hover:underline hover:underline-offset-4">
            Загрузить данные
          </Link>
        ) : null}
      </div>
      {events.isPending ? (
        <p className="px-4 py-6 text-[13px] text-muted-foreground">Загрузка событий…</p>
      ) : events.isError ? (
        <p role="alert" className="px-4 py-6 text-[13px] text-status-critical">
          Не удалось получить события.{" "}
          <button type="button" className="underline" onClick={() => void events.refetch()}>
            Повторить
          </button>
        </p>
      ) : !events.data?.items.length ? (
        <p className="px-4 py-6 text-[13px] text-muted-foreground">
          {latest ? "За выбранное окно значимых событий нет." : "Журнал ещё не загружен. Администратор может добавить справочник и журнал в «Интеграциях»."}
        </p>
      ) : (
        <ul className="max-h-[440px] divide-y divide-border overflow-y-auto">
          {events.data.items.map((event) => (
            <li key={event.event_id}>
              <button
                type="button"
                onClick={() => onSelect(event.channel_id)}
                className="flex w-full cursor-pointer items-start gap-3 px-4 py-2.5 text-left outline-none hover:bg-accent/50 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/60"
              >
                <span
                  aria-hidden
                  className={cn("mt-1.5 size-2 shrink-0 rounded-full", event.alarm ? "bg-status-critical" : "bg-status-attention")}
                />
                <span className="min-w-0 flex-1">
                  <span className="flex items-baseline gap-2">
                    <span className="truncate text-[13.5px] font-medium">{event.name}</span>
                    <span className="ml-auto shrink-0 text-[12px] text-faint tabular-nums">{TIME.format(new Date(event.ts))}</span>
                  </span>
                  <span className="block truncate text-[12.5px] text-muted-foreground">
                    <span className={event.alarm ? "text-status-critical" : "text-foreground"}>{event.value}</span>
                    {event.object_id ? ` · объект ${event.object_id}` : ""}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
