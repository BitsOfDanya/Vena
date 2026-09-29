"use client"

import { Search } from "lucide-react"

import { TYPE_LABEL, type AssetType, type ForecastHorizon } from "@/entities/infrastructure"
import { cn } from "@/shared/lib/utils"
import { Input } from "@/shared/ui/input"
import { Segmented } from "@/shared/ui/segmented"

export type SystemFilter = "all" | AssetType
export type RiskFilter = "all" | "attention" | "critical"
export type NetworkMode = "network" | "tree" | "assets" | "map"

const SYSTEMS: SystemFilter[] = ["all", "pump", "fan", "smoke", "power"]

const modeButton =
  "relative h-full px-3 text-[11px] font-medium tracking-[0.08em] uppercase outline-none focus-visible:z-10 focus-visible:ring-2 focus-visible:ring-ring/60"

export function NetworkToolbar({
  mode,
  onMode,
  title,
  descriptor,
  query,
  onQuery,
  onSubmitQuery,
  system,
  onSystem,
  risk,
  onRisk,
  horizon,
  onHorizon,
  showTree = false,
}: {
  mode: NetworkMode
  onMode: (value: NetworkMode) => void
  title: string
  descriptor: string
  query: string
  onQuery: (value: string) => void
  onSubmitQuery: () => void
  system: SystemFilter
  onSystem: (value: SystemFilter) => void
  risk: RiskFilter
  onRisk: (value: RiskFilter) => void
  horizon: ForecastHorizon
  onHorizon: (value: ForecastHorizon) => void
  showTree?: boolean
}) {
  return (
    <div className="flex shrink-0 flex-wrap items-center gap-x-5 gap-y-3 px-6 pt-1 pb-3">
      <h1 className="flex items-baseline gap-3">
        <span className="text-[22px] font-semibold tracking-[-0.01em]">{title}</span>
        <span className="font-mono text-[12px] text-faint tabular-nums">{descriptor}</span>
      </h1>
      <div role="group" aria-label="Режим просмотра" className="inline-flex h-7 items-stretch rounded-md border bg-surface">
        <button
          type="button"
          aria-current={mode === "network"}
          onClick={() => onMode("network")}
          className={cn(modeButton, "rounded-l-[5px]", mode === "network" ? "bg-elevated text-foreground" : "text-muted-foreground hover:text-foreground")}
        >
          Схема
          {mode === "network" ? <span aria-hidden className="absolute inset-x-2 bottom-0 h-px bg-vena" /> : null}
        </button>
        {showTree ? (
          <button
            type="button"
            aria-current={mode === "tree"}
            onClick={() => onMode("tree")}
            className={cn(modeButton, "border-x", mode === "tree" ? "bg-elevated text-foreground" : "text-muted-foreground hover:text-foreground")}
          >
            Дерево
            {mode === "tree" ? <span aria-hidden className="absolute inset-x-2 bottom-0 h-px bg-vena" /> : null}
          </button>
        ) : null}
        <button
          type="button"
          aria-current={mode === "assets"}
          onClick={() => onMode("assets")}
          className={cn(
            modeButton,
            showTree ? "border-r" : "border-x",
            mode === "assets" ? "bg-elevated text-foreground" : "text-muted-foreground hover:text-foreground"
          )}
        >
          Объекты
          {mode === "assets" ? <span aria-hidden className="absolute inset-x-2 bottom-0 h-px bg-vena" /> : null}
        </button>
        <button
          type="button"
          aria-current={mode === "map"}
          onClick={() => onMode("map")}
          className={cn(modeButton, "rounded-r-[5px]", mode === "map" ? "bg-elevated text-foreground" : "text-muted-foreground hover:text-foreground")}
        >
          Карта
          {mode === "map" ? <span aria-hidden className="absolute inset-x-2 bottom-0 h-px bg-vena" /> : null}
        </button>
      </div>

      <form
        className="relative ml-auto"
        onSubmit={(event) => {
          event.preventDefault()
          onSubmitQuery()
        }}
      >
        <Search aria-hidden className="pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={query}
          onChange={(event) => onQuery(event.target.value)}
          placeholder="Поиск объектов"
          aria-label="Поиск объектов"
          className="h-7 w-44 pl-7 font-mono text-xs"
        />
      </form>

      <Segmented<SystemFilter>
        label="Фильтр системы"
        value={system}
        onChange={onSystem}
        options={SYSTEMS.map((value) => ({ value, label: value === "all" ? "Все" : TYPE_LABEL[value as AssetType] }))}
      />
      <Segmented<RiskFilter>
        label="Фильтр риска"
        value={risk}
        onChange={onRisk}
        options={[
          { value: "all", label: "Весь риск" },
          { value: "attention", label: "Внимание+" },
          { value: "critical", label: "Критично" },
        ]}
      />
      <Segmented<ForecastHorizon>
        label="Горизонт прогноза"
        value={horizon}
        onChange={onHorizon}
        options={[
          { value: 24, label: "24ч" },
          { value: 72, label: "72ч" },
        ]}
      />
    </div>
  )
}
