"use client"

import * as React from "react"

import { RiskLevelLabel, scoreLabel, useAssetDetail, useTemporalBundles } from "@/entities/infrastructure"
import { useWorkspace } from "@/features/workspace"
import { cn } from "@/shared/lib/utils"
import { Button } from "@/shared/ui/button"
import { Inspector, InspectorBody, InspectorFooter, InspectorHeader, InspectorSection } from "@/shared/ui/inspector"
import { Segmented } from "@/shared/ui/segmented"
import { LoadingBar, StateMessage } from "@/shared/ui/state-message"
import { DEFAULT_LAYERS, TemporalCanvas } from "@/widgets/temporal-canvas"

export function AssetDiagnostic({
  assetId,
  onBack,
  onCreateAction,
}: {
  assetId: string
  onBack: () => void
  onCreateAction: () => void
}) {
  const { now, horizon } = useWorkspace()
  const [halfSpan, setHalfSpan] = React.useState(48)
  const temporal = useTemporalBundles([assetId], now, halfSpan, horizon)
  const detail = useAssetDetail(assetId, now, horizon)
  const asset = detail.data?.asset
  const total = detail.data?.factorGroups.reduce((sum, group) => sum + group.points, 0) ?? 0

  return (
    <div className="flex size-full">
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex shrink-0 items-center gap-4 border-b px-4 py-2.5">
          <h2 className="text-[13px] font-semibold tracking-[0.14em] uppercase">
            {assetId} <span className="text-faint">/</span> Диагностика
          </h2>
          <Segmented
            label="Окно истории и прогноза"
            className="ml-auto"
            value={halfSpan}
            onChange={setHalfSpan}
            options={[24, 48, 72].map((value) => ({ value, label: `${value}ч` }))}
          />
          <Button variant="outline" size="sm" onClick={onBack}>
            К сети
          </Button>
        </div>
        <div className="min-h-0 flex-1">
          {temporal.pending && temporal.bundles.length === 0 ? (
            <LoadingBar />
          ) : temporal.bundles.length === 0 ? (
            <StateMessage title="Нет истории" description="По этому объекту история недоступна." />
          ) : (
            <TemporalCanvas now={now} halfSpanHours={halfSpan} bundles={temporal.bundles} layers={DEFAULT_LAYERS} onZoom={setHalfSpan} />
          )}
        </div>
      </div>
      <Inspector label="Объяснение риска">
        <InspectorHeader eyebrow="Текущий риск" title={asset ? `${Math.round(asset.riskScore)}` : "—"}>
          {asset ? (
            <div className="mt-1 flex items-center gap-3">
              <RiskLevelLabel level={asset.riskLevel} />
              <span className="text-xs text-muted-foreground">{scoreLabel(asset.scoreType)} / 100</span>
            </div>
          ) : null}
        </InspectorHeader>
        <InspectorBody>
          <InspectorSection title="Факторы риска">
            {detail.data ? (
              <ul className="space-y-3">
                {detail.data.factorGroups.map((group) => (
                  <li key={group.key}>
                    <div className="flex items-baseline justify-between text-sm">
                      <span className="text-muted-foreground">{group.label}</span>
                      <span className="font-mono tabular-nums">+{group.points}</span>
                    </div>
                    <div className="mt-1 h-1 bg-border">
                      <div className={cn("h-full", group.key === "baseline" ? "bg-muted-foreground/60" : "bg-vena")} style={{ width: `${total > 0 ? (group.points / total) * 100 : 0}%` }} />
                    </div>
                  </li>
                ))}
                <li className="flex items-baseline justify-between border-t pt-2 text-sm">
                  <span className="text-[11px] font-medium tracking-[0.08em] text-faint uppercase">Риск</span>
                  <span className="font-mono tabular-nums">{total}</span>
                </li>
              </ul>
            ) : (
              <LoadingBar className="min-h-16" />
            )}
            <p className="mt-3 text-[11px] text-faint">
              Группировка по правилам: история, активность и состояние. Это не атрибуция модели.
            </p>
          </InspectorSection>
          <InspectorSection title="Сигналы">
            <ul className="divide-y">
              {(detail.data?.factors ?? []).map((factor) => (
                <li key={factor.key} className="flex items-center justify-between py-1.5 text-sm">
                  <span className="text-muted-foreground">{factor.label}</span>
                  <span className={cn("font-mono tabular-nums", factor.direction === "up" && "text-status-attention")}>{factor.value}</span>
                </li>
              ))}
            </ul>
          </InspectorSection>
        </InspectorBody>
        <InspectorFooter>
          <Button className="flex-1" onClick={onCreateAction}>
            Создать работу
          </Button>
        </InspectorFooter>
      </Inspector>
    </div>
  )
}
