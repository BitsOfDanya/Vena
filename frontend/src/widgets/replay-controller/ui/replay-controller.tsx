"use client"

import { Pause, Play, RotateCcw, X } from "lucide-react"

import { REPLAY_SPEEDS, useWorkspace, type ReplaySpeed } from "@/features/workspace"
import { formatClockSeconds, formatFullDay } from "@/shared/lib/time"
import { cn } from "@/shared/lib/utils"
import { Slider } from "@/shared/ui/slider"

export function ReplayDock({ className }: { className?: string }) {
  const { replay, stopReplay, seekReplay, toggleReplay, setReplaySpeed } = useWorkspace()
  if (!replay) return null
  const { episode, time, playing, speed } = replay
  const finished = time >= episode.end

  return (
    <section
      aria-label="Управление записью"
      className={cn("flex h-8 items-center gap-3 border border-status-attention/45 bg-status-attention/10 pr-1 pl-2.5", className)}
    >
      <span className="flex items-baseline gap-2 whitespace-nowrap text-status-attention">
        <span className="text-[11px] font-semibold tracking-[0.12em] uppercase">Replay</span>
        <span className="font-mono text-[11px] tabular-nums">
          {formatFullDay(time)} · {formatClockSeconds(time)}
        </span>
      </span>
      <button
        type="button"
        onClick={toggleReplay}
        aria-label={playing ? "Пауза" : finished ? "Начать заново" : "Воспроизвести"}
        className="flex size-6 items-center justify-center text-foreground outline-none hover:text-vena focus-visible:ring-2 focus-visible:ring-ring/60"
      >
        {playing ? <Pause className="size-3.5" /> : finished ? <RotateCcw className="size-3.5" /> : <Play className="size-3.5" />}
      </button>
      <div role="radiogroup" aria-label="Скорость записи" className="flex items-center gap-1">
        {REPLAY_SPEEDS.map((value: ReplaySpeed) => (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={value === speed}
            onClick={() => setReplaySpeed(value)}
            className={cn(
              "font-mono text-[11px] tabular-nums outline-none focus-visible:ring-2 focus-visible:ring-ring/60",
              value === speed ? "text-foreground underline underline-offset-4" : "text-faint hover:text-muted-foreground"
            )}
          >
            {value}×
          </button>
        ))}
      </div>
      <Slider
        aria-label="Позиция записи"
        className="w-28 xl:w-40"
        min={episode.start}
        max={episode.end}
        step={60_000}
        value={[time]}
        onValueChange={([next]) => seekReplay(next)}
      />
      <button
        type="button"
        onClick={stopReplay}
        aria-label="Выйти из записи"
        className="flex size-6 items-center justify-center text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/60"
      >
        <X className="size-3.5" />
      </button>
    </section>
  )
}
