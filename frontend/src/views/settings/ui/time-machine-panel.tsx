"use client"

import * as React from "react"

import {
  REPLAY_SPEEDS,
  REPLAY_STATUS_LABEL,
  dayStart,
  formatDataClock,
  formatJournalDate,
  journalDay,
  scenarioOption,
  simulationText,
  useReplayScenarios,
  useReplayState,
  useStartScenarioReplay,
  useStartWeekReplay,
  useStopReplay,
} from "@/entities/system"
import { useAuthSession } from "@/features/auth"
import { ApiError } from "@/shared/api/http"
import { formatCount } from "@/shared/lib/plural"
import { Badge } from "@/shared/ui/badge"
import { Button } from "@/shared/ui/button"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/ui/card"
import { Checkbox } from "@/shared/ui/checkbox"
import { Field, FieldLabel } from "@/shared/ui/field"
import { Input } from "@/shared/ui/input"
import { NativeSelect, NativeSelectOption } from "@/shared/ui/native-select"

import { SettingsSection } from "./settings-shell"

function errorText(error: unknown) {
  return error instanceof ApiError ? error.detail : "Не удалось выполнить операцию. Попробуйте снова."
}

export function TimeMachinePanel() {
  const { me } = useAuthSession()
  const admin = me?.role === "admin"
  const replay = useReplayState()
  const catalog = useReplayScenarios(admin)
  const startWeek = useStartWeekReplay()
  const startScenario = useStartScenarioReplay()
  const stop = useStopReplay()
  const [start, setStart] = React.useState("2026-06-03")
  const [end, setEnd] = React.useState("2026-06-06")
  const [speed, setSpeed] = React.useState<number>(REPLAY_SPEEDS[0].value)
  const [simulate, setSimulate] = React.useState(true)
  const [scenarioId, setScenarioId] = React.useState("")
  const [error, setError] = React.useState<string | null>(null)
  const handlers = { onSuccess: () => setError(null), onError: (failure: unknown) => setError(errorText(failure)) }

  if (!admin) return null

  const state = replay.data
  const active = state?.active ?? false
  const busy = startWeek.isPending || startScenario.isPending || stop.isPending
  const items = catalog.data?.items ?? []
  const selected = scenarioId || items[0]?.id || ""
  const clock = formatDataClock(state?.clock)
  const running = active && state?.mode === "week"
  const range =
    state?.journal_from && state.journal_to
      ? `Журнал доступен с ${formatJournalDate(state.journal_from)} по ${formatJournalDate(state.journal_to)}. Перед стартом ML пересчитывает историю до начала периода — это занимает несколько минут.`
      : "Каталог журнала на сервере не найден."

  return (
    <SettingsSection
      title="Машина времени"
      description="Реальный журнал проходит через обычный поток СМВУ: прогнозы загораются, события приходят позже, решения попадают в «Эффект»."
    >
      <Card size="sm">
        <CardHeader>
          <CardTitle>Воспроизведение журнала</CardTitle>
          <CardDescription>{range}</CardDescription>
          <CardAction>
            <Badge variant={state?.state === "failed" ? "destructive" : active ? "default" : "outline"}>
              {state ? REPLAY_STATUS_LABEL[state.state] : "Нет данных"}
            </Badge>
          </CardAction>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <Field>
              <FieldLabel htmlFor="replay-start">Начало</FieldLabel>
              <Input
                id="replay-start"
                type="date"
                value={(running && journalDay(state?.start)) || start}
                min={journalDay(state?.journal_from)}
                max={journalDay(state?.journal_to)}
                disabled={busy || active}
                onChange={(event) => setStart(event.target.value)}
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="replay-end">Конец</FieldLabel>
              <Input
                id="replay-end"
                type="date"
                value={(running && journalDay(state?.end)) || end}
                min={start}
                disabled={busy || active}
                onChange={(event) => setEnd(event.target.value)}
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="replay-speed">Скорость</FieldLabel>
              <NativeSelect
                id="replay-speed"
                className="w-full"
                value={speed}
                disabled={busy || active}
                onChange={(event) => setSpeed(Number(event.target.value))}
              >
                {REPLAY_SPEEDS.map((option) => (
                  <NativeSelectOption key={option.value} value={option.value}>
                    {option.label}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </Field>
          </div>
          <Field orientation="horizontal">
            <Checkbox
              id="replay-simulate"
              checked={simulate}
              disabled={busy || active}
              onCheckedChange={(value) => setSimulate(value === true)}
            />
            <FieldLabel htmlFor="replay-simulate">Симулировать решения диспетчера</FieldLabel>
          </Field>
          <div className="flex flex-wrap gap-2">
            <Button
              disabled={busy || active || !start || !end}
              onClick={() =>
                startWeek.mutate({ start: dayStart(start), end: dayStart(end), speed, simulateDispatcher: simulate }, handlers)
              }
            >
              Запустить
            </Button>
            <Button variant="outline" disabled={busy || !active || state?.state === "stopping"} onClick={() => stop.mutate(false, handlers)}>
              Остановить
            </Button>
            <Button variant="outline" disabled={busy || (!active && (state?.live ?? true))} onClick={() => stop.mutate(true, handlers)}>
              Вернуть живой режим
            </Button>
          </div>
          {state && state.state !== "idle" ? (
            <dl className="grid gap-x-6 gap-y-2 border-t border-border pt-3 text-[13px] sm:grid-cols-2">
              <div>
                <dt className="text-[12px] text-faint">Данные на</dt>
                <dd className="font-mono tabular-nums">{clock ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-[12px] text-faint">Прогноз рассчитан на</dt>
                <dd className="font-mono tabular-nums">{formatDataClock(state.ml_clock) ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-[12px] text-faint">Отправлено событий · пакетов</dt>
                <dd className="font-mono tabular-nums">
                  {formatCount(state.sent_events)} · {formatCount(state.batches)}
                </dd>
              </div>
              {state.mode === "week" && state.simulate_dispatcher ? (
                <div className="sm:col-span-2">
                  <dt className="text-[12px] text-faint">Симуляция диспетчера</dt>
                  <dd>{simulationText(state.simulation)}</dd>
                </div>
              ) : null}
              {state.scenario ? (
                <div className="sm:col-span-2">
                  <dt className="text-[12px] text-faint">Сценарий</dt>
                  <dd>
                    {state.scenario.label}, объект {state.scenario.object}
                    {state.scenario.stage ? `, этап «${state.scenario.stage}» (${state.scenario.stage_index} из ${state.scenario.stages})` : ""}
                  </dd>
                </div>
              ) : null}
            </dl>
          ) : null}
          {state?.detail ? <p className="text-[13px] text-muted-foreground">{state.detail}</p> : null}
        </CardContent>
      </Card>

      <Card size="sm">
        <CardHeader>
          <CardTitle>Учебный сценарий</CardTitle>
          <CardDescription>
            Реальный инцидент из журнала повторяется в три этапа: предвестники, развитие, инцидент. История ML не сбрасывается.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {items.length ? (
            <div className="flex flex-col gap-2 sm:flex-row">
              <NativeSelect
                aria-label="Сценарий"
                className="w-full sm:flex-1"
                value={selected}
                disabled={busy || active}
                onChange={(event) => setScenarioId(event.target.value)}
              >
                {items.map((item) => (
                  <NativeSelectOption key={item.id} value={item.id}>
                    {scenarioOption(item)}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
              <Button disabled={busy || active || !selected} onClick={() => startScenario.mutate(selected, handlers)}>
                Запустить
              </Button>
            </div>
          ) : (
            <p className="text-[13px] text-muted-foreground">
              {catalog.isPending ? "Загрузка каталога…" : "Каталог сценариев ещё не сформирован."}
            </p>
          )}
          {catalog.data?.note ? <p className="text-[12px] text-faint">{catalog.data.note}</p> : null}
        </CardContent>
      </Card>
      {error ? (
        <p role="alert" className="text-[13px] text-status-critical">
          {error}
        </p>
      ) : null}
    </SettingsSection>
  )
}
