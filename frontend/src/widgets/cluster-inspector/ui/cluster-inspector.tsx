"use client"

import { useRouter } from "next/navigation"

import {
  EventGlyph,
  StatusLabel,
  TYPE_LABEL,
  formatDelta,
  formatScore,
  useAssets,
  type Asset,
  type PulseCluster,
  type PulsePattern,
} from "@/entities/infrastructure"
import { useWorkspace } from "@/features/workspace"
import { formatClock, formatDay } from "@/shared/lib/time"
import { Button } from "@/shared/ui/button"
import { Inspector, InspectorBody, InspectorFooter, InspectorHeader, InspectorSection } from "@/shared/ui/inspector"
import { cn } from "@/shared/lib/utils"

export function useInvolvedAssets(assetIds: string[]) {
  const { now, horizon } = useWorkspace()
  const assets = useAssets(now, horizon)
  return (assets.data ?? []).filter((asset) => assetIds.includes(asset.id)).sort((left, right) => right.riskScore - left.riskScore)
}

export function InvolvedAssets({ involved }: { involved: Asset[] }) {
  const router = useRouter()
  const { selectAsset } = useWorkspace()
  return involved.length === 0 ? (
    <p className="text-sm text-muted-foreground">Данные по объектам загружаются.</p>
  ) : (
    <ul className="divide-y">
      {involved.map((asset) => (
        <li key={asset.id}>
          <button
            type="button"
            onClick={() => {
              selectAsset(asset.id)
              router.push("/network")
            }}
            className="flex w-full items-center gap-3 py-2 text-left outline-none hover:bg-elevated focus-visible:ring-2 focus-visible:ring-ring/60"
          >
            <span className="font-mono text-sm">{asset.id}</span>
            <StatusLabel status={asset.status} />
            <span className="ml-auto font-mono text-xs text-muted-foreground tabular-nums">{formatScore(asset.riskScore, asset.scoreType)}</span>
          </button>
        </li>
      ))}
    </ul>
  )
}

export function OpenActions({ involved }: { involved: Asset[] }) {
  const router = useRouter()
  const { selectAsset, setCompare } = useWorkspace()
  return (
    <InspectorFooter>
      <Button
        variant="outline"
        className="flex-1"
        onClick={() => {
          if (involved[0]) selectAsset(involved[0].id)
          router.push("/network")
        }}
      >
        Открыть в сети
      </Button>
      <Button
        className="flex-1"
        onClick={() => {
          setCompare(involved.slice(0, 5).map((asset) => asset.id))
          if (involved[0]) selectAsset(involved[0].id)
          router.push("/timeline")
        }}
      >
        Открыть в хронологии
      </Button>
    </InspectorFooter>
  )
}

export function ClusterInspector({ cluster, onClose }: { cluster: PulseCluster; onClose: () => void }) {
  const involved = useInvolvedAssets(cluster.assetIds)

  return (
    <Inspector label="Инспектор кластера">
      <InspectorHeader eyebrow={`Кластер · ${formatDay(cluster.start)}`} title={`${formatClock(cluster.start)}–${formatClock(cluster.end)}`} onClose={onClose}>
        <p className="mt-0.5 text-xs text-muted-foreground">система · {TYPE_LABEL[cluster.systemType]}</p>
      </InspectorHeader>
      <InspectorBody>
        <InspectorSection>
          <dl className="grid grid-cols-3 gap-3">
            <div>
              <dt className="text-[11px] font-medium tracking-[0.08em] text-faint uppercase">Переходы</dt>
              <dd className="font-mono text-xl tabular-nums">{cluster.transitions}</dd>
            </div>
            <div>
              <dt className="text-[11px] font-medium tracking-[0.08em] text-faint uppercase">Объекты</dt>
              <dd className="font-mono text-xl tabular-nums">{cluster.assetIds.length}</dd>
            </div>
            <div>
              <dt className="text-[11px] font-medium tracking-[0.08em] text-faint uppercase">Δ риска</dt>
              <dd className={cn("font-mono text-xl tabular-nums", cluster.riskDelta > 1 && "text-status-attention")}>
                {formatDelta(cluster.riskDelta)}
              </dd>
            </div>
          </dl>
          <p className="mt-3 text-sm text-muted-foreground">{cluster.summary} по затронутым объектам ({TYPE_LABEL[cluster.systemType].toLowerCase()}) в этом окне.</p>
        </InspectorSection>
        <InspectorSection title="Затронутые объекты">
          <InvolvedAssets involved={involved} />
        </InspectorSection>
      </InspectorBody>
      <OpenActions involved={involved} />
    </Inspector>
  )
}

export function PatternInspector({
  pattern,
  clusters,
  onSelectCluster,
  onClose,
}: {
  pattern: PulsePattern
  clusters: PulseCluster[]
  onSelectCluster: (cluster: PulseCluster) => void
  onClose: () => void
}) {
  const involved = useInvolvedAssets(pattern.assetIds)
  return (
    <Inspector label="Инспектор паттерна">
      <InspectorHeader eyebrow={`Паттерн · ${formatDay(pattern.start)}`} title={`Паттерн ${String(pattern.number).padStart(3, "0")}`} onClose={onClose}>
        <p className="mt-0.5 font-mono text-xs text-muted-foreground tabular-nums">
          {formatClock(pattern.start)}–{formatClock(pattern.end)}
        </p>
      </InspectorHeader>
      <InspectorBody>
        <InspectorSection>
          <dl className="grid grid-cols-3 gap-3">
            <div>
              <dt className="text-[11px] font-medium tracking-[0.08em] text-faint uppercase">События</dt>
              <dd className="font-mono text-xl tabular-nums">{pattern.events}</dd>
            </div>
            <div>
              <dt className="text-[11px] font-medium tracking-[0.08em] text-faint uppercase">Системы</dt>
              <dd className="font-mono text-xl tabular-nums">{pattern.systems.length}</dd>
            </div>
            <div>
              <dt className="text-[11px] font-medium tracking-[0.08em] text-faint uppercase">Δ риска</dt>
              <dd className={cn("font-mono text-xl tabular-nums", pattern.riskDelta > 1 && "text-status-attention")}>{formatDelta(pattern.riskDelta)}</dd>
            </div>
          </dl>
          <p className="mt-3 text-sm text-muted-foreground">
            Связанная активность: нетипичные переходы в системах ({pattern.systems.map((type) => TYPE_LABEL[type].toLowerCase()).join(", ")}) в пределах одного часа.
          </p>
        </InspectorSection>
        <InspectorSection title="Кластеры в паттерне">
          <ul className="divide-y">
            {clusters.map((cluster) => (
              <li key={cluster.id}>
                <button
                  type="button"
                  onClick={() => onSelectCluster(cluster)}
                  className="flex w-full items-center gap-3 py-2 text-left text-sm outline-none hover:bg-elevated focus-visible:ring-2 focus-visible:ring-ring/60"
                >
                  <EventGlyph kind="cluster" />
                  <span>{TYPE_LABEL[cluster.systemType]}</span>
                  <span className="font-mono text-xs text-muted-foreground tabular-nums">
                    {formatClock(cluster.start)}–{formatClock(cluster.end)}
                  </span>
                  <span className="ml-auto font-mono text-xs tabular-nums">{cluster.transitions} соб.</span>
                </button>
              </li>
            ))}
          </ul>
        </InspectorSection>
        <InspectorSection title="Затронутые объекты">
          <InvolvedAssets involved={involved} />
        </InspectorSection>
      </InspectorBody>
      <OpenActions involved={involved} />
    </Inspector>
  )
}
