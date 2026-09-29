import {
  Activity,
  BellRing,
  BookOpenText,
  ChartNoAxesCombined,
  ClipboardList,
  GitBranch,
  History,
  Info,
  LayoutDashboard,
  ScrollText,
  type LucideIcon,
} from "lucide-react"

export type NavItem = { href: string; label: string; icon: LucideIcon; hint: string }

export const NAV_GROUPS: { title: string; items: NavItem[] }[] = [
  {
    title: "Оперативно",
    items: [
      { href: "/pulse", label: "Пульс", icon: Activity, hint: "Что требует внимания сейчас" },
      { href: "/network", label: "Сеть", icon: GitBranch, hint: "Объекты, участки и схема по пикетам" },
      { href: "/alarms", label: "Алармы", icon: BellRing, hint: "Тревоги и проверка перед выездом" },
      { href: "/timeline", label: "Таймлайн", icon: History, hint: "История и прогноз канала" },
    ],
  },
  {
    title: "Работы",
    items: [
      { href: "/actions", label: "Работы", icon: ClipboardList, hint: "План и выполнение работ" },
      { href: "/journal", label: "Журнал", icon: ScrollText, hint: "События СМВУ" },
    ],
  },
  {
    title: "Аналитика",
    items: [
      { href: "/dashboard", label: "Дашборд", icon: LayoutDashboard, hint: "Сводка для руководства" },
      { href: "/effect", label: "Эффект", icon: ChartNoAxesCombined, hint: "Прогноз против факта" },
    ],
  },
]

export const NAV_ITEMS = NAV_GROUPS.flatMap((group) => group.items)

export const MOBILE_NAV = ["/pulse", "/network", "/alarms", "/actions"]

export const ACCOUNT_ITEMS: NavItem[] = [
  { href: "/models", label: "Модели", icon: BookOpenText, hint: "Какие модели работают и насколько точны" },
  { href: "/about", label: "О сервисе", icon: Info, hint: "Как устроена VENA и команда 5bit" },
]

export function isActive(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(`${href}/`)
}
