"use client"

import { PanelLeftClose, PanelLeftOpen } from "lucide-react"
import Link from "next/link"
import { usePathname } from "next/navigation"

import { NAV_GROUPS, isActive } from "@/shared/config/routes"
import { cn } from "@/shared/lib/utils"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/shared/ui/tooltip"
import { VenaLogo } from "@/shared/ui/vena-mark"

export function NavList({ collapsed = false, onNavigate }: { collapsed?: boolean; onNavigate?: () => void }) {
  const pathname = usePathname()
  return (
    <nav aria-label="Основная навигация" className="flex flex-col gap-5">
      {NAV_GROUPS.map((group) => (
        <div key={group.title} className="flex flex-col gap-0.5">
          {collapsed ? (
            <span aria-hidden className="mx-auto mb-1 h-px w-6 bg-border" />
          ) : (
            <span className="mb-1 px-3 text-[11px] font-medium tracking-[0.06em] text-faint uppercase">{group.title}</span>
          )}
          {group.items.map((item) => {
            const active = isActive(pathname, item.href)
            const Icon = item.icon
            const link = (
              <Link
                key={item.href}
                href={item.href}
                onClick={onNavigate}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "group relative flex h-9 items-center gap-3 rounded-md px-3 text-[14px] outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring/60",
                  collapsed && "justify-center px-0",
                  active
                    ? "bg-accent font-medium text-foreground"
                    : "text-muted-foreground hover:bg-accent/60 hover:text-foreground"
                )}
              >
                {active ? <span aria-hidden className="absolute inset-y-0 left-0 w-[3px] bg-vena" /> : null}
                <Icon className={cn("size-[18px] shrink-0", active ? "text-vena" : "")} aria-hidden />
                {collapsed ? <span className="sr-only">{item.label}</span> : <span className="truncate">{item.label}</span>}
              </Link>
            )
            return collapsed ? (
              <Tooltip key={item.href}>
                <TooltipTrigger asChild>{link}</TooltipTrigger>
                <TooltipContent side="right" className="flex-col items-start gap-0.5">
                  <span className="font-medium">{item.label}</span>
                  <span className="opacity-70">{item.hint}</span>
                </TooltipContent>
              </Tooltip>
            ) : (
              link
            )
          })}
        </div>
      ))}
    </nav>
  )
}

export function AppSidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  return (
    <aside
      className={cn(
        "hidden shrink-0 flex-col border-r border-border bg-sidebar transition-[width] duration-200 lg:flex",
        collapsed ? "w-[68px]" : "w-[232px]"
      )}
    >
      <Link
        href="/pulse"
        aria-label="VENA — на главную"
        className={cn("flex h-16 shrink-0 items-center outline-none focus-visible:ring-2 focus-visible:ring-ring/60", collapsed ? "justify-center" : "px-5")}
      >
        <VenaLogo compact={collapsed} />
      </Link>
      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
        <NavList collapsed={collapsed} />
      </div>
      <div className={cn("flex shrink-0 items-center border-t border-border px-3 py-3", collapsed ? "justify-center" : "justify-between")}>
        {collapsed ? null : <span className="px-2 text-[11px] text-faint">команда 5bit · ЛЦТ 2026</span>}
        <button
          type="button"
          onClick={onToggle}
          aria-label={collapsed ? "Развернуть меню" : "Свернуть меню"}
          className="flex size-8 cursor-pointer items-center justify-center rounded-md text-muted-foreground outline-none hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/60"
        >
          {collapsed ? <PanelLeftOpen className="size-[18px]" aria-hidden /> : <PanelLeftClose className="size-[18px]" aria-hidden />}
        </button>
      </div>
    </aside>
  )
}
