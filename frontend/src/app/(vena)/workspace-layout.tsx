"use client"

import { Activity, ChartNoAxesCombined, Database, FileUp, GitBranch, History, ListChecks, MapPinned } from "lucide-react"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import * as React from "react"

import { useSession, type SessionUser } from "@/entities/session"
import { WorkspaceProvider } from "@/features/workspace"
import { NAV_ITEMS } from "@/shared/config/routes"
import { cn } from "@/shared/lib/utils"
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/shared/ui/sheet"
import { CommandPalette } from "@/widgets/command-palette"
import { SystemNoticeBar } from "@/widgets/system-notice"

import { AppHeader } from "./app-header"

const ICONS = [ChartNoAxesCombined, Database, MapPinned, FileUp, Activity, GitBranch, History, ListChecks]
const OPERATOR_ROUTES = new Set(["/dashboard", "/data", "/map", "/imports"])

function Sidebar({ user, onNavigate }: { user: SessionUser; onNavigate?: () => void }) {
  const pathname = usePathname()
  return (
    <div className="flex h-full flex-col bg-sidebar">
      <Link href="/dashboard" className="flex h-[72px] items-center border-b border-sidebar-border px-7 text-xl font-bold tracking-[0.13em] text-white"><span className="text-primary">V</span>ENA<span className="ml-2 rounded bg-primary/15 px-2 py-0.5 text-[9px] font-semibold tracking-[0.14em] text-primary">OPS</span></Link>
      <nav aria-label="Основная навигация" className="flex-1 space-y-1 overflow-y-auto px-3 py-7">
        <p className="mb-3 px-4 text-[11px] font-semibold uppercase tracking-[0.16em] text-faint">Рабочее пространство</p>
        {NAV_ITEMS.map((item, index) => {
          if (user.role === "operator" && !OPERATOR_ROUTES.has(item.href)) return null
          const Icon = ICONS[index]
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`)
          return <Link key={item.href} href={item.href} onClick={onNavigate} aria-current={active ? "page" : undefined} className={cn("flex h-11 items-center gap-3 rounded-lg px-4 text-[14px] font-medium transition-colors", active ? "bg-primary text-white shadow-md shadow-primary/15" : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-white")}><Icon className="size-[18px]" />{item.label}</Link>
        })}
      </nav>
      <div className="border-t border-sidebar-border p-6"><div className="flex items-center gap-2 text-xs text-muted-foreground"><span className="size-2 rounded-full bg-chart-2" />Vena · рабочий контур</div></div>
    </div>
  )
}

export function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const session = useSession()
  const [searchOpen, setSearchOpen] = React.useState(false)
  const [menuOpen, setMenuOpen] = React.useState(false)

  React.useEffect(() => {
    if (session.isError) router.replace("/login")
  }, [session.isError, router])

  const operatorOutsideWorkspace = session.data?.role === "operator" && ![...OPERATOR_ROUTES].some((path) => pathname === path || pathname.startsWith(`${path}/`))
  React.useEffect(() => {
    if (operatorOutsideWorkspace) router.replace("/dashboard")
  }, [operatorOutsideWorkspace, router])

  if (session.isPending || session.isError || !session.data || operatorOutsideWorkspace) {
    return <div className="flex min-h-svh items-center justify-center bg-background text-sm text-muted-foreground">{session.isError ? "Переход к входу…" : "Загрузка рабочего пространства…"}</div>
  }

  return (
    <WorkspaceProvider>
      <div className="flex h-svh min-h-0 w-full overflow-hidden bg-background">
        <aside className="hidden w-[248px] shrink-0 border-r border-sidebar-border md:block"><Sidebar user={session.data} /></aside>
        <Sheet open={menuOpen} onOpenChange={setMenuOpen}><SheetContent side="left" className="w-[248px] border-sidebar-border bg-sidebar p-0"><SheetHeader className="sr-only"><SheetTitle>Навигация</SheetTitle></SheetHeader><Sidebar user={session.data} onNavigate={() => setMenuOpen(false)} /></SheetContent></Sheet>
        <div className="flex min-w-0 flex-1 flex-col">
          <AppHeader user={session.data} onOpenSearch={() => setSearchOpen(true)} onOpenMenu={() => setMenuOpen(true)} />
          {session.data.role === "dispatcher" && <SystemNoticeBar />}
          <main className="relative flex min-h-0 flex-1 flex-col overflow-hidden">{children}</main>
        </div>
      </div>
      {session.data.role === "dispatcher" && <CommandPalette open={searchOpen} onOpenChange={setSearchOpen} />}
    </WorkspaceProvider>
  )
}
