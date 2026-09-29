"use client"

import { Plus } from "lucide-react"
import * as React from "react"

import { StatusMark } from "@/entities/infrastructure"
import type { InspectionPlanItem } from "@/entities/analytics"
import {
  KIND_LABEL,
  OPEN_STATUSES,
  OUTCOME_LABEL,
  SOURCE_LABEL,
  STATUS_LABEL,
  useActions,
  useApproveAction,
  useSetActionStatus,
} from "@/entities/maintenance"
import { CreateActionSheet, type ActionDraft } from "@/features/create-action"
import { DismissActionDialog } from "@/features/dismiss-action"
import { useWorkspace } from "@/features/workspace"
import { useIsMobile } from "@/shared/lib/hooks/use-mobile"
import { HOUR, formatAgo, formatDateTime } from "@/shared/lib/time"
import { Button } from "@/shared/ui/button"
import { Segmented } from "@/shared/ui/segmented"
import { LoadingBar, StateMessage } from "@/shared/ui/state-message"
import { ActionInspector } from "@/widgets/action-inspector"
import { InspectionPlanPanel } from "@/widgets/inspection-plan"
import { MaintenanceTimeline } from "@/widgets/maintenance-timeline"

const HORIZONS = [
  { value: 24, label: "24ч" },
  { value: 48, label: "48ч" },
  { value: 72, label: "72ч" },
]

function SectionTitle({ children, count }: { children: React.ReactNode; count?: number }) {
  return (
    <h2 className="text-[15px] font-semibold text-foreground flex items-baseline gap-2.5">
      {children}
      {count !== undefined ? <span className="font-mono text-[12px] text-faint tabular-nums">{count}</span> : null}
    </h2>
  )
}

