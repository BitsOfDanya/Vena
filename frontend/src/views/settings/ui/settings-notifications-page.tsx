"use client"

import * as React from "react"
import { toast } from "sonner"

import {
  DIGEST_SECTION_LABEL,
  sendTestNotification,
  RULE_TRIGGER_LABEL,
  useNotificationSettings,
  type NotificationChannelId,
} from "@/entities/notification"
import { Button } from "@/shared/ui/button"
import { LoadingBar } from "@/shared/ui/state-message"

import { SettingsSection, SettingsShell, StateTag } from "./settings-shell"

const CHANNEL_LABEL: Record<NotificationChannelId, string> = {
  in_app: "В приложении",
  email: "Email",
  webhook: "Webhook",
  telegram: "Telegram",
  teams: "Microsoft Teams",
}

export function SettingsNotificationsPage() {
  const settings = useNotificationSettings()
  const data = settings.data
  const [rules, setRules] = React.useState<Record<string, boolean>>({})
  const [testing, setTesting] = React.useState(false)

  const enabled = (id: string, fallback: boolean) => rules[id] ?? fallback

  return (
    <SettingsShell title="Уведомления" descriptor="каналы · правила · получатели">
      {!data ? (
        <LoadingBar className="min-h-32" />
      ) : (
        <>
          <SettingsSection title="Каналы" description="Отправка появится после подключения бэкенда и почтового шлюза.">
            <ul className="border border-border bg-elevated">
              {data.channels.map((channel) => (
                <li key={channel.id} className="flex flex-wrap items-center gap-4 border-b border-border-soft px-5 py-3 last:border-b-0">
                  <span className="w-40 text-[14px]">{channel.name}</span>
                  <span className="text-[13px] text-muted-foreground">{channel.detail}</span>
                  <span className="ml-auto flex items-center gap-3">
                    <StateTag state={channel.state} />
                    <Button variant="outline" size="sm" disabled={!channel.available} onClick={() => toast.info(`${channel.name}: настройка требует бэкенда`)}>
                      Настроить
                    </Button>
                  </span>
                </li>
              ))}
            </ul>
          </SettingsSection>

          <SettingsSection title="Email" description="Пароль SMTP во фронтенде не хранится: параметры задаются на сервере.">
            <div className="space-y-3 border border-border bg-elevated px-5 py-4">
              <div className="flex items-center gap-4">
                <span className="w-40 text-[13px] text-muted-foreground">Имя отправителя</span>
                <span className="font-mono text-[13px]">{data.email.senderName}</span>
                <span className="ml-auto">
                  <StateTag state={data.email.state} />
                </span>
              </div>
              <div className="flex items-center gap-4">
                <span className="w-40 text-[13px] text-muted-foreground">Адрес отправителя</span>
                <span className="font-mono text-[13px] text-faint">{data.email.senderAddress || "не задан"}</span>
              </div>
              <div className="flex items-center gap-4">
                <span className="w-40 text-[13px] text-muted-foreground">Группы получателей</span>
                <span className="text-[13px]">{data.recipients.map((group) => group.name).join(", ")}</span>
              </div>
              <div className="flex gap-2 pt-1">
                <Button variant="outline" size="sm" onClick={() => toast.info("Настройка почты требует подключения бэкенда")}>
                  Настроить
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={data.email.state !== "configured" || testing}
                  title={
                    data.email.state === "configured"
                      ? undefined
                      : "Доступно после настройки SMTP на сервере"
                  }
                  onClick={async () => {
                    setTesting(true)
                    try {
                      await sendTestNotification("dispatcher@example.com")
                      toast.success("Тестовое письмо отправлено")
                    } catch (error) {
                      toast.error("Не удалось отправить письмо", {
                        description: error instanceof Error ? error.message : undefined,
                      })
                    } finally {
                      setTesting(false)
                    }
                  }}
                >
                  Отправить тестовое уведомление
                </Button>
              </div>
            </div>
          </SettingsSection>

          <SettingsSection title="Правила">
            <ul className="border border-border bg-elevated">
              {data.rules.map((rule) => (
                <li key={rule.id} className="border-b border-border-soft px-5 py-3 last:border-b-0">
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="font-mono text-[12px] text-faint">{rule.id}</span>
                    <span className="text-[14px] font-medium">{RULE_TRIGGER_LABEL[rule.trigger]}</span>
                    <label className="ml-auto flex items-center gap-2 text-[13px] text-muted-foreground">
                      <input
                        type="checkbox"
                        checked={enabled(rule.id, rule.enabled)}
                        onChange={(event) => setRules((current) => ({ ...current, [rule.id]: event.target.checked }))}
                        className="size-4 accent-[var(--vena)]"
                      />
                      Включено
                    </label>
                  </div>
                  <p className="mt-1 text-[13px] text-muted-foreground">
                    уведомить {rule.recipients.map((id) => data.recipients.find((group) => group.id === id)?.name ?? id).join(", ")} ·{" "}
                    {rule.channels.map((channel) => CHANNEL_LABEL[channel]).join(" + ")} · пауза{" "}
                    <span className="font-mono tabular-nums">{rule.cooldownHours}h</span>
                  </p>
                </li>
              ))}
            </ul>
          </SettingsSection>

          <SettingsSection title="Получатели">
            <ul className="border border-border bg-elevated">
              {data.recipients.map((group) => (
                <li key={group.id} className="flex items-center gap-4 border-b border-border-soft px-5 py-3 last:border-b-0">
                  <span className="w-48 text-[14px]">{group.name}</span>
                  <span className="font-mono text-[13px] text-muted-foreground tabular-nums">{group.members} участников</span>
                  <span className="ml-auto text-[13px] text-faint">
                    {group.emails.length > 0 ? group.emails.join(", ") : "адреса задаются на сервере"}
                  </span>
                </li>
              ))}
            </ul>
          </SettingsSection>

          <SettingsSection title="Ежедневная сводка">
            {data.digests.map((digest) => (
              <div key={digest.id} className="border border-border bg-elevated px-5 py-4">
                <div className="flex items-center gap-3">
                  <span className="text-[14px] font-medium">{digest.name}</span>
                  <span className="font-mono text-[13px] text-muted-foreground tabular-nums">
                    каждый день · {String(digest.hour).padStart(2, "0")}:{String(digest.minute).padStart(2, "0")}
                  </span>
                  <span className="ml-auto">
                    <StateTag state={digest.enabled ? "configured" : "disabled"} />
                  </span>
                </div>
                <p className="mt-1 text-[13px] text-muted-foreground">
                  {digest.recipients.map((id) => data.recipients.find((group) => group.id === id)?.name ?? id).join(", ")}
                </p>
                <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[13px] text-muted-foreground">
                  {digest.sections.map((section) => (
                    <li key={section}>· {DIGEST_SECTION_LABEL[section]}</li>
                  ))}
                </ul>
              </div>
            ))}
          </SettingsSection>
        </>
      )}
    </SettingsShell>
  )
}
