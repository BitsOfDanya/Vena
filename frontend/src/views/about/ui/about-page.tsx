"use client"

import {
  Activity,
  ArrowRight,
  BellRing,
  ClipboardList,
  Database,
  GitBranch,
  Gauge,
  HeartPulse,
  LineChart,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react"
import Link from "next/link"

import { VenaMark } from "@/shared/ui/vena-mark"

const PIPELINE: { step: string; detail: string; href: string; icon: LucideIcon }[] = [
  { step: "Журнал СМВУ", detail: "события каналов: насосы, вентиляция, фазы, дым, газ, доступ", href: "/journal", icon: Database },
  { step: "Модели", detail: "вероятность отказа на 24 и 72 часа и главная причина", href: "/models", icon: LineChart },
  { step: "Ситуация", detail: "что случится, где, почему и что делать первым", href: "/pulse", icon: Activity },
  { step: "Работа", detail: "черновик работы для бригады в один клик", href: "/actions", icon: ClipboardList },
  { step: "Эффект", detail: "сравнение прогноза с фактом и обратная связь", href: "/effect", icon: Gauge },
]

const FEATURES: { title: string; text: string; icon: LucideIcon }[] = [
  { title: "Прогноз отказов", text: "Насосы, вентиляторы, питание, подтопление и пожарная сигнализация: вероятность события на сутки и трое суток по каждому каналу.", icon: LineChart },
  { title: "Проверка тревог", text: "Модель оценивает, подтвердится ли тревога дыма или газа, и отделяет плановые проверки датчиков от реальных срабатываний.", icon: BellRing },
  { title: "Индекс здоровья", text: "Число от 0 до 100 для каждого участка и объекта — откалиброванная вероятность события в ближайшие сутки.", icon: HeartPulse },
  { title: "Схема по пикетам", text: "Датчики объекта на трассе коллектора: видно, на каком участке растёт риск и какие системы задеты.", icon: GitBranch },
  { title: "План осмотров", text: "Каждое утро — насосы и вентиляторы с наибольшим риском, без повторов по уже созданным работам.", icon: ClipboardList },
  { title: "Честная проверка", text: "Все модели проверены на январе–июне 2026 года, которых не было в обучении. Метрики открыты на странице «Модели».", icon: ShieldCheck },
]

const TEAM = [
  { name: "Даниил", role: "ML и бэкенд", text: "модели прогноза, калибровка, анализ журнала, API" },
  { name: "Вадим", role: "Фронтенд и UX", text: "рабочие экраны диспетчера и руководителя" },
  { name: "Денис", role: "Инфраструктура", text: "развёртывание, безопасность, интеграции и загрузка данных" },
  { name: "Илья", role: "ML-исследования", text: "эксперименты с признаками и архитектурами моделей" },
]

const STACK = ["Python", "CatBoost", "LightGBM", "scikit-learn", "DuckDB", "FastAPI", "PostgreSQL", "Next.js", "React", "Docker", "Caddy"]

export function AboutPage() {
  return (
    <div className="size-full overflow-y-auto">
      <div className="mx-auto flex w-full max-w-[1200px] flex-col gap-8 px-4 py-6 sm:px-6 sm:py-8">
        <section className="relative overflow-hidden rounded-xl bg-[#0d2b28] px-6 py-8 text-[#d9ece8] sm:px-10 sm:py-10">
          <div className="flex items-center gap-3">
            <VenaMark tile className="size-11" />
            <div className="leading-tight">
              <p className="text-[20px] font-semibold tracking-[0.16em] text-white">VENA</p>
              <p className="text-[13px] text-[#9cc5bd]">мониторинг инженерных коллекторов</p>
            </div>
          </div>
          <h1 className="mt-6 max-w-[720px] text-[28px] leading-tight font-semibold text-white sm:text-[34px]">
            Предупреждаем об отказах оборудования коллекторов до того, как они станут аварией
          </h1>
          <p className="mt-3 max-w-[720px] text-[15px] leading-relaxed text-[#b5d3cd]">
            VENA читает журнал системы мониторинга и управления, прогнозирует отказы насосов, вентиляции, питания и
            срабатывания пожарной сигнализации и подсказывает диспетчеру, что проверить первым. Решение сделано для
            кейса «Москоллектор» на хакатоне «Лидеры цифровой трансформации 2026».
          </p>
          <div className="mt-8 grid grid-cols-2 gap-6 border-t border-white/15 pt-6 sm:grid-cols-4">
            {[
              ["8", "моделей прогноза"],
              ["10 800+", "прогнозов в каждом расчёте"],
              ["7,5 лет", "журнала СМВУ в обучении"],
              ["24 / 72 ч", "горизонт прогноза"],
            ].map(([value, label]) => (
              <div key={label}>
                <p className="font-mono text-[24px] text-white">{value}</p>
                <p className="mt-1 text-[12.5px] text-[#9cc5bd]">{label}</p>
              </div>
            ))}
          </div>
        </section>

        <section>
          <h2 className="text-[20px] font-semibold">Как это работает</h2>
          <ol className="mt-4 grid gap-3 md:grid-cols-5">
            {PIPELINE.map((item, index) => {
              const Icon = item.icon
              return (
                <li key={item.step} className="relative">
                  <Link
                    href={item.href}
                    className="flex h-full flex-col rounded-lg border border-border bg-elevated p-4 shadow-[var(--shadow-card)] outline-none transition-colors hover:border-vena focus-visible:ring-2 focus-visible:ring-ring/60"
                  >
                    <span className="flex items-center justify-between">
                      <Icon className="size-5 text-vena" aria-hidden />
                      <span className="text-[12px] text-faint tabular-nums">{index + 1}</span>
                    </span>
                    <span className="mt-3 text-[15px] font-semibold">{item.step}</span>
                    <span className="mt-1 text-[13px] text-muted-foreground">{item.detail}</span>
                  </Link>
                  {index < PIPELINE.length - 1 ? (
                    <ArrowRight aria-hidden className="absolute top-1/2 -right-3 z-10 hidden size-4 -translate-y-1/2 text-faint md:block" />
                  ) : null}
                </li>
              )
            })}
          </ol>
        </section>

        <section>
          <h2 className="text-[20px] font-semibold">Что умеет VENA</h2>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((item) => {
              const Icon = item.icon
              return (
                <article key={item.title} className="rounded-lg border border-border bg-elevated p-5 shadow-[var(--shadow-card)]">
                  <span className="flex size-9 items-center justify-center rounded-md bg-vena/10">
                    <Icon className="size-[18px] text-vena" aria-hidden />
                  </span>
                  <h3 className="mt-3 text-[15px] font-semibold">{item.title}</h3>
                  <p className="mt-1 text-[13.5px] leading-relaxed text-muted-foreground">{item.text}</p>
                </article>
              )
            })}
          </div>
        </section>

        <section className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div className="rounded-lg border border-border bg-elevated p-6 shadow-[var(--shadow-card)]">
            <p className="text-[12.5px] font-medium text-vena">Команда</p>
            <h2 className="mt-1 text-[22px] font-semibold">5bit</h2>
            <p className="mt-2 text-[14px] leading-relaxed text-muted-foreground">
              Мы собрали VENA от сырого журнала до работающего сервиса: анализ данных, модели, API, интерфейс и
              развёртывание на собственном сервере.
            </p>
            <ul className="mt-5 grid gap-3 sm:grid-cols-2">
              {TEAM.map((member) => (
                <li key={member.name} className="flex gap-3 rounded-md border border-border p-3">
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-vena text-[14px] font-semibold text-primary-foreground">
                    {member.name[0]}
                  </span>
                  <span className="min-w-0">
                    <span className="block text-[14px] font-semibold">{member.name}</span>
                    <span className="block text-[12.5px] font-medium text-vena">{member.role}</span>
                    <span className="mt-0.5 block text-[12.5px] text-muted-foreground">{member.text}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
          <div className="flex flex-col gap-6">
            <div className="rounded-lg border border-border bg-elevated p-6 shadow-[var(--shadow-card)]">
              <h2 className="text-[17px] font-semibold">Технологии</h2>
              <ul className="mt-3 flex flex-wrap gap-2">
                {STACK.map((item) => (
                  <li key={item} className="rounded-md bg-surface px-2.5 py-1 text-[13px]">
                    {item}
                  </li>
                ))}
              </ul>
            </div>
            <div className="rounded-lg border border-border bg-elevated p-6 shadow-[var(--shadow-card)]">
              <h2 className="text-[17px] font-semibold">С чего начать</h2>
              <ul className="mt-3 space-y-2 text-[14px]">
                {[
                  ["/pulse", "Пульс", "что требует внимания прямо сейчас"],
                  ["/network", "Сеть", "схема объекта по пикетам"],
                  ["/models", "Модели", "точность каждой модели на проверке"],
                  ["/dashboard", "Дашборд", "сводка для руководства"],
                ].map(([href, title, text]) => (
                  <li key={href}>
                    <Link href={href} className="group flex items-baseline gap-2 outline-none focus-visible:ring-2 focus-visible:ring-ring/60">
                      <span className="font-medium text-vena group-hover:underline group-hover:underline-offset-4">{title}</span>
                      <span className="text-muted-foreground">— {text}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
