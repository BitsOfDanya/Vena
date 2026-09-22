import { cn } from "@/shared/lib/utils"

import { LEVEL_LABEL, STATUS_LABEL } from "../lib/risk"
import type { AssetStatus, RiskLevel } from "../model/types"

export const STATUS_TEXT: Record<AssetStatus, string> = {
  normal: "text-status-normal",
  attention: "text-status-attention",
  critical: "text-status-critical",
  offline: "text-status-offline",
}

export function StatusMark({ status, className }: { status: AssetStatus; className?: string }) {
  return (
    <svg aria-hidden viewBox="0 0 10 10" className={cn("size-2.5 shrink-0", STATUS_TEXT[status], className)}>
      {status === "critical" ? <path d="M5 .6 9.4 5 5 9.4.6 5Z" fill="currentColor" /> : null}
      {status === "attention" ? <path d="M5 1 9 5 5 9 1 5Z" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="miter" /> : null}
      {status === "normal" ? <circle cx="5" cy="5" r="3.6" fill="none" stroke="currentColor" strokeWidth="1.3" /> : null}
      {status === "offline" ? (
        <circle cx="5" cy="5" r="3.6" fill="none" stroke="currentColor" strokeWidth="1.3" strokeDasharray="1.6 1.4" />
      ) : null}
    </svg>
  )
}

export function StatusLabel({ status, className }: { status: AssetStatus; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-[0.06em]", STATUS_TEXT[status], className)}>
      <StatusMark status={status} />
      {STATUS_LABEL[status]}
    </span>
  )
}

const LEVEL_STATUS: Record<RiskLevel, AssetStatus> = { low: "normal", medium: "attention", high: "critical" }

export function RiskLevelLabel({ level, className }: { level: RiskLevel; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-[0.06em]", STATUS_TEXT[LEVEL_STATUS[level]], className)}>
      <StatusMark status={LEVEL_STATUS[level]} />
      {LEVEL_LABEL[level]}
    </span>
  )
}
