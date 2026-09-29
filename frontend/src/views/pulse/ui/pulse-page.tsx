"use client"

import { useRouter } from "next/navigation"
import * as React from "react"

import {
  EVENT_TYPE_LABEL,
  EventGlyph,
  TYPE_LABEL,
  glyphKind,
  usePulse,
  usePulseSummary,
  useSituations,
  type AssetType,
  type PulseData,
  type Situation,
} from "@/entities/infrastructure"
import { OPEN_STATUSES, useActions } from "@/entities/maintenance"
import { useAcknowledgeNotification, useNotifications } from "@/entities/notification"
import type { InspectionPlanItem } from "@/entities/analytics"
import {
  SCENARIO_LABEL,
  formatProbability,
  formatProbabilityDelta,
  getAssetPrediction,
  useBackendSituations,
  useCriticalPredictions,
  useRiskRising,
  useSnapshotStatus,
  type PredictionScenario,
} from "@/entities/prediction"
import { CreateActionSheet, type ActionDraft } from "@/features/create-action"
import { useWorkspace } from "@/features/workspace"
import { workflowMode } from "@/shared/config/env"
import { formatClock } from "@/shared/lib/time"
import { cn } from "@/shared/lib/utils"
import { Button } from "@/shared/ui/button"
import { Segmented } from "@/shared/ui/segmented"
import { LoadingBar, StateMessage } from "@/shared/ui/state-message"
import { ClusterInspector, PatternInspector } from "@/widgets/cluster-inspector"
import { LEGEND, PulseSurface, patternLabel, type PulseSelection } from "@/widgets/pulse-surface"
import { ReplayEntry } from "@/widgets/replay-controller"
import { PulseSummaryModules, ShiftSummary, SnapshotLine } from "@/widgets/pulse-summary"
import { SituationRail } from "@/widgets/situation-rail"
import { InspectionPlanPanel } from "@/widgets/inspection-plan"

import { RecentEvents } from "./recent-events"

const WINDOWS = [
  { value: 1, label: "1ч" },
  { value: 6, label: "6ч" },
  { value: 24, label: "24ч" },
]

const SCENARIO_FILTERS: { value: "all" | PredictionScenario; label: string }[] = [
  { value: "all", label: "Все" },
  { value: "fire", label: SCENARIO_LABEL.fire },
  { value: "flooding", label: SCENARIO_LABEL.flooding },
  { value: "power_loss", label: SCENARIO_LABEL.power_loss },
  { value: "ventilation", label: SCENARIO_LABEL.ventilation },
]

const TAPE_PREVIEW = 4
const TAPE_LIMIT = 12

function SectionTitle({ children, count }: { children: React.ReactNode; count?: number }) {
  return (
    <h2 className="mb-2 flex items-baseline gap-2.5 text-[13px] font-medium tracking-[0.1em] text-muted-foreground uppercase">
      {children}
      {count !== undefined ? <span className="font-mono text-[12px] text-faint tabular-nums">{count}</span> : null}
    </h2>
  )
}

function tapeType(data: PulseData, eventId: string): AssetType | undefined {
  return data.lanes.find((lane) => lane.events.some((item) => item.id === eventId))?.type
}

