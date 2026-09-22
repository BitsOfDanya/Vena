import { DEMO_NOW } from "@/entities/infrastructure"
import { HOUR, MINUTE } from "@/shared/lib/time"

import type { Notification, NotificationRepository, NotificationSettings, SystemNotice } from "../model/types"

const STORAGE_KEY = "vena.notifications.v1"

function seed(): Notification[] {
  return [
    {
      id: "N-2051",
      type: "risk",
      severity: "critical",
      title: "P-0142 · risk 68/100",
      description: "Рост нетипичных переходов и повторные отказы за последние сутки.",
      assetId: "P-0142",
      patternId: null,
      createdAt: DEMO_NOW - 45 * MINUTE,
      status: "new",
      readAt: null,
      acknowledgedAt: null,
      resolvedAt: null,
    },
    {
      id: "N-2050",
      type: "pattern",
      severity: "warning",
      title: "Pattern 001 · 4 systems",
      description: "Связанная активность в системах водоотведения, вентиляции, дыма и питания.",
      assetId: null,
      patternId: "pattern-001",
      createdAt: DEMO_NOW - 2 * HOUR,
      status: "new",
      readAt: null,
      acknowledgedAt: null,
      resolvedAt: null,
    },
    {
      id: "N-2049",
      type: "risk",
      severity: "warning",
      title: "PH-0871 · risk 58/100",
      description: "Повторяющиеся изменения состояния питания на канале.",
      assetId: "PH-0871",
      patternId: null,
      createdAt: DEMO_NOW - 5 * HOUR,
      status: "acknowledged",
      readAt: DEMO_NOW - 4 * HOUR,
      acknowledgedAt: DEMO_NOW - 4 * HOUR,
      resolvedAt: null,
    },
    {
      id: "N-2048",
      type: "action",
      severity: "info",
      title: "A-1001 assigned to Бригада А",
      description: "Осмотр P-0142 запланирован в ближайшие 24 часа.",
      assetId: "P-0142",
      patternId: null,
      createdAt: DEMO_NOW - 2 * HOUR,
      status: "acknowledged",
      readAt: DEMO_NOW - 2 * HOUR,
      acknowledgedAt: DEMO_NOW - 2 * HOUR,
      resolvedAt: null,
    },
    {
      id: "N-2044",
      type: "action",
      severity: "info",
      title: "A-0997 completed",
      description: "Обслуживание выполнено, неисправность подтверждена.",
      assetId: "P-0142",
      patternId: null,
      createdAt: DEMO_NOW - 91 * HOUR,
      status: "resolved",
      readAt: DEMO_NOW - 91 * HOUR,
      acknowledgedAt: DEMO_NOW - 91 * HOUR,
      resolvedAt: DEMO_NOW - 91 * HOUR,
    },
  ]
}

let store: Notification[] | null = null

function load(): Notification[] {
  if (store) return store
  if (typeof window !== "undefined") {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY)
      if (raw) {
        store = JSON.parse(raw) as Notification[]
        return store
      }
    } catch {
      store = null
    }
  }
  store = seed()
  return store
}

function persist(next: Notification[]) {
  store = next
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    } catch {
      return
    }
  }
}

function sorted(list: Notification[]) {
  return [...list].sort((left, right) => right.createdAt - left.createdAt)
}

export const notificationRepository: NotificationRepository = {
  async list() {
    return sorted(load())
  },
  async markRead(ids, now) {
    const next = load().map((item) => (ids.includes(item.id) && item.readAt === null ? { ...item, readAt: now } : item))
    persist(next)
    return sorted(next)
  },
  async acknowledge(id, now) {
    const next = load().map((item) =>
      item.id === id ? { ...item, status: "acknowledged" as const, readAt: item.readAt ?? now, acknowledgedAt: now } : item
    )
    persist(next)
    return sorted(next)
  },
  async resolve(id, now) {
    const next = load().map((item) =>
      item.id === id ? { ...item, status: "resolved" as const, readAt: item.readAt ?? now, resolvedAt: now } : item
    )
    persist(next)
    return sorted(next)
  },
}

export async function getSystemNotices(): Promise<SystemNotice[]> {
  return []
}

export async function getNotificationSettings(): Promise<NotificationSettings> {
  return {
    channels: [
      { id: "in_app", name: "In-app", state: "configured", available: true, detail: "Notification centre in VENA" },
      { id: "email", name: "Email", state: "not_configured", available: true, detail: "Requires SMTP relay on the backend" },
      { id: "webhook", name: "Webhook", state: "disabled", available: false, detail: "Planned" },
      { id: "telegram", name: "Telegram", state: "disabled", available: false, detail: "Planned" },
      { id: "teams", name: "Microsoft Teams", state: "disabled", available: false, detail: "Planned" },
    ],
    recipients: [
      { id: "dispatch", name: "Dispatcher team", members: 6, emails: [] },
      { id: "maintenance", name: "Maintenance team", members: 11, emails: [] },
      { id: "management", name: "Management", members: 3, emails: [] },
    ],
    rules: [
      {
        id: "R-01",
        trigger: "critical_risk",
        severity: "critical",
        recipients: ["dispatch"],
        channels: ["in_app", "email"],
        cooldownHours: 4,
        enabled: true,
      },
      {
        id: "R-02",
        trigger: "risk_horizon_24h",
        severity: "warning",
        recipients: ["dispatch", "maintenance"],
        channels: ["in_app"],
        cooldownHours: 6,
        enabled: true,
      },
      {
        id: "R-03",
        trigger: "new_pattern",
        severity: "warning",
        recipients: ["dispatch"],
        channels: ["in_app"],
        cooldownHours: 2,
        enabled: true,
      },
      {
        id: "R-04",
        trigger: "action_overdue",
        severity: "warning",
        recipients: ["maintenance", "management"],
        channels: ["in_app", "email"],
        cooldownHours: 24,
        enabled: false,
      },
      {
        id: "R-05",
        trigger: "action_assigned",
        severity: "info",
        recipients: ["maintenance"],
        channels: ["in_app"],
        cooldownHours: 0,
        enabled: true,
      },
      {
        id: "R-06",
        trigger: "data_source_unavailable",
        severity: "critical",
        recipients: ["dispatch", "management"],
        channels: ["in_app", "email"],
        cooldownHours: 1,
        enabled: true,
      },
    ],
    digests: [
      {
        id: "D-01",
        name: "Morning brief",
        hour: 8,
        minute: 0,
        recipients: ["management", "dispatch"],
        sections: ["critical_risks", "new_patterns", "open_actions", "overdue_actions", "changes"],
        enabled: true,
      },
    ],
    email: { senderName: "VENA", senderAddress: "", state: "not_configured" },
  }
}
