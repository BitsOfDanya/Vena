"use client"

import { Plus } from "lucide-react"
import * as React from "react"

import type { InspectionPlan, InspectionPlanItem } from "@/entities/analytics"
import { useTodaysInspectionPlan } from "@/entities/analytics"
import { formatProbability } from "@/entities/prediction"
import { workflowMode } from "@/shared/config/env"
import { cn } from "@/shared/lib/utils"
import { LoadingBar } from "@/shared/ui/state-message"

const TABS = [
  { key: "pumps", label: "Насосы" },
  { key: "fans", label: "Вентиляторы" },
] as const

function PlanList({ plan, onCreate }: { plan: InspectionPlan | undefined; onCreate: (item: InspectionPlanItem) => void }) {
  if (!plan || plan.items.length === 0) {
    return <p className="px-4 py-6 text-[13px] text-muted-foreground">На сегодня осматривать нечего.</p>
  }
  return (
    <ol className="divide-y divide-border">
      {plan.items.map((item, index) => {
        const tone =
          item.riskLevel === "critical" ? "text-status-critical" : item.riskLevel === "attention" ? "text-status-attention" : "text-foreground"
        return (
          <li key={`${item.modelId}-${item.assetId}`} className="flex items-start gap-3 px-4 py-3">
            <span className="mt-0.5 w-4 shrink-0 text-[12px] text-faint tabular-nums">{index + 1}</span>
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline gap-2">
                <span className="truncate text-[14px] font-medium">{item.name?.trim() || item.assetId}</span>
                <span className={cn("ml-auto shrink-0 text-[13px] font-semibold tabular-nums", tone)}>
                  {formatProbability(item.probability)}
                </span>
              </div>
              {item.location ? <p className="truncate text-[12.5px] text-muted-foreground">{item.location}</p> : null}
              {item.reason ? <p className="mt-0.5 line-clamp-2 text-[12.5px] text-faint">{item.reason}</p> : null}
            </div>
            <button
              type="button"
              onClick={() => onCreate(item)}
              aria-label={`Создать работу: ${item.name?.trim() || item.assetId}`}
              title="Создать работу"
              className="mt-0.5 flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-md border border-border text-muted-foreground outline-none transition-colors hover:border-vena hover:text-vena focus-visible:ring-2 focus-visible:ring-ring/60"
            >
              <Plus className="size-4" aria-hidden />
            </button>
          </li>
        )
      })}
    </ol>
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
  const [tab, setTab] = React.useState<(typeof TABS)[number]["key"]>("pumps")
  if (workflowMode !== "api") return null
  const current = tab === "pumps" ? plan.data?.pumps : plan.data?.fans
  const skipped = current?.skippedRecent.length ?? 0

  return (
    <section aria-label="План осмотров на сегодня" className={cn("rounded-lg border border-border bg-elevated shadow-[var(--shadow-card)]", className)}>
      <div className="border-b border-border px-4 pt-3">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="text-[16px] font-semibold">План осмотров на сегодня</h2>
          <span className="text-[12px] text-faint">прогноз на 72 ч</span>
        </div>
        <p className="mt-0.5 text-[12.5px] text-muted-foreground">Агрегаты с наибольшим риском отказа. Кнопка «+» создаёт работу.</p>
        <div role="tablist" aria-label="Тип оборудования" className="mt-2 flex gap-4">
          {TABS.map((item) => {
            const count = (item.key === "pumps" ? plan.data?.pumps : plan.data?.fans)?.items.length ?? 0
            const selected = tab === item.key
            return (
              <button
                key={item.key}
                type="button"
                role="tab"
                aria-selected={selected}
                onClick={() => setTab(item.key)}
                className={cn(
                  "relative -mb-px cursor-pointer border-b-2 pb-2 text-[13.5px] outline-none focus-visible:ring-2 focus-visible:ring-ring/60",
                  selected ? "border-vena font-medium text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"
                )}
              >
                {item.label} <span className="text-faint tabular-nums">{count}</span>
              </button>
            )
          })}
        </div>
      </div>
      {plan.isPending ? (
        <LoadingBar className="min-h-20" />
      ) : plan.isError ? (
        <p className="px-4 py-6 text-[13px] text-muted-foreground">Не удалось загрузить план осмотров.</p>
      ) : (
        <>
          <PlanList plan={current} onCreate={onCreate} />
          {skipped > 0 ? (
            <p className="border-t border-border px-4 py-2 text-[12px] text-faint">
              Не повторяем: {skipped} с работой за последние сутки
            </p>
          ) : null}
        </>
      )}
    </section>
  )
}
