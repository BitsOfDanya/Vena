"use client"

import { Search, UserRound } from "lucide-react"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"

import { NAV_ITEMS } from "@/shared/config/routes"
import { cn } from "@/shared/lib/utils"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/shared/ui/dropdown-menu"
import { VenaMark } from "@/shared/ui/vena-mark"
import { NotificationCenter } from "@/widgets/notification-center"

export function AppHeader({ onOpenSearch }: { onOpenSearch: () => void }) {
  const pathname = usePathname()
  const router = useRouter()

  return (
    <header className="flex h-14 shrink-0 items-center gap-8 border-b border-border px-6">
      <Link
        href="/pulse"
        className="flex shrink-0 items-center gap-2 outline-none focus-visible:ring-2 focus-visible:ring-ring/60"
        aria-label="VENA"
      >
        <VenaMark className="text-vena" />
        <span className="text-[15px] font-semibold tracking-[0.2em]">VENA</span>
      </Link>
      <nav aria-label="Primary" className="flex h-full min-w-0 items-stretch gap-1 overflow-x-auto">
        {NAV_ITEMS.map((item) => {
          const active = pathname === item.href || pathname.startsWith(`${item.href}/`)
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "relative flex items-center px-2.5 text-[14px] whitespace-nowrap outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/60",
                active ? "font-medium text-foreground" : "text-muted-foreground hover:text-foreground"
              )}
            >
              {item.label}
              {active ? <span aria-hidden className="absolute inset-x-2.5 bottom-3 h-[2px] bg-vena" /> : null}
            </Link>
          )
        })}
      </nav>
      <div className="ml-auto flex shrink-0 items-center gap-1">
        <NotificationCenter />
        <button
          type="button"
          onClick={onOpenSearch}
          aria-label="Search"
          className="flex h-8 items-center gap-2 px-2 text-[13px] text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/60"
        >
          <Search className="size-[18px]" aria-hidden />
          <span className="hidden font-mono text-[12px] text-faint md:inline">⌘K</span>
        </button>
        <DropdownMenu>
          <DropdownMenuTrigger
            aria-label="Account and settings"
            className="flex size-8 items-center justify-center text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/60"
          >
            <UserRound className="size-[18px]" aria-hidden />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel className="font-normal">
              <span className="block text-[13px] font-medium">Duty engineer</span>
              <span className="block text-[12px] text-muted-foreground">Dispatcher team</span>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => router.push("/settings")}>Settings</DropdownMenuItem>
            <DropdownMenuItem onClick={() => router.push("/settings/security")}>Security</DropdownMenuItem>
            <DropdownMenuItem onClick={() => router.push("/settings/audit")}>Audit log</DropdownMenuItem>
            <DropdownMenuItem onClick={() => router.push("/settings/notifications")}>Notification settings</DropdownMenuItem>
            <DropdownMenuItem onClick={() => router.push("/settings/integrations")}>Integrations</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  )
}
