"use client"

import Link from "next/link"

import { Button } from "@/shared/ui/button"

const PIPELINE = [
  { step: "Журнал СМВУ", href: "/journal", detail: "Поток событий каналов" },
  { step: "Модели", href: "/models", detail: "Прогноз с вероятностью" },
  { step: "Инцидент по локации", href: "/pulse", detail: "Карточка ситуации" },
  { step: "Алармы", href: "/alarms", detail: "Очередь тревог диспетчера" },
  { step: "Черновик работы", href: "/actions", detail: "Маршрут бригады" },
  { step: "Решение", href: "/journal", detail: "Подтвердить / отклонить" },
  { step: "Дообучение", href: "/effect", detail: "Эффект и обратная связь" },
] as const

const PATHS = [
  {
    title: "Пожар (раздел 12 ТЗ)",
    steps: [
      "Тревога дыма или температуры → модель подтверждения тревоги",
      "Карточка: проверить по камерам перед выездом",
      "Серия ППР — серым, выезд не нужен",
      "Решение диспетчера → журнал → эффект",
    ],
  },
  {
    title: "Подтопление (раздел 12 ТЗ)",
    steps: [
      "Рост риска насоса / фазы питания АНС",
      "Что / последствие: риск подтопления секции",
      "Что делать: откачка, резерв, передвижной насос",
      "Индекс здоровья участка и история эпизодов на карточке",
    ],
  },
] as const

export function AboutPage() {
  return (
    <div className="flex size-full min-h-0 flex-col overflow-auto">
      <div className="flex shrink-0 flex-wrap items-center gap-x-6 gap-y-3 px-6 pt-4 pb-3">
        <h1 className="text-[26px] font-semibold tracking-[-0.01em]">Как работает VENA</h1>
        <p className="text-[13px] text-muted-foreground">От журнала СМВУ до решения диспетчера и дообучения</p>
        <div className="ml-auto flex items-center gap-3">
          <Button asChild variant="outline" size="sm">
            <Link href="/pulse">К пульсу</Link>
          </Button>
          <Button asChild variant="outline" size="sm">
            <Link href="/models">Модели</Link>
          </Button>
        </div>
      </div>

      <div className="space-y-6 px-6 pb-8">
        <section className="border border-border bg-elevated">
          <div className="border-b border-border-soft px-4 py-3">
            <h2 className="text-[12px] font-medium">Контур для жюри</h2>
            <p className="mt-1 text-[12px] text-muted-foreground">Каждый шаг ведёт на рабочий экран</p>
          </div>
          <ol className="divide-y divide-border-soft">
            {PIPELINE.map((item, index) => (
              <li key={item.step}>
                <Link
                  href={item.href}
                  className="flex items-baseline gap-4 px-4 py-3 outline-none hover:bg-surface/40 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/60"
                >
                  <span className="font-mono text-[12px] text-faint tabular-nums">{index + 1}</span>
                  <span className="text-[14px] font-medium text-vena">{item.step}</span>
                  <span className="text-[13px] text-muted-foreground">{item.detail}</span>
                </Link>
              </li>
            ))}
          </ol>
        </section>

        <div className="grid gap-4 lg:grid-cols-2">
          {PATHS.map((path) => (
            <section key={path.title} className="border border-border bg-elevated">
              <div className="border-b border-border-soft px-4 py-3">
                <h2 className="text-[13px] font-semibold">{path.title}</h2>
              </div>
              <ol className="list-decimal space-y-2 px-4 py-3 pl-8 text-[13px] text-muted-foreground">
                {path.steps.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ol>
            </section>
          ))}
        </div>
      </div>
    </div>
  )
}
