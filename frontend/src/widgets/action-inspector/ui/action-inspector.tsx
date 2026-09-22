"use client"

import { useRouter } from "next/navigation"

import { StatusMark } from "@/entities/infrastructure"
import {
  ACTION_EVENT_LABEL,
  KIND_LABEL,
  OUTCOME_LABEL,
  PRIORITY_LABEL,
  SOURCE_LABEL,
  STATUS_LABEL,
  useApproveAction,
  useDismissAction,
  useSetActionStatus,
  type ActionStatus,
  type MaintenanceAction,
} from "@/entities/maintenance"
import { CloseActionForm } from "@/features/close-action"
import { useWorkspace } from "@/features/workspace"
import { formatClock, formatDateTime } from "@/shared/lib/time"
import { cn } from "@/shared/lib/utils"
import { Button } from "@/shared/ui/button"
import { Inspector, InspectorBody, InspectorFooter, InspectorHeader, InspectorSection } from "@/shared/ui/inspector"

const PRIORITY_MARK = { high: "critical", medium: "attention", low: "offline" } as const

const NEXT_STATUS: Partial<Record<ActionStatus, { status: ActionStatus; label: string }[]>> = {
  planned: [
    { status: "assigned", label: "Assign" },
    { status: "cancelled", label: "Cancel" },
  ],
  assigned: [
    { status: "in_progress", label: "Start work" },
    { status: "waiting", label: "Mark waiting" },
  ],
  in_progress: [{ status: "waiting", label: "Mark waiting" }],
  waiting: [{ status: "in_progress", label: "Resume" }],
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-[11px] font-medium tracking-[0.08em] text-faint uppercase">{label}</dt>
      <dd className="mt-0.5 text-[13px]">{children}</dd>
    </div>
  )
}

export function ActionInspector({ action, onClose }: { action: MaintenanceAction; onClose: () => void }) {
  const router = useRouter()
  const { now, selectAsset } = useWorkspace()
  const setStatus = useSetActionStatus(now)
  const approve = useApproveAction(now)
  const dismiss = useDismissAction(now)
  const transitions = NEXT_STATUS[action.status] ?? []

  return (
    <Inspector label="Action inspector">
      <InspectorHeader eyebrow={`Action · ${action.id}`} title={action.assetId} onClose={onClose}>
        <p className="mt-1 flex items-center gap-2 text-[13px] text-muted-foreground">
          <StatusMark status={PRIORITY_MARK[action.priority]} />
          {PRIORITY_LABEL[action.priority]} priority · {STATUS_LABEL[action.status]}
        </p>
      </InspectorHeader>
      <InspectorBody>
        <InspectorSection>
          <p className="text-[14px]">{action.reason}</p>
          <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3">
            <Field label="Action">{KIND_LABEL[action.kind]}</Field>
            <Field label="Assignee">{action.assignee}</Field>
            <Field label="Window from">
              <span className="font-mono text-[12px] tabular-nums">{formatDateTime(action.windowStart)}</span>
            </Field>
            <Field label="Recommended by">
              <span className="font-mono text-[12px] tabular-nums">{formatDateTime(action.recommendedAt)}</span>
            </Field>
            <Field label="Source">
              {SOURCE_LABEL[action.source]}
              {action.sourceDetail ? <span className="text-muted-foreground"> · {action.sourceDetail}</span> : null}
            </Field>
            <Field label="Created by">
              {action.createdBy}
              <span className="block font-mono text-[12px] text-muted-foreground tabular-nums">{formatDateTime(action.createdAt)}</span>
            </Field>
          </dl>
          {action.note ? <p className="mt-3 text-[13px] text-muted-foreground">{action.note}</p> : null}
          <p className="mt-3 text-[12px] text-faint">
            Notification channels: {action.notifyChannels.length > 0 ? action.notifyChannels.join(", ") : "none"}
          </p>
        </InspectorSection>

        {action.status === "suggested" ? (
          <InspectorSection title="Suggested action">
            <p className="text-[13px] text-muted-foreground">
              Предложено системой по прогнозу риска. Подтвердите, чтобы поставить в план, или отклоните.
            </p>
            <div className="mt-3 flex gap-2">
              <Button size="sm" disabled={approve.isPending} onClick={() => approve.mutate(action.id)}>
                Approve
              </Button>
              <Button variant="outline" size="sm" disabled={dismiss.isPending} onClick={() => dismiss.mutate(action.id)}>
                Dismiss
              </Button>
            </div>
          </InspectorSection>
        ) : null}

        {action.result ? (
          <InspectorSection title="Result">
            <p className="text-[14px] font-medium">{OUTCOME_LABEL[action.result.outcome]}</p>
            {action.result.note ? <p className="mt-1 text-[13px] text-muted-foreground">{action.result.note}</p> : null}
            <p className="mt-2 font-mono text-[12px] text-faint tabular-nums">Closed {formatDateTime(action.result.closedAt)}</p>
          </InspectorSection>
        ) : action.status !== "suggested" && action.status !== "cancelled" ? (
          <>
            {transitions.length > 0 ? (
              <InspectorSection title="Status">
                <div className="flex flex-wrap gap-2">
                  {transitions.map((item) => (
                    <Button
                      key={item.status}
                      variant="outline"
                      size="sm"
                      disabled={setStatus.isPending}
                      onClick={() => setStatus.mutate({ id: action.id, status: item.status })}
                    >
                      {item.label}
                    </Button>
                  ))}
                </div>
              </InspectorSection>
            ) : null}
            <InspectorSection title="Record result">
              <CloseActionForm actionId={action.id} onClosed={onClose} />
            </InspectorSection>
          </>
        ) : null}

        <InspectorSection title="Activity history">
          <ol className="space-y-1.5">
            {action.history.map((item, index) => (
              <li key={`${item.at}-${index}`} className="flex gap-3 text-[13px]">
                <span className="w-12 shrink-0 font-mono text-muted-foreground tabular-nums">{formatClock(item.at)}</span>
                <span className={cn(index === action.history.length - 1 && "font-medium")}>
                  {ACTION_EVENT_LABEL[item.type]}
                  <span className="text-muted-foreground"> · {item.actor}</span>
                  {item.note ? <span className="block text-[12px] text-muted-foreground">{item.note}</span> : null}
                </span>
              </li>
            ))}
          </ol>
        </InspectorSection>
      </InspectorBody>
      <InspectorFooter>
        <Button
          variant="outline"
          className="flex-1"
          onClick={() => {
            selectAsset(action.assetId)
            router.push("/timeline")
          }}
        >
          Open in Timeline
        </Button>
      </InspectorFooter>
    </Inspector>
  )
}
