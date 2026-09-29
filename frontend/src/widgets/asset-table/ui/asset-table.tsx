"use client"

import * as React from "react"

import {
  STATUS_LABEL,
  StatusMark,
  TYPE_LABEL,
  formatScore,
  type Asset,
} from "@/entities/infrastructure"
import { OPEN_STATUSES, STATUS_LABEL as ACTION_STATUS_LABEL, type MaintenanceAction } from "@/entities/maintenance"
import { formatAgo } from "@/shared/lib/time"
import { cn } from "@/shared/lib/utils"

type SortKey = "risk" | "id" | "lastEvent"

const COLUMNS: { key: SortKey | null; label: string; className: string }[] = [
  { key: "id", label: "Объект", className: "w-[7rem]" },
  { key: null, label: "Тип", className: "w-[6rem]" },
  { key: null, label: "Группа", className: "w-[6rem]" },
  { key: null, label: "Состояние", className: "w-[8rem]" },
  { key: "risk", label: "Риск", className: "w-[7rem]" },
  { key: null, label: "Прогноз", className: "w-[6rem]" },
  { key: "lastEvent", label: "Последнее событие", className: "w-[7rem]" },
  { key: null, label: "Открытая работа", className: "" },
]

export function AssetTable({
  assets,
  actions,
  now,
  selectedId,
  onSelect,
}: {
  assets: Asset[]
  actions: MaintenanceAction[]
  now: number
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  const [sort, setSort] = React.useState<SortKey>("risk")

  const openByAsset = new Map<string, MaintenanceAction>()
  for (const action of actions) {
    if (OPEN_STATUSES.includes(action.status) && !openByAsset.has(action.assetId)) openByAsset.set(action.assetId, action)
  }

  const rows = [...assets].sort((left, right) => {
    if (sort === "id") return left.id.localeCompare(right.id)
    if (sort === "lastEvent") return (right.lastEventAt ?? 0) - (left.lastEventAt ?? 0)
    return right.riskScore - left.riskScore
  })

  return (
    <div className="h-full overflow-auto">
      <table className="w-full min-w-[900px] border-collapse text-[13px]">
        <thead className="sticky top-0 z-10 bg-surface">
          <tr className="border-b border-border">
            {COLUMNS.map((column) => (
              <th key={column.label} scope="col" className={cn("px-4 py-2 text-left font-medium text-muted-foreground", column.className)}>
                {column.key ? (
                  <button
                    type="button"
                    onClick={() => setSort(column.key as SortKey)}
                    className={cn(
                      "text-[12px] tracking-[0.06em] uppercase outline-none focus-visible:ring-2 focus-visible:ring-ring/60",
                      sort === column.key ? "text-foreground underline underline-offset-4" : "hover:text-foreground"
                    )}
                  >
                    {column.label}
                  </button>
                ) : (
                  <span className="text-[12px] tracking-[0.06em] uppercase">{column.label}</span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={COLUMNS.length} className="px-4 py-6 text-muted-foreground">
                Нет объектов, подходящих под фильтры.
              </td>
            </tr>
          ) : (
            rows.map((asset) => {
              const action = openByAsset.get(asset.id)
              return (
                <tr
                  key={asset.id}
                  onClick={() => onSelect(asset.id)}
                  tabIndex={0}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault()
                      onSelect(asset.id)
                    }
                  }}
                  className={cn(
                    "cursor-pointer border-b border-border-soft outline-none hover:bg-elevated focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/60",
                    asset.id === selectedId && "bg-elevated"
                  )}
                >
                  <td className="px-4 py-2 font-mono">{asset.id}</td>
                  <td className="px-4 py-2 text-muted-foreground">{TYPE_LABEL[asset.type]}</td>
                  <td className="px-4 py-2 font-mono text-muted-foreground">{asset.group}</td>
                  <td className="px-4 py-2">
                    <span className="flex items-center gap-2">
                      <StatusMark status={asset.status} />
                      {STATUS_LABEL[asset.status]}
                    </span>
                  </td>
                  <td className="px-4 py-2">
                    <span className="flex items-center gap-2">
                      <span aria-hidden className="h-1 w-12 bg-grid">
                        <span
                          className={cn(
                            "block h-full",
                            asset.status === "critical" ? "bg-status-critical" : asset.status === "attention" ? "bg-status-attention" : "bg-status-normal"
                          )}
                          style={{ width: `${Math.round(asset.riskScore)}%` }}
                        />
                      </span>
                      <span className="font-mono tabular-nums">{formatScore(asset.riskScore, asset.scoreType)}</span>
                    </span>
                  </td>
                  <td className="px-4 py-2 font-mono text-muted-foreground tabular-nums">{asset.forecastHorizon}h</td>
                  <td className="px-4 py-2 font-mono text-muted-foreground tabular-nums">
                    {asset.lastEventAt ? formatAgo(asset.lastEventAt, now) : "—"}
                  </td>
                  <td className="px-4 py-2">
                    {action ? (
                      <span className="text-vena">
                        {action.id} · {ACTION_STATUS_LABEL[action.status]}
                      </span>
                    ) : (
                      <span className="text-faint">—</span>
                    )}
                  </td>
                </tr>
              )
            })
          )}
        </tbody>
      </table>
    </div>
  )
}
