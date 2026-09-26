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
  dismiss(id: string, now: number): Promise<MaintenanceAction>
}

export const OUTCOME_LABEL: Record<ActionOutcome, string> = {
  confirmed_issue: "Confirmed issue",
  no_issue_found: "No issue found",
  maintenance_performed: "Maintenance performed",
  monitoring_required: "Monitoring required",
  false_signal: "False or irrelevant signal",
  other: "Other",
}

export const PRIORITY_LABEL: Record<ActionPriority, string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
}

export const STATUS_LABEL: Record<ActionStatus, string> = {
  suggested: "Suggested",
  planned: "Planned",
  assigned: "Assigned",
  in_progress: "In progress",
  waiting: "Waiting",
  completed: "Completed",
  cancelled: "Cancelled",
}

export const KIND_LABEL: Record<ActionKind, string> = {
  inspect: "Inspect",
  "electrical diagnostic": "Electrical diagnostic",
  service: "Service",
  verify: "Verify",
}

export const SOURCE_LABEL: Record<ActionSource, string> = {
  vena_forecast: "VENA forecast",
  manual: "Manual",
  external: "External request",
}

export const ACTION_EVENT_LABEL: Record<ActionEventType, string> = {
  suggested: "Suggested by VENA",
  created: "Created",
  approved: "Approved",
  planned: "Planned",
  assigned: "Assigned",
  started: "Started",
  waiting: "Waiting",
  completed: "Completed",
  cancelled: "Cancelled",
  dismissed: "Dismissed",
  notified: "Notification requested",
}

export const OPEN_STATUSES: ActionStatus[] = ["suggested", "planned", "assigned", "in_progress", "waiting"]

export const ASSIGNEES = ["Бригада А", "Бригада Б", "Электротехническая бригада", "Дежурный инженер"] as const