export function PulsePage() {
  const router = useRouter()
  const { now, horizon, mode, selectAsset, setCompare } = useWorkspace()
  const [windowHours, setWindowHours] = React.useState(6)
  const [scenarioFilter, setScenarioFilter] = React.useState<"all" | PredictionScenario>("all")
  const [selection, setSelection] = React.useState<PulseSelection | null>(null)
  const [tapeOpen, setTapeOpen] = React.useState(false)
  const [acknowledged, setAcknowledged] = React.useState<string[]>([])
  const [sheetOpen, setSheetOpen] = React.useState(false)
  const [draft, setDraft] = React.useState<ActionDraft>({})

  const apiMode = workflowMode === "api"
  const hideDemoTelemetry = apiMode
  const pulse = usePulse(now, windowHours, { enabled: !hideDemoTelemetry })
  const demoSummary = usePulseSummary(now, horizon, { enabled: !apiMode })
  const snapshot = useSnapshotStatus()
  const backendSituations = useBackendSituations()
  const riskRising = useRiskRising(horizon)
  const criticalPredictions = useCriticalPredictions(horizon)
  const demoSituations = useSituations(now, horizon, { enabled: !apiMode })
  const actions = useActions()
  const notifications = useNotifications()
  const acknowledge = useAcknowledgeNotification(now)

  const data = pulse.data
  const cluster = selection?.kind === "cluster" ? (data?.clusters.find((item) => item.id === selection.id) ?? null) : null
  const pattern = selection?.kind === "pattern" ? (data?.patterns.find((item) => item.id === selection.id) ?? null) : null
  const patternClusters = pattern && data ? data.clusters.filter((item) => pattern.clusterIds.includes(item.id)) : []
  const descriptor = apiMode ? "ЖУРНАЛ И ПРОГНОЗЫ" : data
    ? `${mode === "replay" ? "ПОВТОР" : "ЖИВОЙ"} · ${formatClock(data.from)}–${formatClock(data.now)}`
    : mode === "replay"
      ? "ПОВТОР"
      : "ЖИВОЙ"

  const summary = apiMode ? undefined : demoSummary.data
  const predictionsUnavailable = apiMode && (snapshot.isError || snapshot.data?.available === false)
  const apiSituations: Situation[] = (backendSituations.data ?? []).map((item) => ({
    id: item.id,
    type: item.type === "pattern" ? "pattern" : "risk",
    severity: item.severity === "critical" ? "critical" : "warning",
    title: item.title,
    assetIds: item.assetIds,
    patternId: item.patternId,
    summary: item.summary,
    changedAt: item.updatedAt,
    riskScore: item.riskScore,
    scoreText: item.riskScore === null ? null : formatProbability(item.riskScore),
    delta: item.riskDelta,
    horizon: (item.forecastHorizon ?? null) as Situation["horizon"],
    primaryReason: item.primaryReason,
    status: item.status,
    scenario: item.scenario,
    location: item.location,
    locationGroup: item.locationGroup,
    assetCount: item.assetCount,
    incidentProbability: item.incidentProbability,
    healthIndex: item.healthIndex,
    modelId: item.modelId,
    recommendation: item.recommendation,
    history: item.history,
  }))

  const openActions = (actions.data ?? []).filter((action) => OPEN_STATUSES.includes(action.status))
  const actionsDue = openActions.filter((action) => action.recommendedAt - now <= 24 * 3_600_000).length
  const actionsOverdue = openActions.filter((action) => action.recommendedAt < now).length
  const completedThisShift = (actions.data ?? []).filter(
    (action) => action.result !== null && summary !== undefined && action.result.closedAt >= summary.shift.since
  ).length
  const resolved: Situation[] = (apiMode ? apiSituations : (demoSituations.data ?? [])).map((situation) => {
    if (situation.type === "risk" && openActions.some((action) => situation.assetIds.includes(action.assetId))) {
      return { ...situation, status: "action_created" }
    }
    const notification = (notifications.data ?? []).find(
      (item) =>
        (item.assetId !== null && situation.assetIds.includes(item.assetId)) ||
        (item.patternId !== null && item.patternId === situation.patternId)
    )
    if (acknowledged.includes(situation.id) || (notification && notification.status !== "new")) {
      return { ...situation, status: "acknowledged" }
    }
    return situation
  })
  const filtered = resolved.filter(
    (situation) => scenarioFilter === "all" || situation.scenario === scenarioFilter || (!situation.scenario && scenarioFilter === "equipment")
  )

  const clusterPatternOf = (assetType: AssetType | undefined, timestamp: number) => {
    if (!data || !assetType) return null
    const hit = data.clusters.find((item) => item.systemType === assetType && timestamp >= item.start && timestamp <= item.end)
    return hit ? (data.patterns.find((item) => item.clusterIds.includes(hit.id)) ?? null) : null
  }

  function inspect(situation: Situation) {
    if (situation.type === "pattern") {
      setSelection({ kind: "pattern", id: situation.id })
      return
    }
    selectAsset(situation.assetIds[0])
    setCompare(situation.assetIds.slice(0, 5))
    router.push("/network")
  }

  function acknowledgeSituation(situation: Situation) {
    setAcknowledged((current) => [...current, situation.id])
    const notification = (notifications.data ?? []).find(
      (item) =>
        (item.assetId !== null && situation.assetIds.includes(item.assetId)) ||
        (item.patternId !== null && item.patternId === situation.patternId)
    )
    if (notification && notification.status === "new") acknowledge.mutate(notification.id)
  }

  async function createAction(situation: Situation) {
    const assetId = situation.assetIds[0]
    let prediction =
      apiMode
        ? [...(criticalPredictions.data?.critical ?? []), ...(criticalPredictions.data?.attention ?? [])].find(
            (item) => item.assetId === assetId,
          )
        : undefined
    if (apiMode && assetId && !prediction) {
      prediction = (await getAssetPrediction(assetId)) ?? undefined
    }
    const reason = situation.recommendation
      ? `${situation.recommendation.title}${situation.recommendation.hint ? ` — ${situation.recommendation.hint}` : ""}`
      : `${situation.title}: ${situation.primaryReason}`
    const rawScore = prediction?.score ?? situation.incidentProbability ?? situation.riskScore ?? undefined
    setDraft({
      assetId,
      reason,
      priority: situation.severity === "critical" ? "high" : "medium",
      sourcePredictionId: prediction?.id,
      sourceModelId: prediction?.modelId ?? situation.modelId ?? undefined,
      sourceScore: rawScore == null ? undefined : rawScore > 1 ? rawScore / 100 : rawScore,
      sourceHorizonHours: prediction?.horizonHours ?? situation.horizon ?? undefined,
    })
    setSheetOpen(true)
  }

  function createFromInspection(item: InspectionPlanItem) {
    setDraft({
      assetId: item.assetId,
      reason: item.reason
        ? `Осмотр · ${item.reason}`
        : `План осмотра · ${item.name?.trim() || item.assetId}`,
      priority: item.riskLevel === "critical" || item.riskLevel === "attention" ? "high" : "medium",
      kind: "inspect",
      sourcePredictionId: item.predictionId,
      sourceModelId: item.modelId,
      sourceScore: item.probability,
      sourceHorizonHours: item.modelId.includes("72") ? 72 : 24,
    })
    setSheetOpen(true)
  }

  return (
    <div className="flex size-full min-h-0 flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-x-8 gap-y-3 px-6 pt-4 pb-3">
        <h1 className="flex items-baseline gap-3">
          <span className="text-[26px] font-semibold tracking-[-0.01em]">Пульс системы</span>
          <span className={cn("font-mono text-[13px] tabular-nums", mode === "replay" ? "text-status-attention" : "text-faint")}>
            {descriptor}
          </span>
        </h1>
        <div className="ml-auto flex flex-wrap items-center gap-2.5">
          <Segmented label="Окно пульса" value={windowHours} onChange={setWindowHours} options={WINDOWS} />
          {!apiMode && <ReplayEntry />}
        </div>
      </div>

      <div className="shrink-0 space-y-1.5 px-6 pb-3">
        <PulseSummaryModules
          summary={summary}
          apiMode={apiMode}
          predictionsUnavailable={Boolean(predictionsUnavailable)}
          criticalCount={criticalPredictions.data?.criticalCount ?? 0}
          criticalAssets={(criticalPredictions.data?.critical ?? []).slice(0, 2).map((item) => `${item.assetId} · ${formatProbability(item.score)}`)}
          attentionCount={criticalPredictions.data?.attentionCount ?? 0}
          risingCount={(riskRising.data ?? []).filter((item) => (item.scoreDelta ?? 0) > 0).length}
          risingTop={(() => {
            const top = (riskRising.data ?? []).find((item) => (item.scoreDelta ?? 0) > 0)
            return top ? `${top.assetId} ${formatProbabilityDelta(top.scoreDelta ?? 0)}` : null
          })()}
          actionsDue={actionsDue}
          actionsOverdue={actionsOverdue}
          onInspectCritical={() => {
            const first = apiMode
              ? criticalPredictions.data?.critical[0]
                ? { id: criticalPredictions.data.critical[0].assetId }
                : criticalPredictions.data?.attention[0]
                  ? { id: criticalPredictions.data.attention[0].assetId }
                  : undefined
              : summary?.critical.assets[0]
            if (first) {
              selectAsset(first.id)
              setCompare([first.id])
              router.push("/timeline")
            } else {
              router.push("/network")
            }
          }}
          onViewChanges={() => router.push("/network")}
          onInvestigatePattern={() => {
            const latest = summary?.patterns.latest
            if (latest) setSelection({ kind: "pattern", id: latest.id })
          }}
          onOpenPlan={() => router.push("/actions")}
        />
        {apiMode ? (
          <SnapshotLine snapshot={snapshot.data} />
        ) : (
          <ShiftSummary summary={summary} completed={completedThisShift} />
        )}
        {apiMode && !predictionsUnavailable ? (
          <InspectionPlanPanel className="pt-2" onCreate={createFromInspection} />
        ) : null}
      </div>

      <div className="flex min-h-0 flex-1">
        <div className="relative flex min-w-0 flex-1 flex-col">
          <section aria-label="Требуют внимания" className="flex max-h-[38%] shrink-0 flex-col px-6 pb-3">
            <div className="mb-2 flex flex-wrap items-baseline gap-x-4 gap-y-2">
              <SectionTitle count={filtered.length}>Требуют внимания</SectionTitle>
              {apiMode && !predictionsUnavailable ? (
                <span className="text-[12px] text-muted-foreground">
                  в очереди {filtered.length}
                  {(criticalPredictions.data?.criticalCount ?? 0) + (criticalPredictions.data?.attentionCount ?? 0) >
                  filtered.length
                    ? ` · критичных/внимание в снимке: ${(criticalPredictions.data?.criticalCount ?? 0) + (criticalPredictions.data?.attentionCount ?? 0)}`
                    : null}
                </span>
              ) : null}
              <Segmented
                label="Сценарий"
                value={scenarioFilter}
                onChange={setScenarioFilter}
                options={SCENARIO_FILTERS.map((item) => ({
                  ...item,
                  label:
                    item.value === "all"
                      ? `${item.label} (${resolved.length})`
                      : `${item.label} (${resolved.filter((s) => s.scenario === item.value).length})`,
                }))}
              />
            </div>
            {predictionsUnavailable ? (
              <StateMessage
                title="Прогнозы недоступны"
                description="Бэкенд не отдаёт снимок прогнозов, риски не рассчитываются. Демонстрационные значения в этом режиме не подставляются."
              />
            ) : (apiMode ? backendSituations.isPending : demoSituations.isPending) ? (
              <LoadingBar className="min-h-24" />
            ) : (
              <SituationRail
                className="min-h-0 overflow-y-auto"
                situations={filtered}
                now={now}
                onInspect={inspect}
                onAcknowledge={acknowledgeSituation}
                onCreateAction={createAction}
              />
            )}
          </section>

          {apiMode ? <RecentEvents hours={windowHours} onSelect={(id) => { selectAsset(id); router.push("/network") }} /> : (
          <section aria-label="Активность" className="flex min-h-[120px] flex-1 flex-col border-t border-border-soft px-6 pt-2.5">
            <div className="mb-2 flex items-baseline gap-4">
              <h2 className="flex items-baseline gap-2.5 text-[13px] font-medium tracking-[0.1em] text-muted-foreground uppercase">
                Активность · последние {windowHours} ч
              </h2>
              {!hideDemoTelemetry ? (
                <ul aria-label="Легенда" className="ml-auto hidden items-center gap-3 text-[11px] text-faint lg:flex">
                  {LEGEND.map((item) => (
                    <li key={item.label} className="flex items-center gap-1">
                      <EventGlyph kind={item.kind} />
                      {item.label}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
            <div className="min-h-0 flex-1 px-1">
              {pulse.isPending ? (
                <LoadingBar />
              ) : pulse.isError ? (
                <StateMessage
                  title="Пульс недоступен"
                  description="Не удалось загрузить данные об активности."
                  action={
                    <Button variant="outline" size="sm" onClick={() => pulse.refetch()}>
                      Повторить
                    </Button>
                  }
                />
              ) : data && data.lanes.every((lane) => lane.events.length === 0) ? (
                <StateMessage title="Нет активности" description="В выбранном окне нет событий." />
              ) : data ? (
                <PulseSurface data={data} selection={selection} onSelect={setSelection} />
              ) : null}
            </div>
          </section>
          )}

          {hideDemoTelemetry ? null : (
          <section aria-label="Недавние события" className="mt-3 shrink-0 border-t border-border bg-surface">
            <div className="flex items-center gap-3 px-6 py-2">
              <h2 className="flex items-baseline gap-2.5 text-[13px] font-medium tracking-[0.1em] text-muted-foreground uppercase">
                Недавние события
              </h2>
              <span className="font-mono text-[12px] text-faint tabular-nums">{data?.recent.length ?? 0}</span>
              <button
                type="button"
                onClick={() => setTapeOpen((open) => !open)}
                aria-expanded={tapeOpen}
                className="ml-auto text-[13px] text-vena underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring/60"
              >
                {tapeOpen ? "Свернуть" : "Все события"} →
              </button>
            </div>
            {data && data.recent.length > 0 ? (
                <ul className={cn("overflow-y-auto border-t border-border-soft", tapeOpen ? "max-h-[112px]" : "")}>
                  {data.recent.slice(0, tapeOpen ? TAPE_LIMIT : TAPE_PREVIEW).map((event) => {
                    const type = tapeType(data, event.id)
                    const linked = clusterPatternOf(type, event.timestamp)
                    return (
                      <li key={event.id}>
                        <button
                          type="button"
                          onClick={() => {
                            selectAsset(event.assetId)
                            router.push("/timeline")
                          }}
                          className="grid h-7 w-full grid-cols-[4.5rem_5.5rem_4.5rem_1fr_6rem_1rem] items-center gap-4 px-6 text-left text-[13px] outline-none hover:bg-elevated focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/60"
                        >
                          <span className="font-mono text-muted-foreground tabular-nums">{formatClock(event.timestamp)}</span>
                          <span className="font-mono">{event.assetId}</span>
                          <span className="text-muted-foreground">{type ? TYPE_LABEL[type] : "Датчик"}</span>
                          <span className="truncate">
                            <span className="text-foreground">{EVENT_TYPE_LABEL[event.type]}</span>
                            <span className="text-muted-foreground"> · {event.state}</span>
                          </span>
                          <span className="text-[12px] text-vena">{linked ? `Связка ${patternLabel(linked)}` : ""}</span>
                          <EventGlyph kind={glyphKind(event)} className="size-3.5" />
                        </button>
                      </li>
                    )
                  })}
                </ul>
            ) : (
              <p className="border-t border-border-soft px-6 py-3 text-[13px] text-muted-foreground">
                В выбранном окне нет значимых событий.
              </p>
            )}
          </section>
          )}
        </div>
        {cluster ? <ClusterInspector cluster={cluster} onClose={() => setSelection(null)} /> : null}
        {pattern ? (
          <PatternInspector
            pattern={pattern}
            clusters={patternClusters}
            onSelectCluster={(item) => setSelection({ kind: "cluster", id: item.id })}
            onClose={() => setSelection(null)}
          />
        ) : null}
      </div>
      <CreateActionSheet open={sheetOpen} onOpenChange={setSheetOpen} draft={draft} />
    </div>
  )
}
