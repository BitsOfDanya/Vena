import { z } from "zod"

import { apiFetch } from "@/shared/api/http"

const ReplayStatusSchema = z.enum(["idle", "preparing", "running", "stopping", "finished", "failed"])

const ReplayStateSchema = z.object({
  state: ReplayStatusSchema,
  mode: z.enum(["week", "scenario"]).nullable(),
  active: z.boolean(),
  live: z.boolean(),
  start: z.string().nullable(),
  end: z.string().nullable(),
  clock: z.string().nullable(),
  speed: z.number().nullable(),
  sent_events: z.number(),
  batches: z.number(),
  started_at: z.string().nullable(),
  finished_at: z.string().nullable(),
  detail: z.string(),
  simulate_dispatcher: z.boolean(),
  simulation: z.object({ confirmed: z.number(), dismissed: z.number(), left: z.number() }),
  scenario: z
    .object({
      id: z.string(),
      kind: z.string(),
      label: z.string(),
      object: z.string(),
      stage: z.string().nullable(),
      stage_index: z.number(),
      stages: z.number(),
      shift_days: z.number(),
      replay_date: z.string().nullable(),
    })
    .nullable(),
  ml_history_end: z.string().nullable(),
  ml_clock: z.string().nullable(),
  journal_from: z.string().nullable(),
  journal_to: z.string().nullable(),
})

const ScenarioItemSchema = z.object({
  id: z.string(),
  kind: z.string(),
  label: z.string(),
  object: z.string(),
  start: z.string(),
  end: z.string(),
  channels: z.number(),
  rule: z.string(),
  before_hours: z.number(),
  after_hours: z.number(),
  lead: z.array(z.object({ hours_before: z.number(), place: z.number(), objects_ranked: z.number() })),
})

const ScenarioCatalogSchema = z.object({
  generated_at: z.string().nullable(),
  note: z.string(),
  items: z.array(ScenarioItemSchema),
})

export type ReplayStatus = z.infer<typeof ReplayStatusSchema>
export type ReplayState = z.infer<typeof ReplayStateSchema>
export type ScenarioItem = z.infer<typeof ScenarioItemSchema>
export type ScenarioCatalog = z.infer<typeof ScenarioCatalogSchema>

export type WeekReplayInput = { start: string; end: string; speed: number; simulateDispatcher: boolean }

export async function getReplayState(): Promise<ReplayState> {
  return ReplayStateSchema.parse(await apiFetch<unknown>("/api/v1/replay"))
}

export async function getReplayScenarios(): Promise<ScenarioCatalog> {
  return ScenarioCatalogSchema.parse(await apiFetch<unknown>("/api/v1/replay/scenarios"))
}

export async function startWeekReplay(input: WeekReplayInput): Promise<ReplayState> {
  const body = { start: input.start, end: input.end, speed: input.speed, simulate_dispatcher: input.simulateDispatcher }
  return ReplayStateSchema.parse(await apiFetch<unknown>("/api/v1/replay/week", { method: "POST", body: JSON.stringify(body) }))
}

export async function startScenarioReplay(id: string): Promise<ReplayState> {
  return ReplayStateSchema.parse(await apiFetch<unknown>("/api/v1/replay/scenario", { method: "POST", body: JSON.stringify({ id }) }))
}

export async function stopReplay(returnLive: boolean): Promise<ReplayState> {
  return ReplayStateSchema.parse(
    await apiFetch<unknown>("/api/v1/replay/stop", { method: "POST", body: JSON.stringify({ return_live: returnLive }) })
  )
}
