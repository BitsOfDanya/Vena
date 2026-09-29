export type NotificationType = "risk" | "pattern" | "action" | "system" | "integration"
export type NotificationSeverity = "critical" | "warning" | "info"
export type NotificationStatus = "new" | "acknowledged" | "resolved"

export type Notification = {
  id: string
  type: NotificationType
  severity: NotificationSeverity
  title: string
  description: string
  assetId: string | null
  patternId: string | null
  createdAt: number
  status: NotificationStatus
  readAt: number | null
  acknowledgedAt: number | null
  resolvedAt: number | null
}

export type SystemNoticeKind = "data_delayed" | "api_unavailable" | "model_unavailable" | "integration_failure"

export type SystemNotice = {
  id: string
  kind: SystemNoticeKind
  severity: NotificationSeverity
  title: string
  description: string
  href: string | null
  dismissible: boolean
}

export type NotificationRepository = {
  list(): Promise<Notification[]>
  markRead(ids: string[], now: number): Promise<Notification[]>
  acknowledge(id: string, now: number): Promise<Notification[]>
  resolve(id: string, now: number): Promise<Notification[]>
}

export const NOTIFICATION_TYPE_LABEL: Record<NotificationType, string> = {
  risk: "Риск",
  pattern: "Паттерн",
  action: "Работа",
  system: "Система",
  integration: "Интеграция",
}

export const NOTIFICATION_STATUS_LABEL: Record<NotificationStatus, string> = {
  new: "Новое",
  acknowledged: "Принято",
  resolved: "Решено",
}

export type NotificationChannelId = "email" | "in_app" | "webhook" | "telegram" | "teams"
export type ChannelState = "configured" | "not_configured" | "disabled"

export type NotificationChannel = {
  id: NotificationChannelId
  name: string
  state: ChannelState
  available: boolean
  detail: string
}

export type RecipientGroup = {
  id: string
  name: string
  members: number
  emails: string[]
}

export type NotificationRuleTrigger =
  | "critical_risk"
  | "risk_horizon_24h"
  | "new_pattern"
  | "action_overdue"
  | "action_assigned"
  | "data_source_unavailable"

export type NotificationRule = {
  id: string
  trigger: NotificationRuleTrigger
  severity: NotificationSeverity
  recipients: string[]
  channels: NotificationChannelId[]
  cooldownHours: number
  enabled: boolean
}

export const RULE_TRIGGER_LABEL: Record<NotificationRuleTrigger, string> = {
  critical_risk: "Обнаружен критический риск",
  risk_horizon_24h: "Горизонт риска 24 ч или меньше",
  new_pattern: "Новый коррелированный паттерн",
  action_overdue: "Работа просрочена",
  action_assigned: "Работа назначена",
  data_source_unavailable: "Источник данных недоступен",
}

export type DigestSection = "critical_risks" | "new_patterns" | "open_actions" | "overdue_actions" | "changes"

export type DigestSchedule = {
  id: string
  name: string
  hour: number
  minute: number
  recipients: string[]
  sections: DigestSection[]
  enabled: boolean
}

export const DIGEST_SECTION_LABEL: Record<DigestSection, string> = {
  critical_risks: "Критические риски",
  new_patterns: "Новые паттерны",
  open_actions: "Открытые работы",
  overdue_actions: "Просроченные работы",
  changes: "Изменения с прошлого дайджеста",
}

export type EmailSettings = {
  senderName: string
  senderAddress: string
  state: ChannelState
}

export type NotificationSettings = {
  channels: NotificationChannel[]
  recipients: RecipientGroup[]
  rules: NotificationRule[]
  digests: DigestSchedule[]
  email: EmailSettings
}
