"use client"

import { BellRing, Droplets, Fan, Flame, Zap, type LucideIcon } from "lucide-react"
import Link from "next/link"
import * as React from "react"

import {
  calibrationLine,
  dailyTopKLines,
  leadHorizonPhrase,
  modelWhatPredicts,
  scenarioTitle,
  useMlModels,
  verifiedLine,
  type MlModel,
} from "@/entities/analytics"
import { workflowMode } from "@/shared/config/env"
import { cn } from "@/shared/lib/utils"
import { Button } from "@/shared/ui/button"
import { LoadingBar, StateMessage } from "@/shared/ui/state-message"

const ICON: Record<string, LucideIcon> = {
  flooding: Droplets,
  ventilation: Fan,
  fire: Flame,
  power_loss: Zap,
}

const FILTERS = [
  { key: "all", label: "Все" },
  { key: "flooding", label: "Насосы и подтопление" },
  { key: "ventilation", label: "Вентиляция" },
  { key: "power_loss", label: "Питание" },
  { key: "fire", label: "Пожарная" },
] as const

function horizonLabel(hours: number) {
  if (hours >= 72) return "3 суток"
  if (hours >= 24) return "сутки"
  if (hours >= 1) return `${Math.round(hours)} ч`
  return `${Math.round(hours * 60)} мин`
}

function Metric({ value, label }: { value: string; label: string }) {
  return (
    <div className="min-w-0">
      <p className="text-[20px] leading-none font-semibold tabular-nums">{value}</p>
      <p className="mt-1 text-[12px] text-muted-foreground">{label}</p>
    </div>
  )
}

function ModelCard({ model }: { model: MlModel }) {
  const Icon = model.name.startsWith("alarm") ? BellRing : (ICON[model.scenario] ?? Zap)
  const top5 = model.heldOut?.precisionTop5PerDay
  const topK = dailyTopKLines(model.dailyTopK, model.horizonHours)
  const calib = calibrationLine(model.heldOut?.ece)
  const lead = leadHorizonPhrase(model.leadTime?.medianLeadTimeHours, "за")
  const precision = model.leadTime?.alertPrecisionDedup
  const ap = model.heldOut?.avgPrecision
  const base = model.heldOut?.baseRate
  const lift = ap != null && base ? ap / base : null

  return (
    <article id={model.name} className="flex scroll-mt-20 flex-col border-r border-b border-border bg-elevated p-5">
      <div className="flex items-start gap-3">
        <span className="flex size-9 shrink-0 items-center justify-center border border-border">
          <Icon className="size-[18px] text-vena" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="text-[15.5px] leading-snug font-semibold">{scenarioTitle(model.scenario)}</h2>
          <p className="mt-0.5 text-[13px] text-muted-foreground">{modelWhatPredicts(model)}</p>
        </div>
        <span className="shrink-0 border border-border px-2 py-0.5 font-mono text-[12px] text-muted-foreground">
          {horizonLabel(model.horizonHours)}
        </span>
      </div>

      {top5 != null ? (
        <div className="mt-4 border-l-2 border-vena bg-surface/60 py-2.5 pr-3 pl-3">
          <p className="text-[13.5px]">
            Из 5 каналов с наибольшим риском в день{" "}
            <span className="text-[17px] font-semibold text-vena tabular-nums">{Math.round(top5 * 5)}</span> действительно
            отказывают {model.horizonHours >= 72 ? "за 3 суток" : "за сутки"}
          </p>
          {topK.length > 1 ? (
            <ul className="mt-1.5 space-y-0.5 text-[12.5px] text-muted-foreground">
              {topK.slice(1).map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      <div className="mt-4 grid grid-cols-3 divide-x divide-border border-y border-border py-3 [&>*]:px-3 [&>*:first-child]:pl-0">
        <Metric value={precision != null ? `${Math.round(precision * 100)}%` : "—"} label="тревог подтверждаются" />
        <Metric value={lead ? lead.replace("за ", "") : "—"} label="среднее упреждение" />
        <Metric value={lift != null ? `×${lift.toFixed(1)}` : "—"} label="точнее случайного выбора" />
      </div>

      <div className="mt-4 space-y-1 text-[12.5px] text-muted-foreground">
        {calib ? <p>{calib}</p> : null}
        <p>{verifiedLine(model.heldOut?.period)}</p>
      </div>
      <p className="mt-auto pt-3 text-[11.5px] text-faint">
        <span className="font-mono">{model.name}</span>
        {model.trainYears ? ` · обучение ${model.trainYears}` : ""}
        {model.features != null ? ` · ${model.features} признаков` : ""}
      </p>
    </article>
  )
}

export function ModelsPage() {
  const models = useMlModels()
  const [filter, setFilter] = React.useState<(typeof FILTERS)[number]["key"]>("all")

  if (workflowMode !== "api") {
    return (
      <StateMessage title="Модели доступны в рабочем режиме" description="Карточки моделей загружаются из API сервиса." />
    )
  }

  const list = (models.data ?? []).filter((model) => filter === "all" || model.scenario === filter)

  return (
    <div className="size-full overflow-y-auto">
      <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-5 px-4 py-5 sm:px-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-[24px] font-semibold tracking-[-0.01em]">Модели</h1>
            <p className="mt-1 max-w-[760px] text-[13.5px] text-muted-foreground">
              Что предсказывает каждая модель, на какой срок и насколько ей можно верить. Все цифры посчитаны на январе–июне
              2026 года — модели этих данных не видели.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button asChild variant="outline" size="sm">
              <Link href="/effect">Прогноз против факта</Link>
            </Button>
          </div>
        </div>
        <div role="tablist" aria-label="Система" className="flex gap-6 overflow-x-auto border-b border-border">
          {FILTERS.map((item) => {
            const count = (models.data ?? []).filter((model) => item.key === "all" || model.scenario === item.key).length
            return (
              <button
                key={item.key}
                type="button"
                role="tab"
                aria-selected={filter === item.key}
                onClick={() => setFilter(item.key)}
                className={cn(
                  "-mb-px flex shrink-0 cursor-pointer items-baseline gap-1.5 border-b-2 pb-2.5 text-[14px] whitespace-nowrap outline-none focus-visible:ring-2 focus-visible:ring-ring/60",
                  filter === item.key ? "border-vena font-medium text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"
                )}
              >
                {item.label}
                <span className="font-mono text-[12px] text-faint">{count}</span>
              </button>
            )
          })}
        </div>
        {models.isPending ? (
          <LoadingBar className="min-h-40" />
        ) : models.isError ? (
          <StateMessage
            title="Реестр моделей недоступен"
            description="Не удалось загрузить карточки моделей."
            action={
              <Button variant="outline" size="sm" onClick={() => models.refetch()}>
                Повторить
              </Button>
            }
          />
        ) : list.length === 0 ? (
          <StateMessage title="Нет моделей" description="Для выбранной системы моделей нет." />
        ) : (
          <div className="grid border-t border-l border-border md:grid-cols-2 2xl:grid-cols-3">
            {list.map((model) => (
              <ModelCard key={model.name} model={model} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
