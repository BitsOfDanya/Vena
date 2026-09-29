"use client"

import { useQuery } from "@tanstack/react-query"

import { getSpatialStatus } from "@/entities/infrastructure/api/spatial-client"
import { getHealth } from "@/entities/system"
import { useNotificationSettings } from "@/entities/notification"
import { apiFetch } from "@/shared/api/http"
import { dataMode, environmentLabel } from "@/shared/config/env"
import { z } from "zod"

import { SettingsSection, SettingsShell, StateTag } from "./settings-shell"

const SmvuStatusSchema = z.object({
  configured: z.boolean(),
  fresh: z.boolean().optional(),
  last_event_count: z.number().optional(),
  age_seconds: z.number().nullable().optional(),
  detail: z.string().optional(),
})

async function getSmvuStatus() {
  try {
    return SmvuStatusSchema.parse(await apiFetch<unknown>("/api/v1/smvu/status"))
  } catch {
    return { configured: false, fresh: false, detail: "unavailable" }
  }
}

export function SettingsIntegrationsPage() {
  const health = useQuery({ queryKey: ["system", "health"], queryFn: getHealth, retry: false, staleTime: 30_000 })
  const settings = useNotificationSettings()
  const spatial = useQuery({ queryKey: ["system", "spatial-status"], queryFn: getSpatialStatus, retry: false, staleTime: 30_000 })
  const smvu = useQuery({ queryKey: ["system", "smvu-status"], queryFn: getSmvuStatus, retry: false, staleTime: 30_000 })
  const apiState = health.isPending ? "not_configured" : health.isError ? "not_configured" : "configured"
  const spatialState = spatial.data?.configured ? "configured" : "not_configured"
  const smvuState = smvu.data?.configured ? (smvu.data.fresh ? "configured" : "not_configured") : "not_configured"

  return (
    <SettingsShell title="Интеграции" descriptor={`среда ${environmentLabel}`}>
      <SettingsSection title="Источники данных">
        <ul className="border border-border bg-elevated">
          <li className="flex items-center gap-4 border-b border-border-soft px-5 py-3">
            <span className="w-48 text-[14px]">Журнал событий</span>
            <span className="text-[13px] text-muted-foreground">
              {dataMode === "live" ? "Подключён источник событий" : "Демонстрационный снимок данных"}
            </span>
            <span className="ml-auto">
              <StateTag state={dataMode === "live" ? "configured" : "not_configured"} />
            </span>
          </li>
          <li className="flex items-center gap-4 border-b border-border-soft px-5 py-3">
            <span className="w-48 text-[14px]">Поток SMVU</span>
            <span className="text-[13px] text-muted-foreground">
              {smvu.data?.configured
                ? smvu.data.fresh
                  ? `Свежий батч · ${smvu.data.last_event_count ?? 0} событий`
                  : `Последний батч устарел · возраст ${smvu.data.age_seconds ?? "—"} с`
                : "POST /api/v1/smvu/events — хук свежести ≤5 мин"}
            </span>
            <span className="ml-auto">
              <StateTag state={smvuState} />
            </span>
          </li>
          <li className="flex items-center gap-4 border-b border-border-soft px-5 py-3">
            <span className="w-48 text-[14px]">VENA API</span>
            <span className="text-[13px] text-muted-foreground">
              {health.isError ? "Сервис недоступен" : health.isPending ? "Проверка соединения" : "Сервис отвечает"}
            </span>
            <span className="ml-auto">
              <StateTag state={apiState} />
            </span>
          </li>
          <li className="flex items-center gap-4 px-5 py-3">
            <span className="w-48 text-[14px]">Пространственные данные (GeoJSON/WKT)</span>
            <span className="text-[13px] text-muted-foreground">
              {spatial.data?.configured
                ? `${spatial.data.source ?? "слой"} · ${spatial.data.asset_count} активов · режим карты`
                : "Режим карты включится после подключения"}
            </span>
            <span className="ml-auto">
              <StateTag state={spatialState} />
            </span>
          </li>
        </ul>
      </SettingsSection>

      <SettingsSection title="Каналы доставки">
        <ul className="border border-border bg-elevated">
          {(settings.data?.channels ?? []).map((channel) => (
            <li key={channel.id} className="flex items-center gap-4 border-b border-border-soft px-5 py-3 last:border-b-0">
              <span className="w-48 text-[14px]">{channel.name}</span>
              <span className="text-[13px] text-muted-foreground">{channel.detail}</span>
              <span className="ml-auto">
                <StateTag state={channel.state} />
              </span>
            </li>
          ))}
        </ul>
      </SettingsSection>
    </SettingsShell>
  )
}
