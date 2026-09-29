"use client"

import { Ellipsis } from "lucide-react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import * as React from "react"

import { AuthGate } from "@/features/auth"
import { WorkspaceProvider } from "@/features/workspace"
import { ACCOUNT_ITEMS, MOBILE_NAV, NAV_ITEMS, isActive } from "@/shared/config/routes"
import { cn } from "@/shared/lib/utils"
import { Sheet, SheetContent, SheetTitle } from "@/shared/ui/sheet"
import { VenaLogo } from "@/shared/ui/vena-mark"
import { CommandPalette } from "@/widgets/command-palette"
import { SystemNoticeBar } from "@/widgets/system-notice"

import { AppHeader } from "./app-header"
import { AppSidebar, NavList } from "./app-sidebar"

const COLLAPSED_KEY = "vena.sidebar.collapsed"

function readCollapsed() {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === "1"
  } catch {
    return false
  }
}

function MobileTabs({ onMore }: { onMore: () => void }) {
  const pathname = usePathname()
  const items = MOBILE_NAV.map((href) => NAV_ITEMS.find((item) => item.href === href)).filter(
    (item): item is (typeof NAV_ITEMS)[number] => Boolean(item)
  )
  const moreActive = !items.some((item) => isActive(pathname, item.href))
  return (
    <nav
      aria-label="Быстрая навигация"
      className="grid shrink-0 grid-cols-5 border-t border-border bg-background pb-[env(safe-area-inset-bottom)] lg:hidden"
    >
      {items.map((item) => {
        const Icon = item.icon
        const active = isActive(pathname, item.href)
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex h-14 flex-col items-center justify-center gap-1 text-[11px] outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/60",
              active ? "font-medium text-vena" : "text-muted-foreground"
            )}
          >
            <Icon className="size-5" aria-hidden />
            {item.label}
          </Link>
        )
      })}
      <button
        type="button"
        onClick={onMore}
        className={cn(
          "flex h-14 cursor-pointer flex-col items-center justify-center gap-1 text-[11px] outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/60",
          moreActive ? "font-medium text-vena" : "text-muted-foreground"
        )}
      >
        <Ellipsis className="size-5" aria-hidden />
        Ещё
      </button>
    </nav>
  )
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [searchOpen, setSearchOpen] = React.useState(false)
  const [menuOpen, setMenuOpen] = React.useState(false)
  const [collapsed, setCollapsed] = React.useState(readCollapsed)

  const toggle = () => {
    setCollapsed((value) => {
      try {
        localStorage.setItem(COLLAPSED_KEY, value ? "0" : "1")
      } catch {}
      return !value
    })
  }

  return (
    <AuthGate>
      <WorkspaceProvider>
        <div className="flex h-svh min-h-0 w-full overflow-hidden bg-background">
          <AppSidebar collapsed={collapsed} onToggle={toggle} />
          <div className="flex min-w-0 flex-1 flex-col">
            <AppHeader onOpenSearch={() => setSearchOpen(true)} onOpenMenu={() => setMenuOpen(true)} />
            <SystemNoticeBar />
            <main className="relative flex min-h-0 flex-1 flex-col overflow-hidden">{children}</main>
            <MobileTabs onMore={() => setMenuOpen(true)} />
          </div>
        </div>
        <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
          <SheetContent side="left" className="w-[280px] gap-0 p-0">
            <SheetTitle className="sr-only">Меню</SheetTitle>
            <div className="flex h-16 items-center border-b border-border px-5">
              <VenaLogo />
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-3 py-4">
              <NavList onNavigate={() => setMenuOpen(false)} />
              <div className="mt-5 flex flex-col gap-0.5 border-t border-border pt-4">
                {ACCOUNT_ITEMS.map((item) => {
                  const Icon = item.icon
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      onClick={() => setMenuOpen(false)}
                      className="flex h-9 items-center gap-3 rounded-md px-3 text-[14px] text-muted-foreground hover:bg-accent hover:text-foreground"
                    >
                      <Icon className="size-[18px]" aria-hidden />
                      {item.label}
                    </Link>
                  )
                })}
              </div>
            </div>
            <p className="border-t border-border px-5 py-3 text-[11px] text-faint">команда 5bit · ЛЦТ 2026</p>
          </SheetContent>
        </Sheet>
        <CommandPalette open={searchOpen} onOpenChange={setSearchOpen} />
      </WorkspaceProvider>
    </AuthGate>
  )
}
