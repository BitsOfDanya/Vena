export const NAV_ITEMS = [
  { href: "/pulse", label: "Пульс" },
  { href: "/network", label: "Сеть" },
  { href: "/timeline", label: "Таймлайн" },
  { href: "/actions", label: "Работы" },
  { href: "/alarms", label: "Алармы" },
  { href: "/journal", label: "Журнал" },
  { href: "/dashboard", label: "Дашборд" },
  { href: "/effect", label: "Эффект" },
] as const

export const ACCOUNT_ITEMS = [
  { href: "/models", label: "Модели" },
  { href: "/about", label: "О сервисе" },
] as const

export type NavHref = (typeof NAV_ITEMS)[number]["href"]
