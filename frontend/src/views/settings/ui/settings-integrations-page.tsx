"use client"

import { useQuery } from "@tanstack/react-query"

import { getHealth } from "@/entities/system"
import { useNotificationSettings } from "@/entities/notification"
import { dataMode, environmentLabel } from "@/shared/config/env"

import { SettingsSection, SettingsShell, StateTag } from "./settings-shell"

export function SettingsIntegrationsPage() {
  const health = useQuery({ queryKey: ["system", "health"], queryFn: getHealth, retry: false, staleTime: 30_000 })
  const settings = useNotificationSettings()
  const apiState = health.isPending ? "not_configured" : health.isError ? "not_configured" : "configured"

  return (
    <SettingsShell title="Integrations" descriptor={`environment ${environmentLabel}`}>
      <SettingsSection title="Data sources">
        <ul className="border border-border bg-elevated">
          <li className="flex items-center gap-4 border-b border-border-soft px-5 py-3">
            <span className="w-48 text-[14px]">Event journal</span>
            <span className="text-[13px] text-muted-foreground">
              {dataMode === "live" ? "Подключён источник событий" : "Демонстрационный снимок данных"}
            </span>
            <span className="ml-auto">
              <StateTag state={dataMode === "live" ? "configured" : "not_configured"} />
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
            <span className="w-48 text-[14px]">Spatial data (GeoJSON/WKT)</span>
            <span className="text-[13px] text-muted-foreground">Режим карты включится после подключения</span>
            <span className="ml-auto">
              <StateTag state="not_configured" />
            </span>
          </li>
        </ul>
      </SettingsSection>

      <SettingsSection title="Delivery channels">
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
