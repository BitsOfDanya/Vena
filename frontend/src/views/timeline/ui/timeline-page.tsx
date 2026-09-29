"use client"

import { Plus, Search, X } from "lucide-react"
import * as React from "react"

import {
  StatusMark,
  TYPE_LABEL,
  formatScore,
  useAssetSearch,
  useAssets,
  useTemporalBundles,
  type Asset,
} from "@/entities/infrastructure"
import { OPEN_STATUSES, STATUS_LABEL as ACTION_STATUS_LABEL, useActions } from "@/entities/maintenance"
import { CreateActionSheet } from "@/features/create-action"
import { useWorkspace } from "@/features/workspace"
import { useIsMobile } from "@/shared/lib/hooks/use-mobile"
import { cn } from "@/shared/lib/utils"
import { Button } from "@/shared/ui/button"
import { Input } from "@/shared/ui/input"
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/shared/ui/command"
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/ui/popover"
import { Segmented } from "@/shared/ui/segmented"
import { LoadingBar, StateMessage } from "@/shared/ui/state-message"
import { ReplayEntry } from "@/widgets/replay-controller"
import { DEFAULT_LAYERS, TemporalCanvas, ZOOM_STEPS, type Layers } from "@/widgets/temporal-canvas"

const MAX_ASSETS = 5

const LAYER_LABELS: { key: keyof Layers; label: string }[] = [
  { key: "state", label: "Состояние" },
  { key: "events", label: "События" },
  { key: "alarms", label: "Тревоги" },
  { key: "failures", label: "Отказы" },
  { key: "risk", label: "Риск" },
]

