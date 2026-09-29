export type ActionPriority = "high" | "medium" | "low"
export type ActionStatus = "suggested" | "planned" | "assigned" | "in_progress" | "waiting" | "completed" | "cancelled"
export type ActionKind = "inspect" | "electrical diagnostic" | "service" | "verify"
export type ActionSource = "vena_forecast" | "manual" | "external"
export type ActionChannel = "in_app" | "email"

export type ActionOutcome =
  | "confirmed_issue"
  | "no_issue_found"
  | "maintenance_performed"
  | "monitoring_required"
  | "false_signal"
  | "other"

export type ActionResult = {
  outcome: ActionOutcome
  note: string
  closedAt: number
}

export type ActionEventType =
  | "suggested"
  | "created"
  | "approved"
  | "planned"
  | "assigned"
  | "started"
  | "waiting"
  | "completed"
  | "cancelled"
  | "dismissed"
  | "notified"

export type ActionEvent = {
  at: number
  type: ActionEventType
  actor: string
  note: string
}

export type MaintenanceAction = {
  id: string
  assetId: string
  priority: ActionPriority
  kind: ActionKind
  reason: string
  windowStart: number
  recommendedAt: number
  status: ActionStatus
  assignee: string
  source: ActionSource
  sourceDetail: string
  note: string
  createdBy: string
  createdAt: number
  notifyChannels: ActionChannel[]
  history: ActionEvent[]
  result: ActionResult | null
}

export type CreateActionInput = {
  assetId: string
  kind: ActionKind
  reason: string
  priority: ActionPriority
  recommendedAt: number
  assignee: string
  note: string
  source?: ActionSource
  sourceDetail?: string
  notifyChannels?: ActionChannel[]
  status?: ActionStatus
  sourcePredictionId?: string | null
  sourceModelId?: string | null
  sourcePredictionTime?: number | null
  sourceScore?: number | null
  sourceHorizonHours?: number | null
}

export type CloseActionInput = {
  id: string
  outcome: ActionOutcome
  note: string
}

export type ActionRepository = {
  list(): Promise<MaintenanceAction[]>
  create(input: CreateActionInput, now: number): Promise<MaintenanceAction>
  close(input: CloseActionInput, now: number): Promise<MaintenanceAction>
  setStatus(id: string, status: ActionStatus, now: number, actor?: string): Promise<MaintenanceAction>
  approve(id: string, now: number): Promise<MaintenanceAction>
  dismiss(input: DismissActionInput, now: number): Promise<MaintenanceAction>
}

export type DismissReason = "false_alarm" | "planned_works" | "verified_normal" | "monitoring" | "duplicate" | "other"

export type DismissActionInput = { id: string; reason: DismissReason; note: string }

export const DISMISS_REASON_LABEL: Record<DismissReason, string> = {
  false_alarm: "Ложное срабатывание",
  planned_works: "Плановые работы на объекте",
  verified_normal: "Проверено по камерам и телеметрии: норма",
  monitoring: "Мониторинг ситуации без выезда",
  duplicate: "Дубль уже открытой работы",
  other: "Другое",
}

export const DISMISS_REASON_OUTCOME: Record<DismissReason, ActionOutcome> = {
  false_alarm: "false_signal",
  planned_works: "false_signal",
  verified_normal: "no_issue_found",
  monitoring: "monitoring_required",
  duplicate: "other",
  other: "other",
}

export const OUTCOME_LABEL: Record<ActionOutcome, string> = {
  confirmed_issue: "Инцидент подтверждён",
  no_issue_found: "Норма, замечаний нет",
  maintenance_performed: "Обслуживание выполнено",
  monitoring_required: "Требуется мониторинг",
  false_signal: "Ложный или нерелевантный сигнал",
  other: "Другое",
}

export const PRIORITY_LABEL: Record<ActionPriority, string> = {
  high: "Высокий",
  medium: "Средний",
  low: "Низкий",
}

export const STATUS_LABEL: Record<ActionStatus, string> = {
  suggested: "Предложено",
  planned: "В плане",
  assigned: "Назначено",
  in_progress: "В работе",
  waiting: "Ожидание",
  completed: "Завершено",
  cancelled: "Отменено",
}

export const KIND_LABEL: Record<ActionKind, string> = {
  inspect: "Осмотр",
  "electrical diagnostic": "Электродиагностика",
  service: "Обслуживание",
  verify: "Проверка",
}

export const SOURCE_LABEL: Record<ActionSource, string> = {
  vena_forecast: "Прогноз VENA",
  manual: "Вручную",
  external: "Внешний запрос",
}

export const ACTION_EVENT_LABEL: Record<ActionEventType, string> = {
  suggested: "Предложено VENA",
  created: "Создано",
  approved: "Утверждено",
  planned: "В плане",
  assigned: "Назначено",
  started: "Начато",
  waiting: "Ожидание",
  completed: "Завершено",
  cancelled: "Отменено",
  dismissed: "Отклонено",
  notified: "Уведомление запрошено",
}

export const OPEN_STATUSES: ActionStatus[] = ["suggested", "planned", "assigned", "in_progress", "waiting"]

export const ASSIGNEES = ["Бригада А", "Бригада Б", "Электротехническая бригада", "Дежурный инженер"] as const
