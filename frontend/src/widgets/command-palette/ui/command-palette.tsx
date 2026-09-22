"use client"

import { Activity, BellRing, LayoutDashboard, ListChecks, Network, Plug, SlidersHorizontal, Waves } from "lucide-react"
import { useRouter } from "next/navigation"
import * as React from "react"

import { StatusMark, TYPE_LABEL, formatScore, useAssetSearch, useReplayEpisodes } from "@/entities/infrastructure"
import { STATUS_LABEL as ACTION_STATUS_LABEL, useActions } from "@/entities/maintenance"
import { useWorkspace } from "@/features/workspace"
import { formatFullDay } from "@/shared/lib/time"
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
  CommandShortcut,
} from "@/shared/ui/command"

const COMMANDS = [
  { href: "/actions", label: "Create action", icon: ListChecks },
  { href: "/settings/notifications", label: "Notification settings", icon: BellRing },
  { href: "/settings/integrations", label: "Integrations", icon: Plug },
  { href: "/settings", label: "Settings", icon: SlidersHorizontal },
] as const

const NAVIGATION = [
  { href: "/pulse", label: "Open Pulse", icon: Activity },
  { href: "/network", label: "Open Network", icon: Network },
  { href: "/timeline", label: "Open Timeline", icon: Waves },
  { href: "/actions", label: "Open Actions", icon: ListChecks },
  { href: "/dashboard", label: "Open Dashboard", icon: LayoutDashboard },
] as const

export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const router = useRouter()
  const { now, horizon, selectAsset, startReplay } = useWorkspace()
  const [query, setQuery] = React.useState("")
  const search = useAssetSearch(query, now, horizon)
  const episodes = useReplayEpisodes()
  const allActions = useActions()
  const needle = query.trim().toLowerCase()
  const navigation = NAVIGATION.filter((item) => item.label.toLowerCase().includes(needle))
  const commands = COMMANDS.filter((item) => item.label.toLowerCase().includes(needle))
  const actions = (allActions.data ?? []).filter(
    (action) =>
      needle.length > 0 &&
      (action.id.toLowerCase().includes(needle) ||
        action.assetId.toLowerCase().includes(needle) ||
        action.reason.toLowerCase().includes(needle))
  )
  const episode = episodes.data?.[0]
  const showReplay = episode && (needle === "" || "запись replay".includes(needle) || episode.assetId.toLowerCase().includes(needle))

  React.useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault()
        onOpenChange(!open)
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [open, onOpenChange])

  function close() {
    onOpenChange(false)
    setQuery("")
  }

  return (
    <CommandDialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next)
        if (!next) setQuery("")
      }}
      title="Search"
      description="Найдите объект, ID канала или откройте раздел"
      className="max-w-lg"
    >
      <Command shouldFilter={false} className="rounded-none">
        <CommandInput value={query} onValueChange={setQuery} placeholder="Объект, ID канала или раздел" />
        <CommandList className="max-h-80">
          <CommandEmpty>Ничего не найдено по этому запросу.</CommandEmpty>
          {navigation.length > 0 ? (
            <CommandGroup heading="Workspaces">
              {navigation.map(({ href, label, icon: Icon }) => (
                <CommandItem
                  key={href}
                  value={label}
                  onSelect={() => {
                    router.push(href)
                    close()
                  }}
                >
                  <Icon aria-hidden /> {label}
                </CommandItem>
              ))}
            </CommandGroup>
          ) : null}
          {showReplay ? (
            <CommandGroup heading="Replay">
              <CommandItem
                value="replay"
                onSelect={() => {
                  startReplay(episode)
                  router.push("/timeline")
                  close()
                }}
              >
                <Waves aria-hidden /> Replay {formatFullDay(episode.start)} · {episode.assetId}
                <CommandShortcut>{episode.label}</CommandShortcut>
              </CommandItem>
            </CommandGroup>
          ) : null}
          {commands.length > 0 ? (
            <CommandGroup heading="Commands">
              {commands.map(({ href, label, icon: Icon }) => (
                <CommandItem
                  key={label}
                  value={label}
                  onSelect={() => {
                    router.push(href)
                    close()
                  }}
                >
                  <Icon aria-hidden /> {label}
                </CommandItem>
              ))}
            </CommandGroup>
          ) : null}
          {actions.length > 0 ? (
            <CommandGroup heading="Actions">
              {actions.slice(0, 6).map((action) => (
                <CommandItem
                  key={action.id}
                  value={action.id}
                  onSelect={() => {
                    router.push("/actions")
                    close()
                  }}
                >
                  <ListChecks aria-hidden />
                  <span className="font-mono">{action.id}</span>
                  <span className="text-muted-foreground">{action.assetId}</span>
                  <CommandShortcut>{ACTION_STATUS_LABEL[action.status]}</CommandShortcut>
                </CommandItem>
              ))}
            </CommandGroup>
          ) : null}
          {navigation.length > 0 || showReplay || commands.length > 0 ? <CommandSeparator /> : null}
          <CommandGroup heading={needle ? "Assets" : "Highest risk assets"}>
            {(search.data ?? []).map((asset) => (
              <CommandItem
                key={asset.id}
                value={asset.id}
                onSelect={() => {
                  selectAsset(asset.id)
                  router.push("/network")
                  close()
                }}
              >
                <StatusMark status={asset.status} />
                <span className="font-mono">{asset.id}</span>
                <span className="text-muted-foreground">{TYPE_LABEL[asset.type]}</span>
                <span className="ml-auto font-mono text-xs text-muted-foreground tabular-nums">
                  CH {asset.channelId} · {formatScore(asset.riskScore, asset.scoreType)}
                </span>
              </CommandItem>
            ))}
          </CommandGroup>
        </CommandList>
      </Command>
    </CommandDialog>
  )
}