function AssetPicker({ chosen, onPick }: { chosen: string[]; onPick: (id: string) => void }) {
  const { now, horizon } = useWorkspace()
  const [open, setOpen] = React.useState(false)
  const [query, setQuery] = React.useState("")
  const results = useAssetSearch(query, now, horizon)
  const disabled = chosen.length >= MAX_ASSETS

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" disabled={disabled} title={disabled ? `Можно сравнивать до ${MAX_ASSETS} объектов` : undefined}>
          <Plus data-icon="inline-start" /> Добавить объект
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-72 p-0">
        <Command shouldFilter={false}>
          <CommandInput placeholder="ID объекта, канал, группа" value={query} onValueChange={setQuery} />
          <CommandList>
            <CommandEmpty>Объекты не найдены.</CommandEmpty>
            <CommandGroup>
              {(results.data ?? [])
                .filter((asset) => !chosen.includes(asset.id))
                .map((asset) => (
                  <CommandItem
                    key={asset.id}
                    value={asset.id}
                    onSelect={() => {
                      onPick(asset.id)
                      setOpen(false)
                      setQuery("")
                    }}
                  >
                    <StatusMark status={asset.status} />
                    <span className="font-mono">{asset.id}</span>
                    <span className="ml-auto font-mono text-xs text-muted-foreground tabular-nums">{formatScore(asset.riskScore, asset.scoreType)}</span>
                  </CommandItem>
                ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}

const RECENT_KEY = "vena.timeline.recent.v1"

function readRecent(): string[] {
  if (typeof window === "undefined") return []
  try {
    const raw = window.localStorage.getItem(RECENT_KEY)
    return raw ? (JSON.parse(raw) as string[]) : []
  } catch {
    return []
  }
}

function rememberRecent(id: string) {
  if (typeof window === "undefined") return
  try {
    const next = [id, ...readRecent().filter((item) => item !== id)].slice(0, 5)
    window.localStorage.setItem(RECENT_KEY, JSON.stringify(next))
  } catch {
    return
  }
}

function AssetRows({ assets, onPick }: { assets: Asset[]; onPick: (id: string) => void }) {
  return (
    <ul className="divide-y divide-border-soft border-t border-border-soft">
      {assets.map((asset) => (
        <li key={asset.id}>
          <button
            type="button"
            onClick={() => onPick(asset.id)}
            className="flex h-9 w-full items-center gap-4 text-left outline-none hover:bg-elevated focus-visible:ring-2 focus-visible:ring-ring/60"
          >
            <StatusMark status={asset.status} className="ml-1 size-3" />
            <span className="font-mono text-[14px]">{asset.id}</span>
            <span className="text-[13px] text-muted-foreground">{TYPE_LABEL[asset.type]}</span>
            <span className="ml-auto flex items-center gap-3 pr-2">
              <span aria-hidden className="h-1 w-24 bg-grid">
                <span
                  className={cn(
                    "block h-full",
                    asset.status === "critical" ? "bg-status-critical" : asset.status === "attention" ? "bg-status-attention" : "bg-status-normal"
                  )}
                  style={{ width: `${Math.round(asset.riskScore)}%` }}
                />
              </span>
              <span className="font-mono text-[13px] tabular-nums">{formatScore(asset.riskScore, asset.scoreType)}</span>
            </span>
          </button>
        </li>
      ))}
    </ul>
  )
}

function Suggestions({ onPick }: { onPick: (id: string) => void }) {
  const { now, horizon } = useWorkspace()
  const [query, setQuery] = React.useState("")
  const assets = useAssets(now, horizon)
  const search = useAssetSearch(query, now, horizon)
  const all = assets.data ?? []
  const recentIds = React.useMemo(() => readRecent(), [])
  const recent = recentIds.map((id) => all.find((asset) => asset.id === id)).filter((asset): asset is Asset => Boolean(asset))
  const top = all
    .filter((asset) => asset.status === "critical" || asset.status === "attention")
    .sort((left, right) => right.riskScore - left.riskScore)
    .slice(0, 6)
  const changed = [...all]
    .filter((asset) => asset.lastEventAt !== null)
    .sort((left, right) => (right.lastEventAt ?? 0) - (left.lastEventAt ?? 0))
    .slice(0, 5)
  const needle = query.trim()

  return (
    <div className="flex h-full flex-col items-start gap-6 overflow-y-auto px-3 pt-6 pb-8">
      <div className="w-full max-w-xl space-y-3">
        <div className="space-y-1.5">
          <p className="text-[15px] font-medium">Выберите объект для анализа.</p>
          <p className="text-[14px] text-muted-foreground">
            Выберите объект, чтобы увидеть историю состояния и прогноз вокруг текущего момента.
          </p>
        </div>
        <div className="relative">
          <Search aria-hidden className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="ID объекта, канал, группа"
            aria-label="Поиск объектов"
            className="h-9 pl-9 font-mono text-[13px]"
          />
        </div>
      </div>

      {needle.length > 0 ? (
        <div className="w-full max-w-xl">
          <p className="mb-1 text-[12px] font-medium tracking-[0.1em] text-faint uppercase">Результаты поиска</p>
          {(search.data ?? []).length === 0 ? (
            <p className="text-[13px] text-muted-foreground">Объекты не найдены.</p>
          ) : (
            <AssetRows assets={search.data ?? []} onPick={onPick} />
          )}
        </div>
      ) : (
        <>
          {recent.length > 0 ? (
            <div className="w-full max-w-xl">
              <p className="mb-1 text-[12px] font-medium tracking-[0.1em] text-faint uppercase">Недавно просмотренные</p>
              <AssetRows assets={recent} onPick={onPick} />
            </div>
          ) : null}
          {top.length > 0 ? (
            <div className="w-full max-w-xl">
              <p className="mb-1 text-[12px] font-medium tracking-[0.1em] text-faint uppercase">Наивысший риск сейчас</p>
              <AssetRows assets={top} onPick={onPick} />
            </div>
          ) : null}
          {changed.length > 0 ? (
            <div className="w-full max-w-xl">
              <p className="mb-1 text-[12px] font-medium tracking-[0.1em] text-faint uppercase">Недавно изменившиеся</p>
              <AssetRows assets={changed} onPick={onPick} />
            </div>
          ) : null}
        </>
      )}
    </div>
  )
}

export function TimelinePage() {
  const isMobile = useIsMobile()
  const { now, horizon, mode, selectedAssetId, selectAsset, compareIds, setCompare } = useWorkspace()
  const [halfSpan, setHalfSpan] = React.useState(24)
  const [layers, setLayers] = React.useState<Layers>(DEFAULT_LAYERS)
  const ids = compareIds.length > 0 ? compareIds : selectedAssetId ? [selectedAssetId] : []
  const temporal = useTemporalBundles(ids, now, halfSpan, horizon)
  const assets = useAssets(now, horizon)
  const actions = useActions()
  const [acknowledged, setAcknowledged] = React.useState<string[]>([])
  const [sheetOpen, setSheetOpen] = React.useState(false)
  const primaryId = selectedAssetId ?? ids[0] ?? null
  const primary = (assets.data ?? []).find((asset) => asset.id === primaryId) ?? null
  const primaryAction = (actions.data ?? []).find(
    (action) => action.assetId === primaryId && OPEN_STATUSES.includes(action.status)
  )

  const add = (id: string) => {
    rememberRecent(id)
    setCompare([...ids, id].slice(-MAX_ASSETS))
  }
  const remove = (id: string) => {
    const next = ids.filter((item) => item !== id)
    setCompare(next)
    if (selectedAssetId === id) selectAsset(next[0] ?? null)
  }

  if (isMobile) {
    return (
      <StateMessage
        title="Нужен экран пошире"
        description="Хронология рассчитана на настольные и диспетчерские экраны. На этом устройстве используйте «Пульс» и «Работы»."
      />
    )
  }

  return (
    <div className="flex size-full flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-x-6 gap-y-3 px-6 pt-1 pb-3">
        <div className="flex items-baseline gap-3">
          <h1 className="text-[22px] font-semibold tracking-[-0.01em]">Хронология</h1>
          <span className="font-mono text-[12px] text-faint">{mode === "replay" ? "запись" : "прошлое · сейчас · прогноз"}</span>
        </div>
        <ul aria-label="Объекты на хронологии" className="flex flex-wrap items-center gap-1.5">
          {ids.map((id) => (
            <li key={id} className="flex h-7 items-center gap-1.5 border border-border bg-surface pr-1 pl-2.5">
              <span className="font-mono text-xs">{id}</span>
              <button
                type="button"
                aria-label={`Убрать ${id}`}
                onClick={() => remove(id)}
                className="flex size-5 items-center justify-center text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/60"
              >
                <X className="size-3.5" aria-hidden />
              </button>
            </li>
          ))}
          <li>
            <AssetPicker chosen={ids} onPick={add} />
          </li>
        </ul>
        <div className="ml-auto flex flex-wrap items-center gap-3">
          <div role="group" aria-label="Слои" className="flex items-center gap-1">
            {LAYER_LABELS.map((layer) => (
              <button
                key={layer.key}
                type="button"
                aria-pressed={layers[layer.key]}
                onClick={() => setLayers((current) => ({ ...current, [layer.key]: !current[layer.key] }))}
                className={cn(
                  "h-7 border px-2 text-[11px] font-medium tracking-[0.06em] uppercase outline-none focus-visible:ring-2 focus-visible:ring-ring/60",
                  layers[layer.key] ? "border-foreground/40 bg-elevated text-foreground" : "border-transparent text-faint hover:text-foreground"
                )}
              >
                {layer.label}
              </button>
            ))}
          </div>
          <Segmented label="Окно времени" value={halfSpan} onChange={setHalfSpan} options={ZOOM_STEPS.map((value) => ({ value, label: `±${value}h` }))} />
          <ReplayEntry />
        </div>
      </div>
      {primary ? (
        <div className="mx-3 mb-2 flex shrink-0 flex-wrap items-center gap-x-6 gap-y-2 border border-border bg-elevated px-4 py-2.5">
          <span className="flex items-baseline gap-2.5">
            <StatusMark status={primary.status} className="translate-y-0.5 size-3" />
            <span className="font-mono text-[16px]">{primary.id}</span>
            <span className="text-[13px] text-muted-foreground">{TYPE_LABEL[primary.type]}</span>
          </span>
          <span className="text-[13px]">
            <span className="text-faint">риск </span>
            <span className="font-mono tabular-nums">{formatScore(primary.riskScore, primary.scoreType)}</span>
          </span>
          <span className="text-[13px]">
            <span className="text-faint">прогноз </span>
            <span className="font-mono tabular-nums">{primary.forecastHorizon}h</span>
          </span>
          <span className="text-[13px]">
            <span className="text-faint">открытая работа </span>
            {primaryAction ? (
              <span className="text-vena">
                {primaryAction.id} · {ACTION_STATUS_LABEL[primaryAction.status]}
              </span>
            ) : (
              <span className="text-muted-foreground">—</span>
            )}
          </span>
          <span className="ml-auto flex items-center gap-3">
            {acknowledged.includes(primary.id) ? (
              <span className="text-[12px] tracking-[0.06em] text-faint uppercase">Принято</span>
            ) : (
              <Button variant="outline" size="sm" onClick={() => setAcknowledged((current) => [...current, primary.id])}>
                Подтвердить риск
              </Button>
            )}
            <Button size="sm" onClick={() => setSheetOpen(true)} disabled={Boolean(primaryAction)}>
              Создать работу
            </Button>
          </span>
        </div>
      ) : null}
      <div className="min-h-0 flex-1 overflow-y-auto px-3">
        {ids.length === 0 ? (
          <Suggestions
            onPick={(id) => {
              rememberRecent(id)
              selectAsset(id)
              setCompare([id])
            }}
          />
        ) : temporal.pending && temporal.bundles.length === 0 ? (
          <LoadingBar />
        ) : temporal.error && temporal.bundles.length === 0 ? (
          <StateMessage title="Хронология недоступна" description="Не удалось загрузить историю и прогноз по выбранным объектам." />
        ) : (
          <TemporalCanvas
            now={now}
            halfSpanHours={halfSpan}
            bundles={temporal.bundles}
            layers={layers}
            onZoom={setHalfSpan}
            onSelectAsset={(id) => selectAsset(id)}
            selectedAssetId={selectedAssetId}
          />
        )}
      </div>
      <CreateActionSheet
        open={sheetOpen}
        onOpenChange={setSheetOpen}
        draft={primary ? { assetId: primary.id, priority: primary.status === "critical" ? "high" : "medium" } : {}}
      />
    </div>
  )
}