export function ActionsPage() {
  const { now } = useWorkspace()
  const isMobile = useIsMobile()
  const actions = useActions()
  const approve = useApproveAction(now)
  const setStatus = useSetActionStatus(now)
  const [hours, setHours] = React.useState(72)
  const [selectedId, setSelectedId] = React.useState<string | null>(null)
  const [sheetOpen, setSheetOpen] = React.useState(false)
  const [draft, setDraft] = React.useState<ActionDraft>({})

  const list = React.useMemo(() => actions.data ?? [], [actions.data])
  const suggested = list.filter((action) => action.status === "suggested")
  const scheduled = list.filter((action) => OPEN_STATUSES.includes(action.status) && action.status !== "suggested")
  const planned = scheduled.filter((action) => action.recommendedAt - now <= hours * HOUR)
  const finished = list
    .filter((action) => action.status === "completed" || action.status === "cancelled")
    .sort((left, right) => (right.result?.closedAt ?? right.createdAt) - (left.result?.closedAt ?? left.createdAt))
  const selected = list.find((action) => action.id === selectedId) ?? null
  const count = (status: string) => scheduled.filter((action) => action.status === status).length
  const brigadeQueue = [...suggested, ...planned].slice(0, 40)

  function createFromInspection(item: InspectionPlanItem) {
    setDraft({
      assetId: item.assetId,
      reason: item.reason
        ? `Осмотр · ${item.reason}`
        : `План осмотра · ${item.name?.trim() || item.assetId}`,
      priority: item.riskLevel === "critical" || item.riskLevel === "attention" ? "high" : "medium",
      kind: "inspect",
      sourcePredictionId: item.predictionId,
      sourceModelId: item.modelId,
      sourceScore: item.probability,
      sourceHorizonHours: item.modelId.includes("72") ? 72 : 24,
    })
    setSheetOpen(true)
  }

  if (isMobile) {
    return (
      <div className="flex size-full min-h-0 flex-col overflow-auto">
        <div className="shrink-0 space-y-2 px-4 pt-4 pb-3">
          <h1 className="text-[22px] font-semibold tracking-[-0.01em]">Работы бригады</h1>
          <p className="text-[13px] text-muted-foreground">Что сделать · где · отметить результат на месте</p>
          <Segmented label="Горизонт" value={hours} onChange={setHours} options={HORIZONS} />
        </div>
        <InspectionPlanPanel className="px-4 pb-3" onCreate={createFromInspection} />
        {actions.isPending ? (
          <LoadingBar />
        ) : actions.isError ? (
          <StateMessage title="Работы недоступны" description="Не удалось загрузить план." />
        ) : selected ? (
          <div className="px-4 pb-8">
            <ActionInspector
              key={selected.id}
              action={selected}
              onClose={() => setSelectedId(null)}
              className="static inset-auto h-auto w-full max-w-none border border-border"
            />
          </div>
        ) : brigadeQueue.length === 0 ? (
          <StateMessage title="Очередь пуста" description="Нет предложенных или запланированных работ в выбранном окне." />
        ) : (
          <ul className="space-y-3 px-4 pb-8">
            {brigadeQueue.map((action) => (
              <li key={action.id} className="border border-border bg-elevated px-4 py-3">
                <div className="flex items-baseline gap-2">
                  <StatusMark status={action.priority === "high" ? "critical" : "attention"} className="size-3" />
                  <span className="font-mono text-[14px]">{action.assetId}</span>
                  <span className="text-[12px] text-faint">{STATUS_LABEL[action.status]}</span>
                </div>
                <p className="mt-2 text-[14px]">{action.reason}</p>
                <p className="mt-1 text-[12px] text-muted-foreground">
                  {KIND_LABEL[action.kind]} · к {formatDateTime(action.recommendedAt)}
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button size="sm" variant="outline" onClick={() => setSelectedId(action.id)}>
                    Открыть
                  </Button>
                  {action.status === "suggested" ? (
                    <Button size="sm" disabled={approve.isPending} onClick={() => approve.mutate(action.id)}>
                      Принять
                    </Button>
                  ) : null}
                  {action.status === "assigned" ? (
                    <Button
                      size="sm"
                      disabled={setStatus.isPending}
                      onClick={() => setStatus.mutate({ id: action.id, status: "in_progress" })}
                    >
                      Начать
                    </Button>
                  ) : null}
                  {action.status === "planned" ? (
                    <Button
                      size="sm"
                      disabled={setStatus.isPending}
                      onClick={() => setStatus.mutate({ id: action.id, status: "assigned" })}
                    >
                      Назначить
                    </Button>
                  ) : null}
                  {action.status === "in_progress" || action.status === "waiting" ? (
                    <Button size="sm" onClick={() => setSelectedId(action.id)}>
                      Закрыть с результатом
                    </Button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        )}
        <CreateActionSheet open={sheetOpen} onOpenChange={setSheetOpen} draft={draft} />
      </div>
    )
  }

  return (
    <div className="flex size-full min-h-0 flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-x-8 gap-y-3 px-6 pt-4 pb-4">
        <h1 className="flex items-baseline gap-3">
          <span className="text-[26px] font-semibold tracking-[-0.01em]">План работ</span>
          <span className="font-mono text-[13px] text-faint">след. {hours}ч</span>
        </h1>
        <p className="flex items-center gap-6 text-[13px] text-muted-foreground">
          <span>
            Предложено <span className="ml-1 font-mono text-[15px] text-foreground tabular-nums">{String(suggested.length).padStart(2, "0")}</span>
          </span>
          <span>
            В плане <span className="ml-1 font-mono text-[15px] text-foreground tabular-nums">{String(count("planned")).padStart(2, "0")}</span>
          </span>
          <span>
            Назначено <span className="ml-1 font-mono text-[15px] text-foreground tabular-nums">{String(count("assigned")).padStart(2, "0")}</span>
          </span>
          <span>
            В работе{" "}
            <span className="ml-1 font-mono text-[15px] text-foreground tabular-nums">{String(count("in_progress")).padStart(2, "0")}</span>
          </span>
        </p>
        <div className="ml-auto flex items-center gap-2.5">
          <Segmented label="Горизонт планирования" value={hours} onChange={setHours} options={HORIZONS} />
          <Button
            size="sm"
            onClick={() => {
              setDraft({})
              setSheetOpen(true)
            }}
          >
            <Plus data-icon="inline-start" /> Создать работу
          </Button>
        </div>
      </div>

      <div className="flex min-h-0 flex-1">
        <div className="min-w-0 flex-1 overflow-auto">
          <InspectionPlanPanel className="px-6 pb-4" onCreate={createFromInspection} />
          {actions.isPending ? (
            <LoadingBar />
          ) : actions.isError ? (
            <StateMessage
              title="Работы недоступны"
              description="Не удалось загрузить план обслуживания."
              action={
                <Button variant="outline" size="sm" onClick={() => actions.refetch()}>
                  Повторить
                </Button>
              }
            />
          ) : (
            <>
              {suggested.length > 0 ? (
                <section aria-label="Предложенные работы" className="px-6 pb-5">
                  <SectionTitle count={suggested.length}>Предложено VENA</SectionTitle>
                  <ul className="mt-2 border border-border bg-elevated">
                    {suggested.map((action) => (
                      <li key={action.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-border-soft px-5 py-3 last:border-b-0">
                        <StatusMark status={action.priority === "high" ? "critical" : "attention"} className="size-3" />
                        <span className="font-mono text-[14px]">{action.assetId}</span>
                        <span className="text-[13px] text-muted-foreground">
                          {KIND_LABEL[action.kind]} · {action.reason}
                        </span>
                        <span className="font-mono text-[12px] text-faint tabular-nums">{action.createdAt > now ? formatDateTime(action.createdAt) : formatAgo(action.createdAt, now)}</span>
                        <span className="ml-auto flex items-center gap-3">
                          <button
                            type="button"
                            onClick={() => setSelectedId(action.id)}
                            className="text-[13px] text-muted-foreground underline-offset-4 outline-none hover:text-foreground hover:underline focus-visible:ring-2 focus-visible:ring-ring/60"
                          >
                            Открыть
                          </button>
                          <DismissActionDialog
                            actionId={action.id}
                            trigger={
                              <button
                                type="button"
                                className="text-[13px] text-muted-foreground underline-offset-4 outline-none hover:text-foreground hover:underline focus-visible:ring-2 focus-visible:ring-ring/60"
                              >
                                Отклонить
                              </button>
                            }
                          />
                          <Button size="sm" disabled={approve.isPending} onClick={() => approve.mutate(action.id)}>
                            Утвердить
                          </Button>
                        </span>
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null}

              <section aria-label="План вмешательств" className="px-6">
                <SectionTitle count={planned.length}>План вмешательств</SectionTitle>
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

              <section aria-label="Закрытые работы" className="mt-6 px-6 pb-8">
                <SectionTitle count={finished.length}>Недавно закрытые</SectionTitle>
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
      <CreateActionSheet open={sheetOpen} onOpenChange={setSheetOpen} draft={draft} />
    </div>
  )
}
