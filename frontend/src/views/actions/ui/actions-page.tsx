"use client"

import { Plus } from "lucide-react"
import * as React from "react"

import { StatusMark } from "@/entities/infrastructure"
import {
  KIND_LABEL,
  OPEN_STATUSES,
  OUTCOME_LABEL,
  SOURCE_LABEL,
  STATUS_LABEL,
  useActions,
  useApproveAction,
  useDismissAction,
} from "@/entities/maintenance"
import { CreateActionSheet } from "@/features/create-action"
import { useWorkspace } from "@/features/workspace"
import { HOUR, formatAgo, formatDateTime } from "@/shared/lib/time"
import { Button } from "@/shared/ui/button"
import { Segmented } from "@/shared/ui/segmented"
import { LoadingBar, StateMessage } from "@/shared/ui/state-message"
import { ActionInspector } from "@/widgets/action-inspector"
import { MaintenanceTimeline } from "@/widgets/maintenance-timeline"

const HORIZONS = [
  { value: 24, label: "24h" },
  { value: 48, label: "48h" },
  { value: 72, label: "72h" },
]

function SectionTitle({ children, count }: { children: React.ReactNode; count?: number }) {
  return (
    <h2 className="flex items-baseline gap-2.5 text-[13px] font-medium tracking-[0.1em] text-muted-foreground uppercase">
      {children}
      {count !== undefined ? <span className="font-mono text-[12px] text-faint tabular-nums">{count}</span> : null}
    </h2>
  )
}

