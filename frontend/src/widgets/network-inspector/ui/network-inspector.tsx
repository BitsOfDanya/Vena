"use client"

import { ArrowDownRight, ArrowRight, ArrowUpRight } from "lucide-react"
import { useRouter } from "next/navigation"

import {
  EVENT_TYPE_LABEL,
  RiskLevelLabel,
  StatusLabel,
  TYPE_LABEL,
  formatDelta,
  scoreLabel,
  useAssetDetail,
  type FactorDirection,
} from "@/entities/infrastructure"
import { useWorkspace } from "@/features/workspace"
import { cn } from "@/shared/lib/utils"
import { formatAgo, formatClock, formatDateTime } from "@/shared/lib/time"
import { Button } from "@/shared/ui/button"
import { Inspector, InspectorBody, InspectorFooter, InspectorHeader, InspectorSection } from "@/shared/ui/inspector"
import { LoadingBar, StateMessage } from "@/shared/ui/state-message"

const DIRECTION_ICON: Record<FactorDirection, typeof ArrowUpRight> = {
  up: ArrowUpRight,
  down: ArrowDownRight,
  flat: ArrowRight,
}

const DIRECTION_LABEL: Record<FactorDirection, string> = {
  up: "рост",
  down: "снижение",
  flat: "без изменений",
}

export function NetworkInspector({
  assetId,
  onClose,
  onInspect,
  onCreateAction,
}: {
  assetId: string
  onClose: () => void
  onInspect: () => void
  onCreateAction: (draft: { assetId: string; reason: string; priority: "high" | "medium" | "low" }) => void
}) {
  const router = useRouter()
  const { now, horizon, selectAsset, setCompare } = useWorkspace()
  const detail = useAssetDetail(assetId, now, horizon)
  const data = detail.data

  if (detail.isPending) {
    return (
      <Inspector label="Инспектор объекта">
        <InspectorHeader title={assetId} onClose={onClose} />
        <LoadingBar />
      </Inspector>
    )
  }

  if (!data) {
    return (
      <Inspector label="Инспектор объекта">
        <InspectorHeader title={assetId} onClose={onClose} />
        <StateMessage title="Объект не найден" description="Этого объекта нет в текущем наборе данных." />
      </Inspector>
    )
  }

  const { asset } = data
  const priority = asset.riskLevel === "high" ? "high" : asset.riskLevel === "medium" ? "medium" : "low"
  const reasons = data.factors
    .filter((factor) => factor.direction === "up")
    .map((factor) => `${factor.label.toLowerCase()} ${factor.value}`)
    .join(", ")

  return (
    <Inspector label="Инспектор объекта">
      <InspectorHeader eyebrow={`${TYPE_LABEL[asset.type]} · ${asset.group}`} title={asset.id} onClose={onClose}>
        <div className="mt-1 flex items-center gap-3">
          {asset.status === "offline" ? <StatusLabel status="offline" /> : <RiskLevelLabel level={asset.riskLevel} />}
          <span className="font-mono text-[11px] text-muted-foreground">CH {asset.channelId}</span>
        </div>
      </InspectorHeader>
      <InspectorBody>
        <InspectorSection title={scoreLabel(asset.scoreType)}>
          <div className="flex items-baseline gap-3">
            <span className="font-mono text-4xl tabular-nums">{Math.round(asset.riskScore)}</span>
            <span className="font-mono text-sm text-muted-foreground">/ 100</span>
            <span className={cn("ml-auto font-mono text-sm tabular-nums", data.delta > 0 ? "text-status-attention" : "text-muted-foreground")}>
              {data.delta > 0 ? "↑" : data.delta < 0 ? "↓" : "→"}
              {formatDelta(Math.abs(data.delta))} с {formatClock(data.deltaSince)}
            </span>
          </div>
          <dl className="mt-3 grid grid-cols-2 gap-3 text-xs">
            <div>
              <dt className="text-[11px] font-medium tracking-[0.08em] text-faint uppercase">Окно прогноза</dt>
              <dd className="mt-0.5 font-mono text-sm tabular-nums">{asset.forecastHorizon} h</dd>
            </div>
            <div>
              <dt className="text-[11px] font-medium tracking-[0.08em] text-faint uppercase">Последнее событие</dt>
              <dd className="mt-0.5 font-mono text-sm tabular-nums">{asset.lastEventAt ? formatAgo(asset.lastEventAt, now) : "нет"}</dd>
            </div>
          </dl>
        </InspectorSection>

        <InspectorSection title="Факторы риска">
          <ul className="divide-y">
            {data.factors.map((factor) => {
              const Icon = DIRECTION_ICON[factor.direction]
              return (
                <li key={factor.key} className="flex items-center gap-3 py-1.5 text-sm">
                  <span className="text-muted-foreground">{factor.label}</span>
                  <span className={cn("ml-auto font-mono tabular-nums", factor.direction === "up" && "text-status-attention")}>{factor.value}</span>
                  <Icon aria-label={DIRECTION_LABEL[factor.direction]} className={cn("size-3.5", factor.direction === "up" ? "text-status-attention" : "text-faint")} />
                </li>
              )
            })}
          </ul>
          <p className="mt-2 text-[11px] text-faint">
            Основание: {data.factors[0]?.basis === "model_contribution" ? "вклад модели" : "правила по недавним событиям"}
          </p>
        </InspectorSection>

        <InspectorSection title="Недавняя активность">
          {data.recent.length === 0 ? (
            <p className="text-sm text-muted-foreground">За последние 48 часов значимых событий нет.</p>
          ) : (
            <ul className="space-y-1.5">
              {data.recent.map((event) => (
                <li key={event.id} className="flex gap-3 text-xs">
                  <span className="w-20 shrink-0 font-mono text-muted-foreground tabular-nums">{formatDateTime(event.timestamp).slice(-11)}</span>
                  <span>
                    {EVENT_TYPE_LABEL[event.type]} · {event.state}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </InspectorSection>

        <InspectorSection>
          <button
            type="button"
            className="text-xs text-vena underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring/60"
            onClick={() => {
              selectAsset(asset.id)
              setCompare([asset.id])
              router.push("/timeline")
            }}
          >
            Открыть в хронологии
          </button>
        </InspectorSection>
      </InspectorBody>
      <InspectorFooter>
        <Button variant="outline" className="flex-1" onClick={onInspect}>
          Осмотреть
        </Button>
        <Button
          className="flex-1"
          onClick={() => onCreateAction({ assetId: asset.id, reason: reasons ? `Повышенный риск: ${reasons}` : "Проверить текущее состояние", priority })}
        >
          Создать работу
        </Button>
      </InspectorFooter>
    </Inspector>
  )
}
