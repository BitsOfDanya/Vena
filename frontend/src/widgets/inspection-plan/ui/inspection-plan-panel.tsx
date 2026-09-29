"use client"

import type { InspectionPlan, InspectionPlanItem } from "@/entities/analytics"
import { useTodaysInspectionPlan } from "@/entities/analytics"
import { formatProbability } from "@/entities/prediction"
import { workflowMode } from "@/shared/config/env"
import { Button } from "@/shared/ui/button"
import { LoadingBar } from "@/shared/ui/state-message"

function PlanColumn({
  title,
  plan,
  onCreate,
}: {
  title: string
  plan: InspectionPlan | undefined
  onCreate: (item: InspectionPlanItem) => void
}) {
  if (!plan) return null
  return (
    <div className="min-w-0">
      <h3 className="text-[11px] font-medium tracking-[0.1em] text-muted-foreground uppercase">
        {title}
        <span className="ml-2 font-mono text-[12px] text-faint tabular-nums">{plan.items.length}</span>
      </h3>
      {plan.skippedRecent.length > 0 ? (
        <p className="mt-1 text-[12px] text-muted-foreground">
          Пропущено с работой за сутки: {plan.skippedRecent.length}
        </p>
      ) : null}
      {plan.items.length === 0 ? (
        <p className="mt-2 text-[13px] text-muted-foreground">Нет каналов в плане.</p>
      ) : (
        <ul className="mt-2 space-y-2">
          {plan.items.map((item) => (
            <li
              key={`${item.modelId}-${item.assetId}`}
              className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border border-border-soft bg-background px-3 py-2"
            >
              <span className="min-w-0 flex-1 truncate text-[13px] font-medium">
                {item.name?.trim() || item.assetId}
              </span>
              <span className="font-mono text-[12px] tabular-nums text-muted-foreground">
                {formatProbability(item.probability)}
              </span>
              {item.riskLevel === "critical" || item.riskLevel === "attention" ? (
                <span className="text-[11px] tracking-[0.04em] text-faint">
                  {item.riskLevel === "critical" ? "критично" : "внимание"}
                </span>
              ) : null}
              {item.location ? (
                <span className="basis-full truncate text-[12px] text-muted-foreground">{item.location}</span>
              ) : null}
              {item.reason ? (
                <span className="basis-full truncate text-[12px] text-faint">{item.reason}</span>
              ) : null}
              <Button size="sm" variant="outline" className="mt-1" onClick={() => onCreate(item)}>
                Создать работу
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function InspectionPlanPanel({
  onCreate,
  className,
}: {
  onCreate: (item: InspectionPlanItem) => void
  className?: string
}) {
  const plan = useTodaysInspectionPlan()
  if (workflowMode !== "api") return null

  return (
    <section aria-label="План осмотров на сегодня" className={className}>
      <div className="mb-2 flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <h2 className="text-[13px] font-medium tracking-[0.1em] text-muted-foreground uppercase">
          План осмотров на сегодня
        </h2>
        <p className="text-[12px] text-muted-foreground">
          5 насосов и 5 вентиляторов с наибольшим риском · у вентиляторов каналы с работой за сутки пропускаются
        </p>
      </div>
      {plan.isPending ? (
        <LoadingBar className="min-h-20" />
      ) : plan.isError ? (
        <p className="text-[13px] text-muted-foreground">Не удалось загрузить план осмотров.</p>
      ) : (
        <div className="max-h-[min(36vh,22rem)] overflow-y-auto overscroll-contain border border-border bg-elevated p-4">
          <div className="grid gap-4 sm:grid-cols-2">
          <PlanColumn title="Насосы · 72 ч" plan={plan.data?.pumps} onCreate={onCreate} />
          <PlanColumn title="Вентиляторы · 72 ч" plan={plan.data?.fans} onCreate={onCreate} />
          </div>
        </div>
      )}
    </section>
  )
}