export function ActionsPage() {
  const { now } = useWorkspace()
  const actions = useActions()
  const approve = useApproveAction(now)
  const dismiss = useDismissAction(now)
  const [hours, setHours] = React.useState(72)
  const [selectedId, setSelectedId] = React.useState<string | null>(null)
  const [sheetOpen, setSheetOpen] = React.useState(false)

  const list = React.useMemo(() => actions.data ?? [], [actions.data])
  const suggested = list.filter((action) => action.status === "suggested")
  const scheduled = list.filter((action) => OPEN_STATUSES.includes(action.status) && action.status !== "suggested")
  const planned = scheduled.filter((action) => action.recommendedAt - now <= hours * HOUR)
  const finished = list
    .filter((action) => action.status === "completed" || action.status === "cancelled")
    .sort((left, right) => (right.result?.closedAt ?? right.createdAt) - (left.result?.closedAt ?? left.createdAt))
  const selected = list.find((action) => action.id === selectedId) ?? null
  const count = (status: string) => scheduled.filter((action) => action.status === status).length

  return (
    <div className="flex size-full min-h-0 flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-x-8 gap-y-3 px-6 pt-4 pb-4">
        <h1 className="flex items-baseline gap-3">
          <span className="text-[26px] font-semibold tracking-[-0.01em]">Action Plan</span>
          <span className="font-mono text-[13px] text-faint">next {hours}h</span>
        </h1>
        <p className="flex items-center gap-6 text-[13px] text-muted-foreground">
          <span>
            Suggested <span className="ml-1 font-mono text-[15px] text-foreground tabular-nums">{String(suggested.length).padStart(2, "0")}</span>
          </span>
          <span>
            Planned <span className="ml-1 font-mono text-[15px] text-foreground tabular-nums">{String(count("planned")).padStart(2, "0")}</span>
          </span>
          <span>
            Assigned <span className="ml-1 font-mono text-[15px] text-foreground tabular-nums">{String(count("assigned")).padStart(2, "0")}</span>
          </span>
          <span>
            In progress{" "}
            <span className="ml-1 font-mono text-[15px] text-foreground tabular-nums">{String(count("in_progress")).padStart(2, "0")}</span>
          </span>
        </p>
        <div className="ml-auto flex items-center gap-2.5">
          <Segmented label="Planning horizon" value={hours} onChange={setHours} options={HORIZONS} />
          <Button size="sm" onClick={() => setSheetOpen(true)}>
            <Plus data-icon="inline-start" /> New action
          </Button>
        </div>
      </div>

      <div className="flex min-h-0 flex-1">
        <div className="min-w-0 flex-1 overflow-auto">
          {actions.isPending ? (
            <LoadingBar />
          ) : actions.isError ? (
            <StateMessage
              title="Actions unavailable"
              description="Не удалось загрузить план обслуживания."
              action={
                <Button variant="outline" size="sm" onClick={() => actions.refetch()}>
                  Retry
                </Button>
              }
            />
          ) : (
            <>
              {suggested.length > 0 ? (
                <section aria-label="Suggested actions" className="px-6 pb-5">
                  <SectionTitle count={suggested.length}>Suggested by VENA</SectionTitle>
                  <ul className="mt-2 border border-border bg-elevated">
                    {suggested.map((action) => (
                      <li key={action.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-border-soft px-5 py-3 last:border-b-0">
                        <StatusMark status={action.priority === "high" ? "critical" : "attention"} className="size-3" />
                        <span className="font-mono text-[14px]">{action.assetId}</span>
                        <span className="text-[13px] text-muted-foreground">
                          {KIND_LABEL[action.kind]} · {action.reason}
                        </span>
                        <span className="font-mono text-[12px] text-faint tabular-nums">{formatAgo(action.createdAt, now)}</span>
                        <span className="ml-auto flex items-center gap-3">
                          <button
                            type="button"
                            onClick={() => setSelectedId(action.id)}
                            className="text-[13px] text-muted-foreground underline-offset-4 outline-none hover:text-foreground hover:underline focus-visible:ring-2 focus-visible:ring-ring/60"
                          >
                            Review
                          </button>
                          <button
                            type="button"
                            disabled={dismiss.isPending}
                            onClick={() => dismiss.mutate(action.id)}
                            className="text-[13px] text-muted-foreground underline-offset-4 outline-none hover:text-foreground hover:underline focus-visible:ring-2 focus-visible:ring-ring/60"
                          >
                            Dismiss
                          </button>
                          <Button size="sm" disabled={approve.isPending} onClick={() => approve.mutate(action.id)}>
                            Approve
                          </Button>
                        </span>
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null}

              <section aria-label="Intervention plan" className="px-6">
                <SectionTitle count={planned.length}>Intervention plan</SectionTitle>
                <div className="mt-2 border border-border bg-elevated">
                  <MaintenanceTimeline
                    actions={planned}
                    now={now}
                    horizonHours={hours}
                    selectedId={selectedId}
                    onSelect={setSelectedId}
                  />
                </div>
              </section>

              <section aria-label="Closed actions" className="mt-6 px-6 pb-8">
                <SectionTitle count={finished.length}>Recently closed</SectionTitle>
                {finished.length === 0 ? (
                  <p className="mt-2 text-[13px] text-muted-foreground">Закрытых работ пока нет.</p>
                ) : (
                  <ul className="mt-2 border-t border-border-soft">
                    {finished.map((action) => (
                      <li key={action.id} className="border-b border-border-soft">
                        <button
                          type="button"
                          onClick={() => setSelectedId(action.id)}
                          className="grid w-full grid-cols-[5rem_6rem_1fr_9rem_10rem] items-center gap-4 py-2 text-left text-[13px] outline-none hover:bg-elevated focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/60"
                        >
                          <span className="font-mono text-muted-foreground">{action.id}</span>
                          <span className="font-mono">{action.assetId}</span>
                          <span className="truncate text-muted-foreground">{action.reason}</span>
                          <span className="text-muted-foreground">{SOURCE_LABEL[action.source]}</span>
                          <span className="text-right whitespace-nowrap">
                            {action.result ? OUTCOME_LABEL[action.result.outcome] : STATUS_LABEL[action.status]}
                            <span className="ml-2 font-mono text-[12px] text-faint tabular-nums">
                              {action.result ? formatDateTime(action.result.closedAt) : ""}
                            </span>
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </>
          )}
        </div>
        {selected ? <ActionInspector key={selected.id} action={selected} onClose={() => setSelectedId(null)} /> : null}
      </div>
      <CreateActionSheet open={sheetOpen} onOpenChange={setSheetOpen} draft={{}} />
    </div>
  )
}
