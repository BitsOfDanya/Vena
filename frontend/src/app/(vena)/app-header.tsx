"use client"

import { Menu, Search, UserRound } from "lucide-react"
import { usePathname, useRouter } from "next/navigation"

import { logoutAccount, type SessionUser } from "@/entities/session"
import { NAV_ITEMS } from "@/shared/config/routes"
import { Button } from "@/shared/ui/button"
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/shared/ui/dropdown-menu"
import { NotificationCenter } from "@/widgets/notification-center"
import { useQueryClient } from "@tanstack/react-query"

export function AppHeader({ user, onOpenSearch, onOpenMenu }: {
  user: SessionUser
  onOpenSearch: () => void
  onOpenMenu: () => void
}) {
  const pathname = usePathname()
  const router = useRouter()
  const queryClient = useQueryClient()
  const title = NAV_ITEMS.find((item) => pathname.startsWith(item.href))?.label ?? "Настройки"

  async function logout() {
    await logoutAccount()
    queryClient.clear()
    router.replace("/login")
  }

  return (
    <header className="flex h-[72px] shrink-0 items-center gap-4 border-b border-border/70 bg-card px-5 md:px-8">
      <Button className="md:hidden" size="icon" variant="ghost" aria-label="Открыть меню" onClick={onOpenMenu}><Menu className="size-5" /></Button>
      <div><p className="text-xs text-muted-foreground">Рабочее пространство</p><p className="text-lg font-semibold">{title}</p></div>
      <div className="ml-auto flex items-center gap-2 md:gap-4">
        {user.role === "dispatcher" && <Button variant="secondary" className="hidden w-52 justify-start gap-2 text-muted-foreground lg:flex" onClick={onOpenSearch}><Search className="size-4" />Поиск <span className="ml-auto text-xs">⌘K</span></Button>}
        {user.role === "dispatcher" && <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Поиск" onClick={onOpenSearch}><Search className="size-5" /></Button>}
        {user.role === "dispatcher" && <NotificationCenter />}
        <DropdownMenu>
          <DropdownMenuTrigger className="flex items-center gap-3 rounded-lg px-2 py-1 text-left outline-none hover:bg-secondary focus-visible:ring-2 focus-visible:ring-ring">
            <span className="flex size-9 items-center justify-center rounded-full bg-primary/20 text-primary"><UserRound className="size-5" /></span>
            <span className="hidden min-w-0 md:block"><span className="block max-w-36 truncate text-sm font-medium">{user.full_name}</span><span className="block text-xs text-muted-foreground">{user.role === "dispatcher" ? "Диспетчер" : "Оператор"}</span></span>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel className="font-normal"><span className="block text-sm font-medium">{user.full_name}</span><span className="block text-xs text-muted-foreground">{user.email}</span></DropdownMenuLabel>
            <DropdownMenuSeparator />
            {user.role === "dispatcher" && <DropdownMenuItem onClick={() => router.push("/settings")}>Настройки</DropdownMenuItem>}
            <DropdownMenuItem onClick={logout}>Выйти</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  )
}
