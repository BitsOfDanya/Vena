"use client"

import * as React from "react"

import { useAssets, useNetwork, usePulse } from "@/entities/infrastructure"
import { useActions } from "@/entities/maintenance"
import { CreateActionSheet, type ActionDraft } from "@/features/create-action"
import { useWorkspace } from "@/features/workspace"
import { workflowMode } from "@/shared/config/env"
import { useIsMobile } from "@/shared/lib/hooks/use-mobile"
import { Button } from "@/shared/ui/button"
import { LoadingBar, StateMessage } from "@/shared/ui/state-message"
import { AssetDiagnostic } from "@/widgets/asset-diagnostic"
import { AssetTable } from "@/widgets/asset-table"
import { AssetTreePanel } from "@/widgets/asset-tree"
import { NetworkCanvas } from "@/widgets/network-canvas"
import { NetworkInspector } from "@/widgets/network-inspector"
import { NetworkMap } from "@/widgets/network-map"
import { NetworkToolbar, type NetworkMode, type RiskFilter, type SystemFilter } from "@/widgets/network-toolbar"

export function NetworkPage() {
  const { now, horizon, setHorizon, selectedAssetId, selectAsset } = useWorkspace()
  const isMobile = useIsMobile()
  const network = useNetwork(now, horizon)
  const pulse = usePulse(now)
  const apiMode = workflowMode === "api"
  const [query, setQuery] = React.useState("")
  const [system, setSystem] = React.useState<SystemFilter>("all")
  const [risk, setRisk] = React.useState<RiskFilter>(apiMode ? "attention" : "all")
  const [diagnostic, setDiagnostic] = React.useState(false)
  const [sheetOpen, setSheetOpen] = React.useState(false)
  const [draft, setDraft] = React.useState<ActionDraft>({})
  const [focusId, setFocusId] = React.useState<string | null>(selectedAssetId)
  const [mode, setMode] = React.useState<NetworkMode>(apiMode ? "tree" : "network")
  const assets = useAssets(now, horizon)
  const actions = useActions()

  const needle = query.trim().toLowerCase()
  const nodes = network.data?.nodes
  const matches = React.useMemo(
    () =>
      (nodes ?? []).filter((node) => {
        if (system !== "all" && node.type !== system) return false
        if (risk === "attention" && node.status !== "attention" && node.status !== "critical") return false
        if (risk === "critical" && node.status !== "critical") return false
        if (needle && !node.id.toLowerCase().includes(needle) && !node.group.toLowerCase().includes(needle)) return false
        return true
      }),
    [nodes, system, risk, needle]
  )
  const dimmed = React.useMemo(() => {
    const visible = new Set(matches.map((node) => node.id))
    return new Set((nodes ?? []).filter((node) => !visible.has(node.id)).map((node) => node.id))
  }, [matches, nodes])

  const openAction = (next: ActionDraft) => {
    const asset = (assets.data ?? []).find((item) => item.id === next.assetId)
    setDraft({
      ...next,
      sourcePredictionId: next.sourcePredictionId ?? asset?.predictionId ?? undefined,
      sourceModelId: next.sourceModelId ?? asset?.predictionModelId ?? undefined,
      sourceScore: next.sourceScore,
      sourceHorizonHours: next.sourceHorizonHours ?? asset?.forecastHorizon,
    })
    setSheetOpen(true)
  }

  if (isMobile) {
    return (
      <StateMessage
        title="Нужен экран пошире"
        description="Схема сети рассчитана на настольные и диспетчерские экраны. На этом устройстве используйте «Пульс» для текущей активности и «Работы» для планирования."
      />
    )
  }

  if (diagnostic && selectedAssetId) {
    return (
      <>
        <AssetDiagnostic
          assetId={selectedAssetId}
          onBack={() => setDiagnostic(false)}
          onCreateAction={() => openAction({ assetId: selectedAssetId })}
        />
        <CreateActionSheet open={sheetOpen} onOpenChange={setSheetOpen} draft={draft} />
      </>
    )
  }

  return (
    <div className="flex size-full flex-col">
      <NetworkToolbar
        mode={mode}
        onMode={setMode}
        title="Инфраструктурная сеть"
        descriptor={
          mode === "tree"
            ? "объект → секция → канал · Health Index"
            : network.data
              ? `${network.data.groups.length} групп · ${network.data.nodes.length} объектов`
              : ""
        }
        query={query}
        onQuery={setQuery}
        onSubmitQuery={() => {
          const first = matches[0]
          if (first && needle) {
            selectAsset(first.id)
            setFocusId(`${first.id}`)
          }
        }}
        system={system}
        onSystem={setSystem}
        risk={risk}
        onRisk={setRisk}
        horizon={horizon}
        onHorizon={setHorizon}
        showTree={apiMode}
        realGeometryOnly={apiMode}
      />
      <div className="relative flex min-h-0 flex-1">
        <div className="relative min-w-0 flex-1">
          {mode === "tree" ? (
            <AssetTreePanel
              query={query}
              selectedId={selectedAssetId}
              system={system}
              risk={risk}
              onSelect={(id) => {
                selectAsset(id)
                setFocusId(null)
              }}
            />
          ) : network.isPending ? (
            <LoadingBar />
          ) : network.isError ? (
            <StateMessage
              title="Схема недоступна"
              description="Не удалось загрузить схему инфраструктуры."
              action={
                <Button variant="outline" size="sm" onClick={() => network.refetch()}>
                  Повторить
                </Button>
              }
            />
          ) : mode === "assets" ? (
            <AssetTable
              assets={(assets.data ?? []).filter((asset) => {
                if (system !== "all" && asset.type !== system) return false
                if (risk === "attention" && asset.status !== "attention" && asset.status !== "critical") return false
                if (risk === "critical" && asset.status !== "critical") return false
                if (needle && !asset.id.toLowerCase().includes(needle) && !asset.group.toLowerCase().includes(needle)) return false
                return true
              })}
              actions={actions.data ?? []}
              now={now}
              selectedId={selectedAssetId}
              onSelect={(id) => selectAsset(id)}
            />
          ) : mode === "map" && network.data ? (
            <NetworkMap
              nodes={matches}
              selectedId={selectedAssetId}
              dimmed={dimmed}
              onSelect={(id) => {
                selectAsset(id)
                setFocusId(null)
              }}
            />
          ) : network.data ? (
            <>
              <NetworkCanvas
                model={network.data}
                selectedId={selectedAssetId}
                dimmed={dimmed}
                pulseAssetId={pulse.data?.recent[0]?.assetId ?? null}
                focusId={focusId}
                onSelect={(id) => {
                  selectAsset(id)
                  setFocusId(null)
                }}
              />
              {matches.length === 0 ? (
                <div className="pointer-events-none absolute inset-x-0 top-6 flex justify-center">
                  <p className="rounded-md border bg-popover px-3 py-2 text-sm text-muted-foreground">Нет объектов, подходящих под фильтры.</p>
                </div>
              ) : null}
            </>
          ) : null}
        </div>
        {selectedAssetId ? (
          <NetworkInspector
            assetId={selectedAssetId}
            onClose={() => selectAsset(null)}
            onInspect={() => setDiagnostic(true)}
            onCreateAction={(next) => openAction(next)}
          />
        ) : null}
      </div>
      <CreateActionSheet open={sheetOpen} onOpenChange={setSheetOpen} draft={draft} />
    </div>
  )
}
