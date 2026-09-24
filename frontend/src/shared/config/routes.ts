export const NAV_ITEMS = [
  { href: "/dashboard", label: "Обзор" },
  { href: "/data", label: "Данные" },
  { href: "/map", label: "Карта" },
  { href: "/imports", label: "Загрузки" },
  { href: "/pulse", label: "Пульс" },
  { href: "/network", label: "Сеть" },
  { href: "/timeline", label: "История" },
  { href: "/actions", label: "Работы" },
] as const

export type NavHref = (typeof NAV_ITEMS)[number]["href"]
