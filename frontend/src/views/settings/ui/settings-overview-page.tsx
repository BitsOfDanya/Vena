"use client"

import Link from "next/link"
import { useQuery } from "@tanstack/react-query"

import { useNotificationSettings } from "@/entities/notification"
import { getAuthMe } from "@/entities/system"

import { SettingsSection, SettingsShell, StateTag } from "./settings-shell"

export function SettingsOverviewPage() {
  const settings = useNotificationSettings()
  const me = useQuery({ queryKey: ["system", "auth-me"], queryFn: getAuthMe, retry: false, staleTime: 30_000 })
  const channels = settings.data?.channels ?? []
  const digest = settings.data?.digests[0]

  return (
    <SettingsShell title="Настройки" descriptor="рабочая область">
      <SettingsSection title="Учётная запись">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 border border-border bg-elevated px-5 py-4 text-[14px]">
          <div>
            <dt className="text-[12px] text-faint">Пользователь</dt>
            <dd className="mt-0.5 font-mono text-[13px]">{me.data?.subject ?? "Дежурный инженер"}</dd>
          </div>
          <div>
            <dt className="text-[12px] text-faint">Роль</dt>
            <dd className="mt-0.5 font-mono text-[13px]">{me.data?.role ?? "dispatcher"}</dd>
          </div>
          <div>
            <dt className="text-[12px] text-faint">Часовой пояс</dt>
            <dd className="mt-0.5 font-mono text-[13px]">Europe/Moscow</dd>
          </div>
          <div>
            <dt className="text-[12px] text-faint">Язык интерфейса</dt>
            <dd className="mt-0.5">Русский</dd>
          </div>
        </dl>
        <div className="flex flex-wrap gap-4">
          <Link
            href="/settings/security"
            className="text-[13px] text-vena underline-offset-4 hover:underline focus-visible:ring-2 focus-visible:ring-ring/60 focus-visible:outline-none"
          >
            Открыть безопасность
          </Link>
          <Link
            href="/settings/audit"
            className="text-[13px] text-vena underline-offset-4 hover:underline focus-visible:ring-2 focus-visible:ring-ring/60 focus-visible:outline-none"
          >
            Открыть журнал аудита
          </Link>
        </div>
      </SettingsSection>

      <SettingsSection title="Каналы уведомлений" description="Каналы доставки настраиваются на странице «Уведомления».">
        <ul className="border border-border bg-elevated">
          {channels.map((channel) => (
            <li key={channel.id} className="flex items-center gap-4 border-b border-border-soft px-5 py-3 last:border-b-0">
              <span className="text-[14px]">{channel.name}</span>
              <span className="text-[13px] text-muted-foreground">{channel.detail}</span>
              <span className="ml-auto">
                <StateTag state={channel.state} />
              </span>
            </li>
          ))}
        </ul>
        <Link
          href="/settings/notifications"
          className="inline-block text-[13px] text-vena underline-offset-4 hover:underline focus-visible:ring-2 focus-visible:ring-ring/60 focus-visible:outline-none"
        >
          Открыть настройки уведомлений
        </Link>
      </SettingsSection>

      {digest ? (
        <SettingsSection title="Ежедневная сводка">
          <div className="border border-border bg-elevated px-5 py-4">
            <p className="text-[14px] font-medium">{digest.name}</p>
            <p className="mt-1 font-mono text-[13px] text-muted-foreground tabular-nums">
              каждый день · {String(digest.hour).padStart(2, "0")}:{String(digest.minute).padStart(2, "0")} МСК
            </p>
          </div>
        </SettingsSection>
      ) : null}
    </SettingsShell>
  )
}
