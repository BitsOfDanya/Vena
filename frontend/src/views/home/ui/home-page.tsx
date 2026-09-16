import {
  ArrowUpRight,
  Boxes,
  Braces,
  Check,
  Component,
  DatabaseZap,
  Layers3,
  Sparkles,
} from "lucide-react"
import Link from "next/link"

import { RequestDemoForm } from "@/features/request-demo"
import { Badge } from "@/shared/ui/badge"
import { Button } from "@/shared/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/ui/card"
import { Separator } from "@/shared/ui/separator"
import { HealthStatus } from "@/widgets/health-status"

const stack = [
  "Next.js 16 + TypeScript",
  "Tailwind CSS + shadcn/ui",
  "Radix UI primitives",
  "TanStack Query",
  "React Hook Form + Zod",
]

const architecture = [
  {
    icon: Layers3,
    title: "FSD без конфликта роутера",
    description: "app остаётся входом Next.js, а слой Pages живёт как views. Остальные границы FSD сохранены.",
  },
  {
    icon: DatabaseZap,
    title: "Типизированный data layer",
    description: "TanStack Query отвечает за серверное состояние, а ответы API проверяются схемами Zod.",
  },
  {
    icon: Component,
    title: "Своя дизайн-система",
    description: "Полный набор shadcn-компонентов находится в shared/ui и использует светлые токены Vena.",
  },
]

export function HomePage() {
  return (
    <main className="mx-auto min-h-svh w-full max-w-7xl px-4 py-5 sm:px-6 lg:px-8">
      <header className="flex items-center justify-between rounded-2xl border bg-card/75 px-4 py-3 shadow-sm backdrop-blur-xl sm:px-5">
        <Link className="flex items-center gap-2 font-heading font-semibold tracking-tight" href="/">
          <span className="grid size-8 place-items-center rounded-xl bg-primary text-primary-foreground shadow-sm">
            V
          </span>
          Vena
        </Link>
        <nav className="flex items-center gap-2" aria-label="Основная навигация">
          <Button asChild variant="ghost" className="hidden sm:inline-flex">
            <a href="#architecture">Архитектура</a>
          </Button>
          <Button asChild variant="outline">
            <Link href="/design-system">
              Компоненты <ArrowUpRight data-icon="inline-end" />
            </Link>
          </Button>
        </nav>
      </header>

      <section className="grid gap-8 py-16 lg:grid-cols-[1.15fr_0.85fr] lg:items-center lg:py-24">
        <div className="max-w-3xl">
          <Badge className="mb-5" variant="secondary">
            <Sparkles data-icon="inline-start" /> Vena foundation
          </Badge>
          <h1 className="font-heading text-4xl leading-[1.04] font-semibold tracking-[-0.045em] text-balance sm:text-6xl lg:text-7xl">
            Чистая основа для следующей продуктовой итерации.
          </h1>
          <p className="mt-6 max-w-2xl text-base leading-7 text-muted-foreground sm:text-lg">
            Бэкенд, фронтенд, границы модулей и UI-kit уже соединены. Можно переходить к предметной области, не возвращаясь к инфраструктурным решениям.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button asChild size="lg">
              <a href="#architecture">Посмотреть устройство <ArrowUpRight /></a>
            </Button>
            <Button asChild size="lg" variant="outline">
              <Link href="/design-system">Открыть дизайн-систему</Link>
            </Button>
          </div>
        </div>

        <Card className="border-white/70 bg-card/80 shadow-xl shadow-cyan-950/5 backdrop-blur-xl">
          <CardHeader className="border-b">
            <div className="mb-3 flex items-center justify-between">
              <span className="grid size-10 place-items-center rounded-xl bg-accent text-accent-foreground">
                <Boxes className="size-5" />
              </span>
              <Badge variant="outline">ready</Badge>
            </div>
            <CardTitle>Стек собран</CardTitle>
            <CardDescription>Зафиксированные версии и один рабочий контур.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <HealthStatus />
            <Separator />
            <ul className="space-y-3">
              {stack.map((item) => (
                <li className="flex items-center gap-2 text-sm" key={item}>
                  <span className="grid size-5 place-items-center rounded-full bg-emerald-100 text-emerald-700">
                    <Check className="size-3" strokeWidth={3} />
                  </span>
                  {item}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </section>

      <section className="scroll-mt-8 py-10" id="architecture">
        <div className="mb-7 flex items-end justify-between gap-4">
          <div>
            <Badge className="mb-3" variant="outline">
              <Braces data-icon="inline-start" /> Архитектура
            </Badge>
            <h2 className="font-heading text-3xl font-semibold tracking-tight sm:text-4xl">Границы уже на месте</h2>
          </div>
          <p className="hidden max-w-sm text-right text-sm text-muted-foreground md:block">
            Публичные API слайсов, тонкий routing layer и изолированное серверное состояние.
          </p>
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          {architecture.map(({ description, icon: Icon, title }) => (
            <Card className="bg-card/70 transition-transform duration-200 hover:-translate-y-1" key={title}>
              <CardHeader>
                <span className="mb-4 grid size-10 place-items-center rounded-xl bg-secondary text-secondary-foreground">
                  <Icon className="size-5" />
                </span>
                <CardTitle>{title}</CardTitle>
                <CardDescription className="leading-6">{description}</CardDescription>
              </CardHeader>
            </Card>
          ))}
        </div>
      </section>

      <section className="grid gap-6 py-14 lg:grid-cols-[0.75fr_1.25fr] lg:items-start">
        <div className="pt-2">
          <Badge className="mb-3" variant="secondary">Forms</Badge>
          <h2 className="font-heading text-3xl font-semibold tracking-tight">Валидация входит в основу</h2>
          <p className="mt-3 max-w-md leading-7 text-muted-foreground">
            Пример показывает целевой паттерн: схема рядом с feature, состояние формы локально, мутация через TanStack Query — когда появится endpoint.
          </p>
        </div>
        <RequestDemoForm />
      </section>

      <footer className="mt-8 flex flex-col gap-2 border-t py-6 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
        <span>Vena · full-stack foundation</span>
        <span>FastAPI · Next.js · FSD</span>
      </footer>
    </main>
  )
}
