import { apiFetch } from "@/shared/api/http"

import type { Notification, NotificationRepository, NotificationSettings, SystemNotice } from "../model/types"

type ApiNotification = {
  id: string
  type: Notification["type"]
  severity: "info" | "attention" | "critical"
  title: string
  description: string
  asset_id: string | null
  pattern_id: string | null
  action_id: string | null
  created_at: string
  status: Notification["status"]
  read_at: string | null
  acknowledged_at: string | null
  resolved_at: string | null
}

function time(value: string | null): number | null {
  return value === null ? null : Date.parse(value)
}

function toNotification(item: ApiNotification): Notification {
  return {
    id: item.id,
    type: item.type,
    severity: item.severity === "attention" ? "warning" : item.severity,
    title: item.title,
    description: item.description,
    assetId: item.asset_id,
    patternId: item.pattern_id,
    createdAt: Date.parse(item.created_at),
    status: item.status,
    readAt: time(item.read_at),
    acknowledgedAt: time(item.acknowledged_at),
    resolvedAt: time(item.resolved_at),
  }
}

async function list(): Promise<Notification[]> {
  const items = await apiFetch<ApiNotification[]>("/api/v1/notifications?limit=100")
  return items.map(toNotification)
}

async function patch(id: string, body: Record<string, unknown>): Promise<Notification[]> {
  await apiFetch<ApiNotification>(`/api/v1/notifications/${id}`, { method: "PATCH", body: JSON.stringify(body) })
  return list()
}

export const apiNotificationRepository: NotificationRepository = {
  list,
  async markRead(ids) {
    for (const id of ids) {
      await apiFetch(`/api/v1/notifications/${id}`, { method: "PATCH", body: JSON.stringify({ read: true }) })
    }
    return list()
  },
  acknowledge: (id) => patch(id, { status: "acknowledged" }),
  resolve: (id) => patch(id, { status: "resolved" }),
}

type ApiNotice = {
  id: string
  kind: SystemNotice["kind"]
  severity: "info" | "attention" | "critical"
  title: string
  description: string
  href: string | null
  dismissible: boolean
}

export async function getApiSystemNotices(): Promise<SystemNotice[]> {
  const items = await apiFetch<ApiNotice[]>("/api/v1/system/notices")
  return items.map((item) => ({
    ...item,
    severity: item.severity === "attention" ? "warning" : item.severity,
  }))
}

type ApiSettings = {
  channels: { id: string; name: string; state: "configured" | "not_configured" | "disabled"; available: boolean; detail: string }[]
  recipients: { id: string; name: string; emails: string[]; enabled: boolean }[]
  rules: {
    id: string
    trigger: string
    severity: "info" | "attention" | "critical"
    recipients: string[]
    channels: string[]
    cooldown_minutes: number
    enabled: boolean
  }[]
  digest: { id: string; name: string; enabled: boolean; hour: number; minute: number; recipients: string[]; sections: string[] }
}

export async function getApiNotificationSettings(): Promise<NotificationSettings> {
  const data = await apiFetch<ApiSettings>("/api/v1/settings/notifications")
  const email = await apiFetch<{ configured: boolean; provider: string; from_address: string | null }>(
    "/api/v1/integrations/email/status"
  )
  return {
    channels: data.channels.map((channel) => ({
      id: channel.id as NotificationSettings["channels"][number]["id"],
      name: channel.name,
      state: channel.state,
      available: channel.available,
      detail: channel.detail,
    })),
    recipients: data.recipients.map((group) => ({
      id: group.id,
      name: group.name,
      members: group.emails.length,
      emails: group.emails,
    })),
    rules: data.rules.map((rule) => ({
      id: rule.id,
      trigger: rule.trigger as NotificationSettings["rules"][number]["trigger"],
      severity: rule.severity === "attention" ? "warning" : rule.severity,
      recipients: rule.recipients,
      channels: rule.channels as NotificationSettings["rules"][number]["channels"],
      cooldownHours: Math.round(rule.cooldown_minutes / 60),
      enabled: rule.enabled,
    })),
    digests: [
      {
        id: data.digest.id,
        name: data.digest.name,
        hour: data.digest.hour,
        minute: data.digest.minute,
        recipients: data.digest.recipients,
        sections: data.digest.sections as NotificationSettings["digests"][number]["sections"],
        enabled: data.digest.enabled,
      },
    ],
    email: {
      senderName: "VENA",
      senderAddress: email.from_address ?? "",
      state: email.configured ? "configured" : "not_configured",
    },
  }
}

export async function sendTestEmail(recipient: string): Promise<void> {
  await apiFetch("/api/v1/notifications/test", { method: "POST", body: JSON.stringify({ recipient }) })
}
