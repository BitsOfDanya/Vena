"use client"

import { Search } from "lucide-react"

import { TYPE_LABEL, type AssetType, type ForecastHorizon } from "@/entities/infrastructure"
import { Input } from "@/shared/ui/input"
import { Segmented } from "@/shared/ui/segmented"

export type SystemFilter = "all" | AssetType
export type RiskFilter = "all" | "attention" | "critical"
export type NetworkMode = "network" | "picket" | "tree" | "assets" | "map"

const SYSTEMS: SystemFilter[] = ["all", "pump", "fan", "smoke", "power"]

const MODES: { value: NetworkMode; label: string }[] = [
  { value: "picket", label: "Схема" },
  { value: "network", label: "Схема" },
  { value: "tree", label: "Дерево" },
  { value: "assets", label: "Объекты" },
  { value: "map", label: "Карта" },
]

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
  showPicket = false,
  realGeometryOnly = false,
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
  showPicket?: boolean
  realGeometryOnly?: boolean
}) {
  const modes = MODES.filter((item) =>
    showPicket
      ? item.value === "picket" || item.value === "tree" || item.value === "assets"
      : (item.value !== "tree" || showTree) && item.value !== "picket" && (item.value !== "map" || !realGeometryOnly)
  )
  return (
    <div className="flex shrink-0 flex-wrap items-center gap-x-5 gap-y-3 px-6 pt-1 pb-3">
      <h1 className="flex min-w-0 flex-col">
        <span className="text-[24px] font-semibold tracking-[-0.01em]">{title}</span>
        {descriptor ? <span className="text-[13px] text-muted-foreground">{descriptor}</span> : null}
      </h1>
      <Segmented
        label="Режим просмотра"
        value={mode}
        onChange={onMode}
        options={modes.map((item) => ({ value: item.value, label: item.label }))}
      />

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
          placeholder="Объект, шкаф или канал"
          aria-label="Поиск объектов"
          className="h-8 w-56 pl-7 text-[13px]"
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
