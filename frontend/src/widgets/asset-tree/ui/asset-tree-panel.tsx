"use client"

import * as React from "react"

import { useAssetTree, type ObjectNode } from "@/entities/analytics"
import { SCENARIO_LABEL, type PredictionScenario } from "@/entities/prediction"
import { cn } from "@/shared/lib/utils"
import { LoadingBar, StateMessage } from "@/shared/ui/state-message"
import type { RiskFilter, SystemFilter } from "@/widgets/network-toolbar"

function hiTone(index: number | null) {
  if (index === null) return "text-faint"
  if (index < 40) return "text-status-critical"
  if (index < 70) return "text-status-attention"
  return "text-status-normal"
}

function scenarioText(scenario: string | null | undefined) {
  if (!scenario) return null
  return SCENARIO_LABEL[scenario as PredictionScenario] ?? scenario
}

function riskLine(riskByScenario: Record<string, number>) {
  const entries = Object.entries(riskByScenario)
    .filter(([, value]) => value > 0)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
  if (entries.length === 0) return null
  return entries
    .map(([scenario, value]) => `${scenarioText(scenario) ?? scenario} ${Math.round(value * 100)}%`)
    .join(" · ")
}

function channelMatches(
  channel: ObjectNode["sections"][number]["channels"][number],
  system: SystemFilter,
  risk: RiskFilter,
  needle: string
) {
  if (system !== "all") {
    const typeHint = `${channel.sensorType ?? ""} ${channel.scenario}`.toLowerCase()
    if (system === "pump" && !typeHint.includes("pump") && channel.scenario !== "flooding") return false
    if (system === "fan" && !typeHint.includes("fan") && channel.scenario !== "ventilation") return false
    if (system === "smoke" && !typeHint.includes("smoke") && channel.scenario !== "fire") return false
    if (system === "power" && !typeHint.includes("phase") && !typeHint.includes("power") && channel.scenario !== "power_loss")
      return false
  }
  if (risk === "attention" && channel.riskLevel !== "attention" && channel.riskLevel !== "critical") return false
  if (risk === "critical" && channel.riskLevel !== "critical") return false
  if (
    needle &&
    !channel.assetId.toLowerCase().includes(needle) &&
    !(channel.name?.toLowerCase().includes(needle) ?? false)
  ) {
    return false
  }
  return true
}

export function AssetTreePanel({
  query,
  selectedId,
  onSelect,
  system = "all",
  risk = "all",
}: {
  query: string
  selectedId: string | null
  onSelect: (assetId: string) => void
  system?: SystemFilter
  risk?: RiskFilter
}) {
  const tree = useAssetTree()
  const needle = query.trim().toLowerCase()

  if (tree.isPending) return <LoadingBar />
  if (tree.isError) {
    return (
      <StateMessage
        title="Дерево недоступно"
        description="Не удалось загрузить реестр объектов из снимка прогнозов."
      />
    )
  }

  const objects = (tree.data ?? [])
    .map((object) => filterObject(object, system, risk, needle))
    .filter((object): object is ObjectNode => object !== null)

  if (objects.length === 0) {
    return <StateMessage title="Нет объектов" description="В дереве СМВУ нет узлов по текущему фильтру." />
  }

  return (
    <div className="h-full overflow-auto px-6 py-3">
      <p className="mb-3 text-[12px] text-muted-foreground">
        Здоровье: &lt;40 критично · &lt;70 внимание · иначе норма
      </p>
      <ul className="space-y-4">
        {objects.map((object) => (
          <li key={object.objectId} className="border border-border bg-elevated">
            <div className="flex items-baseline gap-3 border-b border-border-soft px-4 py-2.5">
              <span className="text-[15px] font-semibold">{object.label}</span>
              <span className="font-mono text-[12px] text-faint">{object.objectId}</span>
              <span className={cn("ml-auto font-mono text-[13px] tabular-nums", hiTone(object.healthIndex))}>
                {object.healthIndex === null ? "Здоровье —" : `Здоровье ${object.healthIndex}`}
              </span>
            </div>
            <ul>
              {object.sections.map((section) => {
                const risks = riskLine(section.riskByScenario)
                return (
                  <li key={section.group} className="border-b border-border-soft last:border-b-0">
                    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-4 py-2">
                      <span className="text-[13px] font-medium">{section.label ?? section.group}</span>
                      {section.mainScenario ? (
                        <span className="text-[12px] text-muted-foreground">{scenarioText(section.mainScenario)}</span>
                      ) : null}
                      <span className={cn("ml-auto font-mono text-[12px] tabular-nums", hiTone(section.healthIndex))}>
                        {section.healthIndex === null ? "—" : section.healthIndex}
                      </span>
                    </div>
                    {risks ? <p className="px-4 pb-1 text-[11px] text-faint">{risks}</p> : null}
                    <ul className="pb-2">
                      {section.channels.map((channel) => (
                        <li key={channel.assetId}>
                          <button
                            type="button"
                            onClick={() => onSelect(channel.assetId)}
                            className={cn(
                              "grid w-full grid-cols-[7rem_1fr_6rem_4rem_3.5rem] items-center gap-3 px-4 py-1.5 text-left text-[13px] outline-none hover:bg-surface focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/60",
                              selectedId === channel.assetId && "bg-surface"
                            )}
                          >
                            <span className="font-mono tabular-nums">{channel.assetId}</span>
                            <span className="truncate text-muted-foreground">{channel.name ?? channel.sensorType ?? "—"}</span>
                            <span className="truncate text-[12px] text-muted-foreground">{scenarioText(channel.scenario)}</span>
                            <span className="font-mono text-[12px] tabular-nums">{channel.probability === null ? "Нет прогноза" : `${Math.round(channel.probability * 100)}%`}</span>
                            <span
                              className={cn(
                                "text-[11px] tracking-[0.04em] uppercase",
                                channel.riskLevel === "critical"
                                  ? "text-status-critical"
                                  : channel.riskLevel === "attention"
                                    ? "text-status-attention"
                                    : "text-faint"
                              )}
                            >
                              {channel.riskLevel === "critical"
                                ? "крит."
                                : channel.riskLevel === "attention"
                                  ? "вним."
                                  : "норма"}
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </li>
                )
              })}
            </ul>
          </li>
        ))}
      </ul>
    </div>
  )
}

function filterObject(
  object: ObjectNode,
  system: SystemFilter,
  risk: RiskFilter,
  needle: string
): ObjectNode | null {
  const sections = object.sections
    .map((section) => {
      const sectionNeedleHit =
        !needle ||
        object.objectId.toLowerCase().includes(needle) ||
        object.label.toLowerCase().includes(needle) ||
        section.group.toLowerCase().includes(needle) ||
        (section.label?.toLowerCase().includes(needle) ?? false)
      const channels = section.channels.filter((channel) =>
        channelMatches(channel, system, risk, sectionNeedleHit ? "" : needle)
      )
      if (channels.length === 0) return null
      return { ...section, channels }
    })
    .filter((section): section is ObjectNode["sections"][number] => section !== null)

  if (sections.length === 0) return null
  return { ...object, sections }
}
