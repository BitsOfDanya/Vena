import { DEMO_NOW } from "@/entities/infrastructure"
import { HOUR, MINUTE } from "@/shared/lib/time"

import type {
  ActionEvent,
  ActionEventType,
  ActionRepository,
  ActionStatus,
  MaintenanceAction,
} from "../model/types"

const STORAGE_KEY = "vena.actions.v3"
const SYSTEM_ACTOR = "VENA"
const USER_ACTOR = "Дежурный инженер"

function event(at: number, type: ActionEventType, actor: string, note = ""): ActionEvent {
  return { at, type, actor, note }
}

function seed(): MaintenanceAction[] {
  return [
    {
      id: "A-1001",
      assetId: "P-0142",
      priority: "high",
      kind: "inspect",
      reason: "Высокая повторяемость, рост числа переходов",
      windowStart: DEMO_NOW,
      recommendedAt: DEMO_NOW + 24 * HOUR,
      status: "assigned",
      assignee: "Бригада А",
      source: "vena_forecast",
      sourceDetail: "Pump72",
      note: "",
      createdBy: USER_ACTOR,
      createdAt: DEMO_NOW - 2 * HOUR,
      notifyChannels: ["in_app"],
      history: [
        event(DEMO_NOW - 3 * HOUR, "suggested", SYSTEM_ACTOR, "Risk 68/100, horizon 72h"),
        event(DEMO_NOW - 2 * HOUR, "approved", USER_ACTOR),
        event(DEMO_NOW - 2 * HOUR, "planned", USER_ACTOR),
        event(DEMO_NOW - 100 * MINUTE, "assigned", USER_ACTOR, "Бригада А"),
      ],
      result: null,
    },
    {
      id: "A-1002",
      assetId: "PH-0871",
      priority: "medium",
      kind: "electrical diagnostic",
      reason: "Повторяющиеся изменения состояния питания",
      windowStart: DEMO_NOW + 8 * HOUR,
      recommendedAt: DEMO_NOW + 32 * HOUR,
      status: "planned",
      assignee: "Электротехническая бригада",
      source: "vena_forecast",
      sourceDetail: "Power24",
      note: "",
      createdBy: USER_ACTOR,
      createdAt: DEMO_NOW - 5 * HOUR,
      notifyChannels: [],
      history: [
        event(DEMO_NOW - 6 * HOUR, "suggested", SYSTEM_ACTOR, "Risk 58/100, horizon 24h"),
        event(DEMO_NOW - 5 * HOUR, "approved", USER_ACTOR),
        event(DEMO_NOW - 5 * HOUR, "planned", USER_ACTOR),
      ],
      result: null,
    },
    {
      id: "A-1003",
      assetId: "F-0312",
      priority: "medium",
      kind: "service",
      reason: "Частота событий выше базовой по каналу",
      windowStart: DEMO_NOW + 26 * HOUR,
      recommendedAt: DEMO_NOW + 60 * HOUR,
      status: "suggested",
      assignee: "Бригада Б",
      source: "vena_forecast",
      sourceDetail: "Fan72",
      note: "",
      createdBy: SYSTEM_ACTOR,
      createdAt: DEMO_NOW - 40 * MINUTE,
      notifyChannels: [],
      history: [event(DEMO_NOW - 40 * MINUTE, "suggested", SYSTEM_ACTOR, "Risk 49/100, horizon 72h")],
      result: null,
    },
    {
      id: "A-1004",
      assetId: "S-4412",
      priority: "low",
      kind: "verify",
      reason: "Единичная серия тревог, нужна проверка на месте",
      windowStart: DEMO_NOW + 48 * HOUR,
      recommendedAt: DEMO_NOW + 70 * HOUR,
      status: "suggested",
      assignee: "Дежурный инженер",
      source: "vena_forecast",
      sourceDetail: "Alarm corroboration",
      note: "",
      createdBy: SYSTEM_ACTOR,
      createdAt: DEMO_NOW - 90 * MINUTE,
      notifyChannels: [],
      history: [event(DEMO_NOW - 90 * MINUTE, "suggested", SYSTEM_ACTOR, "Alarm sequence without corroboration")],
      result: null,
    },
    {
      id: "A-0999",
      assetId: "K-2085",
      priority: "medium",
      kind: "inspect",
      reason: "Заявка участка: посторонний шум в камере",
      windowStart: DEMO_NOW + 4 * HOUR,
      recommendedAt: DEMO_NOW + 40 * HOUR,
      status: "waiting",
      assignee: "Бригада Б",
      source: "external",
      sourceDetail: "Заявка участка №412",
      note: "",
      createdBy: USER_ACTOR,
      createdAt: DEMO_NOW - 20 * HOUR,
      notifyChannels: [],
      history: [
        event(DEMO_NOW - 20 * HOUR, "created", USER_ACTOR, "Заявка участка №412"),
        event(DEMO_NOW - 19 * HOUR, "assigned", USER_ACTOR, "Бригада Б"),
        event(DEMO_NOW - 3 * HOUR, "waiting", "Бригада Б", "Ожидание доступа в камеру"),
      ],
      result: null,
    },
    {
      id: "A-0997",
      assetId: "P-0142",
      priority: "high",
      kind: "service",
      reason: "Отказ после окна эскалации",
      windowStart: DEMO_NOW - 96 * HOUR,
      recommendedAt: DEMO_NOW - 90 * HOUR,
      status: "completed",
      assignee: "Бригада А",
      source: "vena_forecast",
      sourceDetail: "Pump72",
      note: "",
      createdBy: USER_ACTOR,
      createdAt: DEMO_NOW - 100 * HOUR,
      notifyChannels: [],
      history: [
        event(DEMO_NOW - 100 * HOUR, "suggested", SYSTEM_ACTOR),
        event(DEMO_NOW - 99 * HOUR, "approved", USER_ACTOR),
        event(DEMO_NOW - 98 * HOUR, "assigned", USER_ACTOR, "Бригада А"),
        event(DEMO_NOW - 94 * HOUR, "started", "Бригада А"),
        event(DEMO_NOW - 91 * HOUR, "completed", "Бригада А", "Заменён контактор"),
      ],
      result: { outcome: "maintenance_performed", note: "Заменён контактор", closedAt: DEMO_NOW - 91 * HOUR },
    },
  ]
}

