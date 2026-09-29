import { cn } from "@/shared/lib/utils"

import type { EventSeverity, EventType } from "../model/types"

export type GlyphKind = "event" | "transition" | "attention" | "critical" | "sustained" | "cluster"

export const EVENT_GLYPH_LEGEND: { kind: GlyphKind; label: string }[] = [
  { kind: "event", label: "Событие" },
  { kind: "transition", label: "Переход" },
  { kind: "attention", label: "Внимание" },
  { kind: "critical", label: "Критично" },
  { kind: "sustained", label: "Устойчиво" },
  { kind: "cluster", label: "Кластер" },
]

export function glyphKind(event: { severity: EventSeverity; type: EventType }): GlyphKind {
  if (event.severity === "critical") return "critical"
  if (event.severity === "warning") return "attention"
  return event.type === "transition" || event.type === "state_change" ? "transition" : "event"
}

export function GlyphShape({ kind, x = 0, y = 0, size = 8 }: { kind: GlyphKind; x?: number; y?: number; size?: number }) {
  const half = size / 2
  switch (kind) {
    case "event":
      return <circle cx={x} cy={y} r={1.5} className="fill-faint" />
    case "transition":
      return <path d={`M${x} ${y - half} V${y + half}`} className="stroke-muted-foreground" strokeWidth={1.4} fill="none" />
    case "attention":
      return (
        <path
          d={`M${x} ${y - half} L${x + half} ${y} L${x} ${y + half} L${x - half} ${y} Z`}
          className="fill-background stroke-status-attention"
          strokeWidth={1.4}
          strokeLinejoin="miter"
        />
      )
    case "critical":
      return <path d={`M${x} ${y - half - 0.8} L${x + half + 0.8} ${y} L${x} ${y + half + 0.8} L${x - half - 0.8} ${y} Z`} className="fill-status-critical" />
    case "sustained":
      return <path d={`M${x - half - 2} ${y} H${x + half + 2}`} className="stroke-status-attention" strokeWidth={3} fill="none" />
    case "cluster":
      return (
        <g className="stroke-muted-foreground" strokeWidth={1} fill="none">
          <rect x={x - half} y={y - half} width={size} height={size} className="fill-elevated" />
          <path d={`M${x - half} ${y + half} L${x + half} ${y - half} M${x - half} ${y} L${x} ${y - half} M${x} ${y + half} L${x + half} ${y}`} />
        </g>
      )
  }
}

export function EventGlyph({ kind, className }: { kind: GlyphKind; className?: string }) {
  return (
    <svg aria-hidden viewBox="0 0 12 12" className={cn("size-3 shrink-0", className)}>
      <GlyphShape kind={kind} x={6} y={6} size={7} />
    </svg>
  )
}
