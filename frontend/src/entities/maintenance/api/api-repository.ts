import { apiFetch } from "@/shared/api/http"

import type { ActionRepository, ActionStatus, MaintenanceAction } from "../model/types"

type ApiActionEvent = {
  event_type: string
  actor: string
  at: string
  from_status: string | null
  to_status: string | null
  note: string
}

type ApiAction = {
  id: string
  asset_id: string
  source: "vena_forecast" | "manual" | "external_request"
  source_detail: string
  kind: string
  reason: string
  priority: MaintenanceAction["priority"]
  window_start: string
  recommended_at: string
  status: ActionStatus | "dismissed"
  assignee: string
  note: string
  notify_channels: string[]
  created_by: string
  created_at: string
  updated_at: string
  result_outcome: string | null
  result_note: string
  completed_at: string | null
  history: ApiActionEvent[]
}

const STATUS: Record<string, ActionStatus> = {
  suggested: "suggested",
  planned: "planned",
  assigned: "assigned",
  in_progress: "in_progress",
  waiting: "waiting",
  completed: "completed",
  cancelled: "cancelled",
  dismissed: "cancelled",
}

function toAction(item: ApiAction): MaintenanceAction {
  return {
    id: item.id,
    assetId: item.asset_id,
    priority: item.priority,
    kind: item.kind as MaintenanceAction["kind"],
    reason: item.reason,
    windowStart: Date.parse(item.window_start),
    recommendedAt: Date.parse(item.recommended_at),
    status: STATUS[item.status] ?? "planned",
    assignee: item.assignee,
    source: item.source === "external_request" ? "external" : item.source,
    sourceDetail: item.source_detail,
    note: item.note,
    createdBy: item.created_by,
    createdAt: Date.parse(item.created_at),
    notifyChannels: item.notify_channels.filter((channel): channel is "in_app" | "email" => channel === "in_app" || channel === "email"),
    history: item.history.map((event) => ({
      at: Date.parse(event.at),
      type: event.event_type as MaintenanceAction["history"][number]["type"],
      actor: event.actor,
      note: event.note,
    })),
    result:
      item.result_outcome === null
        ? null
        : {
            outcome: (item.result_outcome === "false_or_irrelevant_signal"
              ? "false_signal"
              : item.result_outcome) as NonNullable<MaintenanceAction["result"]>["outcome"],
            note: item.result_note,
            closedAt: item.completed_at ? Date.parse(item.completed_at) : Date.parse(item.updated_at),
          },
  }
}

async function list(): Promise<MaintenanceAction[]> {
  const items = await apiFetch<ApiAction[]>("/api/v1/actions")
  return items.map(toAction)
}

async function command(id: string, path: string, body?: Record<string, unknown>): Promise<MaintenanceAction> {
  const item = await apiFetch<ApiAction>(`/api/v1/actions/${id}/${path}`, {
    method: "POST",
    body: body ? JSON.stringify(body) : undefined,
  })
  return toAction(item)
}

const STATUS_COMMAND: Partial<Record<ActionStatus, string>> = {
  in_progress: "start",
  waiting: "wait",
  cancelled: "cancel",
}

export const apiActionRepository: ActionRepository = {
  list,
  async create(input) {
    const item = await apiFetch<ApiAction>("/api/v1/actions", {
      method: "POST",
      body: JSON.stringify({
        asset_id: input.assetId,
        kind: input.kind,
        reason: input.reason,
        priority: input.priority,
        recommended_at: new Date(input.recommendedAt).toISOString(),
        assignee: input.assignee,
        note: input.note,
        source: input.source === "external" ? "external_request" : (input.source ?? "manual"),
        source_detail: input.sourceDetail ?? "",
        notify_channels: input.notifyChannels ?? [],
        status: input.status === "suggested" ? "suggested" : "planned",
        source_prediction_id: input.sourcePredictionId ?? null,
        source_model_id: input.sourceModelId ?? null,
        source_prediction_time: input.sourcePredictionTime
          ? new Date(input.sourcePredictionTime).toISOString()
          : null,
        source_score: input.sourceScore ?? null,
        source_horizon_hours: input.sourceHorizonHours ?? null,
      }),
    })
    return toAction(item)
  },
  close: (input) =>
    command(input.id, "result", {
      outcome: input.outcome === "false_signal" ? "false_or_irrelevant_signal" : input.outcome,
      note: input.note,
    }),
  async setStatus(id, status) {
    if (status === "assigned") {
      const current = (await list()).find((action) => action.id === id)
      return command(id, "assign", { assignee: current?.assignee || "Дежурный инженер" })
    }
    const path = STATUS_COMMAND[status]
    if (!path) throw new Error(`Unsupported transition: ${status}`)
    return command(id, path)
  },
  approve: (id) => command(id, "approve"),
  dismiss: (input) => command(input.id, "dismiss", { reason: input.reason, note: input.note }),
}