let store: MaintenanceAction[] | null = null

function load(): MaintenanceAction[] {
  if (store) return store
  if (typeof window !== "undefined") {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY)
      if (raw) {
        store = JSON.parse(raw) as MaintenanceAction[]
        return store
      }
    } catch {
      store = null
    }
  }
  store = seed()
  return store
}

function persist(next: MaintenanceAction[]) {
  store = next
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    } catch {
      return
    }
  }
}

function nextId(list: MaintenanceAction[]) {
  const numbers = list.map((action) => Number(action.id.replace("A-", ""))).filter((value) => Number.isFinite(value))
  return `A-${Math.max(1100, ...numbers) + 1}`
}

const STATUS_EVENT: Record<ActionStatus, ActionEventType> = {
  suggested: "suggested",
  planned: "planned",
  assigned: "assigned",
  in_progress: "started",
  waiting: "waiting",
  completed: "completed",
  cancelled: "cancelled",
}

function update(id: string, patch: (action: MaintenanceAction) => MaintenanceAction) {
  const list = load()
  const current = list.find((action) => action.id === id)
  if (!current) throw new Error("Action not found")
  const updated = patch(current)
  persist(list.map((action) => (action.id === id ? updated : action)))
  return updated
}

export const actionRepository: ActionRepository = {
  async list() {
    return [...load()].sort((left, right) => left.recommendedAt - right.recommendedAt)
  },
  async create(input, now) {
    const list = load()
    const status: ActionStatus = input.status ?? "planned"
    const channels = input.notifyChannels ?? []
    const history: ActionEvent[] = [event(now, "created", USER_ACTOR, input.sourceDetail ?? "")]
    if (status === "planned") history.push(event(now, "planned", USER_ACTOR))
    if (channels.length > 0) history.push(event(now, "notified", USER_ACTOR, `${channels.join(", ")} → ${input.assignee}`))
    const action: MaintenanceAction = {
      id: nextId(list),
      assetId: input.assetId,
      priority: input.priority,
      kind: input.kind,
      reason: input.reason,
      windowStart: now,
      recommendedAt: input.recommendedAt,
      status,
      assignee: input.assignee,
      source: input.source ?? "manual",
      sourceDetail: input.sourceDetail ?? "Диспетчер",
      note: input.note,
      createdBy: USER_ACTOR,
      createdAt: now,
      notifyChannels: channels,
      history,
      result: null,
    }
    persist([...list, action])
    return action
  },
  async close(input, now) {
    return update(input.id, (action) => ({
      ...action,
      status: "completed",
      result: { outcome: input.outcome, note: input.note, closedAt: now },
      history: [...action.history, event(now, "completed", USER_ACTOR, input.note)],
    }))
  },
  async setStatus(id, status, now, actor = USER_ACTOR) {
    return update(id, (action) => ({
      ...action,
      status,
      history: [...action.history, event(now, STATUS_EVENT[status], actor)],
    }))
  },
  async approve(id, now) {
    return update(id, (action) => ({
      ...action,
      status: "planned",
      history: [...action.history, event(now, "approved", USER_ACTOR), event(now, "planned", USER_ACTOR)],
    }))
  },
  async dismiss(id, now) {
    return update(id, (action) => ({
      ...action,
      status: "cancelled",
      history: [...action.history, event(now, "dismissed", USER_ACTOR)],
    }))
  },
}
