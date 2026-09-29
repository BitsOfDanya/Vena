"use client"

import { Search, UserRound } from "lucide-react"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"

import { useAuthSession } from "@/features/auth"
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
  const { me, authEnabled, signOut } = useAuthSession()
  const title = me?.subject ?? "Дежурный инженер"
  const subtitle = me?.role ?? "…"

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
      <nav aria-label="Основная навигация" className="flex h-full min-w-0 items-stretch gap-1 overflow-x-auto">
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
          aria-label="Поиск"
          className="flex h-8 cursor-pointer items-center gap-2 px-2 text-[13px] text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/60"
        >
          <Search className="size-[18px]" aria-hidden />
          <span className="hidden font-mono text-[12px] text-faint md:inline">⌘K</span>
        </button>
        <DropdownMenu>
          <DropdownMenuTrigger
            aria-label="Аккаунт и настройки"
            className="flex size-8 cursor-pointer items-center justify-center text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/60"
          >
            <UserRound className="size-[18px]" aria-hidden />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel className="font-normal">
              <span className="block text-[13px] font-medium">{title}</span>
              <span className="block font-mono text-[12px] text-muted-foreground">{subtitle}</span>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => router.push("/settings")}>Настройки</DropdownMenuItem>
            <DropdownMenuItem onClick={() => router.push("/settings/security")}>Безопасность</DropdownMenuItem>
            <DropdownMenuItem onClick={() => router.push("/settings/audit")}>Журнал аудита</DropdownMenuItem>
            <DropdownMenuItem onClick={() => router.push("/settings/notifications")}>Уведомления</DropdownMenuItem>
            <DropdownMenuItem onClick={() => router.push("/settings/integrations")}>Интеграции</DropdownMenuItem>
            {authEnabled ? (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onClick={() => {
                    void signOut()
                  }}
                >
                  Выйти
                </DropdownMenuItem>
              </>
            ) : null}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  )
}
