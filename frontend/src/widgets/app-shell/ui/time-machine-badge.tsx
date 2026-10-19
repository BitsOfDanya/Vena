"use client"

import { History } from "lucide-react"

import { replayBadgeText, useReplayState } from "@/entities/system"
import { Badge } from "@/shared/ui/badge"

export function TimeMachineBadge() {
  const replay = useReplayState()
  const text = replayBadgeText(replay.data)
  if (!text) return null
  return (
    <Badge variant="outline" role="status" className="mr-1 hidden border-status-attention/60 text-status-attention sm:inline-flex">
      <History data-icon="inline-start" aria-hidden />
      <span className="font-mono tabular-nums">{text}</span>
    </Badge>
  )
}
