export const NAV_ITEMS = [
  { href: "/pulse", label: "Pulse" },
  { href: "/network", label: "Network" },
  { href: "/timeline", label: "Timeline" },
  { href: "/actions", label: "Actions" },
  { href: "/alarms", label: "Alarms" },
  { href: "/journal", label: "Journal" },
  { href: "/dashboard", label: "Dashboard" },
] as const

export type NavHref = (typeof NAV_ITEMS)[number]["href"]
