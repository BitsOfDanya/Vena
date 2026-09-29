"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"

import { useAuthSession } from "@/features/auth"

import { cn } from "@/shared/lib/utils"

const TABS = [
  { href: "/settings", label: "Обзор" },
  { href: "/settings/notifications", label: "Уведомления" },
  { href: "/settings/integrations", label: "Интеграции" },
  { href: "/settings/security", label: "Безопасность" },
  { href: "/settings/users", label: "Пользователи" },
  { href: "/settings/audit", label: "Аудит" },
]

export function SettingsShell({ title, descriptor, children }: { title: string; descriptor: string; children: React.ReactNode }) {
  const pathname = usePathname()
  const { me } = useAuthSession()

  return (
    <div className="flex size-full min-h-0 flex-col">
      <div className="shrink-0 px-6 pt-4">
        <h1 className="flex items-baseline gap-3">
          <span className="text-[26px] font-semibold tracking-[-0.01em]">{title}</span>
          <span className="font-mono text-[13px] text-faint">{descriptor}</span>
        </h1>
        <nav aria-label="Настройки" className="mt-3 flex gap-5 border-b border-border">
          {TABS.filter(tab => tab.href !== "/settings/users" || me?.role === "admin").map((tab) => {
            const active = pathname === tab.href
            return (
              <Link
                key={tab.href}
                href={tab.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "relative pb-2 text-[14px] outline-none focus-visible:ring-2 focus-visible:ring-ring/60",
                  active ? "font-medium text-foreground" : "text-muted-foreground hover:text-foreground"
                )}
              >
                {tab.label}
                {active ? <span aria-hidden className="absolute inset-x-0 -bottom-px h-[2px] bg-vena" /> : null}
              </Link>
            )
          })}
        </nav>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
        <div className="max-w-4xl space-y-8">{children}</div>
      </div>
    </div>
  )
}

export function SettingsSection({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children: React.ReactNode
}) {
  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-[15px] font-semibold text-foreground">{title}</h2>
        {description ? <p className="mt-1 text-[13px] text-muted-foreground">{description}</p> : null}
      </div>
      {children}
    </section>
  )
}

export function StateTag({ state }: { state: "configured" | "not_configured" | "disabled" }) {
  const label = state === "configured" ? "Настроено" : state === "disabled" ? "Отключено" : "Не настроено"
  return (
    <span
      className={cn(
        "border px-2 py-0.5 text-[12px] font-medium",
        state === "configured" && "border-status-normal/60 text-status-normal",
        state === "not_configured" && "border-status-attention/60 text-status-attention",
        state === "disabled" && "border-border text-faint"
      )}
    >
      {label}
    </span>
  )
}
