"use client"

import { LogOut, Menu, Monitor, Moon, Search, Settings, Sun, UserRound } from "lucide-react"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { useTheme } from "next-themes"

import { useAuthSession } from "@/features/auth"
import { ACCOUNT_ITEMS, NAV_ITEMS, isActive } from "@/shared/config/routes"
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

const ROLE_LABEL: Record<string, string> = {
  admin: "Администратор",
  dispatcher: "Диспетчер",
  viewer: "Наблюдатель",
}

const THEMES = [
  { value: "light", label: "Светлая", icon: Sun },
  { value: "dark", label: "Тёмная", icon: Moon },
  { value: "system", label: "Как в системе", icon: Monitor },
] as const

const iconButton =
  "flex size-9 cursor-pointer items-center justify-center rounded-md text-muted-foreground outline-none transition-colors hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/60"

export function AppHeader({ onOpenSearch, onOpenMenu }: { onOpenSearch: () => void; onOpenMenu: () => void }) {
  const pathname = usePathname()
  const router = useRouter()
  const { theme, setTheme } = useTheme()
  const { me, authEnabled, signOut } = useAuthSession()
  const title = me?.subject ?? "Дежурный инженер"
  const role = me?.role ? (ROLE_LABEL[me.role] ?? me.role) : ""
  const current = [...NAV_ITEMS, ...ACCOUNT_ITEMS].find((item) => isActive(pathname, item.href))

  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-background/95 px-3 backdrop-blur sm:px-5">
      <button type="button" onClick={onOpenMenu} aria-label="Открыть меню" className={cn(iconButton, "lg:hidden")}>
        <Menu className="size-5" aria-hidden />
      </button>
      <Link href="/pulse" aria-label="VENA" className="flex items-center gap-2 lg:hidden">
        <VenaMark tile className="size-7" />
        <span className="text-[15px] font-semibold tracking-[0.14em]">VENA</span>
      </Link>
      {current ? (
        <div className="hidden min-w-0 items-baseline gap-3 lg:flex">
          <span className="text-[15px] font-semibold">{current.label}</span>
          <span className="truncate text-[13px] text-muted-foreground">{current.hint}</span>
        </div>
      ) : null}
      <div className="ml-auto flex shrink-0 items-center gap-1">
        <button
          type="button"
          onClick={onOpenSearch}
          aria-label="Поиск"
          className="mr-1 hidden h-9 w-64 cursor-pointer items-center gap-2 whitespace-nowrap rounded-md border border-border bg-elevated px-3 text-[13px] text-muted-foreground outline-none transition-colors hover:border-input hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/60 md:flex"
        >
          <Search className="size-4" aria-hidden />
          <span className="truncate">Объект, канал, раздел…</span>
          <kbd className="ml-auto rounded border border-border bg-surface px-1.5 font-mono text-[11px] text-faint">⌘K</kbd>
        </button>
        <button type="button" onClick={onOpenSearch} aria-label="Поиск" className={cn(iconButton, "md:hidden")}>
          <Search className="size-[18px]" aria-hidden />
        </button>
        <NotificationCenter />
        <DropdownMenu>
          <DropdownMenuTrigger aria-label="Аккаунт и настройки" className={cn(iconButton, "gap-2 px-1.5 sm:w-auto")}>
            <span className="flex size-7 items-center justify-center rounded-full bg-accent text-foreground">
              <UserRound className="size-4" aria-hidden />
            </span>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-64">
            <DropdownMenuLabel className="font-normal">
              <span className="block truncate text-[14px] font-medium text-foreground">{title}</span>
              {role ? <span className="block text-[12px] text-muted-foreground">{role}</span> : null}
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            {ACCOUNT_ITEMS.map((item) => {
              const Icon = item.icon
              return (
                <DropdownMenuItem key={item.href} onClick={() => router.push(item.href)}>
                  <Icon className="size-4" aria-hidden />
                  {item.label}
                </DropdownMenuItem>
              )
            })}
            <DropdownMenuItem onClick={() => router.push("/settings")}>
              <Settings className="size-4" aria-hidden />
              Настройки
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <div className="px-2 py-1.5">
              <p className="mb-1.5 text-[12px] text-muted-foreground">Тема</p>
              <div role="radiogroup" aria-label="Тема оформления" className="grid grid-cols-3 gap-1 rounded-md bg-surface p-0.5">
                {THEMES.map((item) => {
                  const Icon = item.icon
                  const selected = (theme ?? "light") === item.value
                  return (
                    <button
                      key={item.value}
                      type="button"
                      role="radio"
                      aria-checked={selected}
                      aria-label={item.label}
                      title={item.label}
                      onClick={() => setTheme(item.value)}
                      className={cn(
                        "flex h-7 cursor-pointer items-center justify-center rounded-[5px] text-muted-foreground outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring/60",
                        selected ? "bg-elevated text-foreground shadow-sm" : "hover:text-foreground"
                      )}
                    >
                      <Icon className="size-4" aria-hidden />
                    </button>
                  )
                })}
              </div>
            </div>
            {authEnabled ? (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onClick={() => {
                    void signOut()
                  }}
                >
                  <LogOut className="size-4" aria-hidden />
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
