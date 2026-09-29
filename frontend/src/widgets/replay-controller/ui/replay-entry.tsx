"use client"

import { History } from "lucide-react"

import { useReplayEpisodes } from "@/entities/infrastructure"
import { useWorkspace } from "@/features/workspace"
import { Button } from "@/shared/ui/button"

import { ReplayDock } from "./replay-controller"

export function ReplayEntry({ className }: { className?: string }) {
  const episodes = useReplayEpisodes()
  const { mode, startReplay } = useWorkspace()
  const episode = episodes.data?.[0]

  if (mode === "replay") return <ReplayDock className={className} />

  return (
    <Button className={className} variant="outline" size="sm" disabled={!episode} onClick={() => episode && startReplay(episode)}>
      <History data-icon="inline-start" /> Запись
    </Button>
  )
}
