"use client"

import { StatusMark, type Situation } from "@/entities/infrastructure"
import { SCENARIO_LABEL, type PredictionScenario } from "@/entities/prediction"
import { formatAgo } from "@/shared/lib/time"
import { cn } from "@/shared/lib/utils"

function scenarioLabel(scenario: string | null | undefined) {
  if (!scenario) return null
  return SCENARIO_LABEL[scenario as PredictionScenario] ?? scenario
}

function historyLine(situation: Situation) {
  const history = situation.history
  if (!history || history.episodes365d <= 0) return null
  const parts = [`${history.episodes365d} эпиз. / год`]
  if (history.medianDurationMinutes != null && history.medianDurationMinutes > 0) {
    const hours = history.medianDurationMinutes / 60
    parts.push(hours >= 1 ? `медиана ${hours.toFixed(1)} ч` : `медиана ${Math.round(history.medianDurationMinutes)} мин`)
  }
  return parts.join(" · ")
}

export function SituationRail({
  className,
  situations,
  now,
  onInspect,
  onAcknowledge,
  onCreateAction,
}: {
  className?: string
  situations: Situation[]
  now: number
  onInspect: (situation: Situation) => void
  onAcknowledge: (situation: Situation) => void
  onCreateAction: (situation: Situation) => void
}) {
  if (situations.length === 0) {
    return (
      <div className="border border-border bg-elevated px-5 py-6">
        <p className="text-[13px] font-medium tracking-[0.06em] text-muted-foreground uppercase">Внимание не требуется</p>
        <p className="mt-1 text-[14px] text-muted-foreground">В выбранном окне нет объектов и паттернов, требующих вмешательства.</p>
      </div>
    )
  }

  return (
    <ul className={cn("border border-border bg-elevated", className)}>
      {situations.map((situation) => {
        const scenario = scenarioLabel(situation.scenario)
        const probability =
          situation.incidentProbability ??
          (situation.scoreText !== null && situation.riskScore !== null ? situation.riskScore : null)
        const probabilityText =
          probability === null
            ? situation.scoreText
            : `${Math.round(probability * 100)}%`
        const whyText = situation.recommendation?.hint || situation.primaryReason
        const actions = situation.recommendation?.actions.slice(0, 3) ?? []
        const past = historyLine(situation)

        return (
          <li
            key={situation.id}
            className="grid grid-cols-[3px_1fr] gap-3 border-b border-border-soft last:border-b-0"
          >
            <span
              aria-hidden
              className={cn("self-stretch", situation.severity === "critical" ? "bg-status-critical" : "bg-status-attention")}
            />
            <div className="min-w-0 py-2.5 pr-4">
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <StatusMark status={situation.severity === "critical" ? "critical" : "attention"} className="translate-y-0.5 size-3" />
                <span className={cn("text-[15px] font-semibold", situation.type === "pattern" && "text-vena")}>{situation.title}</span>
                {probabilityText ? (
                  <span className="font-mono text-[13px] tabular-nums">{probabilityText}</span>
                ) : null}
                {situation.delta !== null && situation.delta !== 0 ? (
                  <span
                    className={cn(
                      "font-mono text-[13px] tabular-nums",
                      situation.delta > 0 ? "text-status-attention" : "text-muted-foreground"
                    )}
                  >
                    {situation.delta > 0 ? "↑" : "↓"}
                    {Math.abs(situation.delta) < 1 ? Math.abs(situation.delta).toFixed(3) : Math.abs(Math.round(situation.delta))}
                  </span>
                ) : null}
                {situation.horizon !== null ? (
                  <span className="font-mono text-[12px] text-faint">
                    {situation.horizon >= 24
                      ? `≈ через ${Math.round(situation.horizon / 24)} дн.`
                      : `≈ через ${situation.horizon} ч`}
                  </span>
                ) : null}
                {situation.healthIndex !== null && situation.healthIndex !== undefined ? (
                  <span className="font-mono text-[12px] text-faint tabular-nums">HI {situation.healthIndex}</span>
                ) : null}
                <span className="ml-auto font-mono text-[12px] text-faint tabular-nums">{formatAgo(situation.changedAt, now)}</span>
              </div>

              <div className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-[12px] text-muted-foreground">
                {scenario ? <span>{scenario}</span> : null}
                {situation.location ? <span>{situation.location}</span> : null}
                {(situation.assetCount ?? situation.assetIds.length) > 1 ? (
                  <span className="font-mono tabular-nums">{situation.assetCount ?? situation.assetIds.length} каналов</span>
                ) : situation.assetIds[0] ? (
                  <span className="font-mono tabular-nums">{situation.assetIds[0]}</span>
                ) : null}
              </div>

              <p className="mt-1 text-[13px] text-muted-foreground">
                <span className="text-faint">Почему · </span>
                {whyText}
              </p>
              {situation.recommendation ? (
                <div className="mt-0.5 text-[13px] text-muted-foreground">
                  <p>
                    <span className="text-faint">Что делать · </span>
                    {situation.recommendation.title}
                  </p>
                  {actions.length > 0 ? (
                    <ol className="mt-0.5 list-decimal space-y-0.5 pl-4 text-[12px]">
                      {actions.map((step) => (
                        <li key={step}>{step}</li>
                      ))}
                    </ol>
                  ) : null}
                  {situation.recommendation.note ? (
                    <p className="mt-0.5 text-[11px] text-faint">{situation.recommendation.note}</p>
                  ) : null}
                </div>
              ) : null}
              {past ? (
                <p className="mt-0.5 text-[12px] text-faint">
                  <span>Раньше · </span>
                  {past}
                </p>
              ) : null}

              <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1">
                <button
                  type="button"
                  onClick={() => onInspect(situation)}
                  className="text-[13px] font-medium text-vena underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-ring/60"
                >
                  В дереве
                </button>
                {situation.status === "new" ? (
                  <button
                    type="button"
                    onClick={() => onAcknowledge(situation)}
                    className="text-[13px] text-muted-foreground underline-offset-4 outline-none hover:text-foreground hover:underline focus-visible:ring-2 focus-visible:ring-ring/60"
                  >
                    Принять
                  </button>
                ) : null}
                {situation.status !== "action_created" ? (
                  <button
                    type="button"
                    onClick={() => onCreateAction(situation)}
                    className="text-[13px] text-muted-foreground underline-offset-4 outline-none hover:text-foreground hover:underline focus-visible:ring-2 focus-visible:ring-ring/60"
                  >
                    Создать работу
                  </button>
                ) : (
                  <span className="text-[12px] tracking-[0.04em] text-faint uppercase">работа создана</span>
                )}
                {situation.status === "acknowledged" ? (
                  <span className="text-[12px] tracking-[0.04em] text-faint uppercase">принято</span>
                ) : null}
              </div>
            </div>
          </li>
        )
      })}
    </ul>
  )
}
