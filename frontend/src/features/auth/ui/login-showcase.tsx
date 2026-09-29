"use client"

import * as React from "react"

import { VenaMark } from "@/shared/ui/vena-mark"

const READOUTS = [
  { channel: "Н1 ПК1090", object: "5963", system: "Насос", lane: 0, pk: 1090, p: 97, horizon: "72 ч", why: "Частота сбоев растёт" },
  { channel: "1ФАО1", object: "5218", system: "Фидер аварийного освещения", lane: 2, pk: 499, p: 96, horizon: "24 ч", why: "События канала участились относительно обычного уровня" },
  { channel: "АНС2 Н3 ПК366", object: "5011", system: "Насос", lane: 0, pk: 366, p: 74, horizon: "72 ч", why: "Повышенная активность канала за несколько часов" },
  { channel: "В12 ПК683", object: "5657", system: "Вентилятор", lane: 1, pk: 683, p: 50, horizon: "72 ч", why: "Тревоги канала участились за последнюю неделю" },
]

const LANES = [
  { label: "НАСОСЫ", points: [120, 240, 366, 520, 610, 780, 950, 1090] },
  { label: "ВЕНТИЛЯЦИЯ", points: [80, 300, 460, 683, 840, 1010] },
  { label: "ПИТАНИЕ", points: [60, 200, 499, 560, 720, 900, 1150] },
  { label: "ДЫМ", points: [140, 330, 420, 640, 760, 980, 1120] },
]

const COMPARE = [
  ["Сигнал приходит, когда агрегат уже встал", "Риск отказа виден за 13–48 часов"],
  ["Тысячи тревог в месяц без приоритета", "5 каналов на день, которые действительно стоит проверить"],
  ["Непонятно, почему сработало", "Причина, последствие и первый шаг в карточке"],
  ["Точность никто не проверял", "Все модели проверены на январе–июне 2026"],
]

const WIDTH = 640
const LEFT = 92
const SPAN = 1200
const x = (pk: number) => LEFT + (pk / SPAN) * (WIDTH - LEFT - 16)

function Glyph({ lane, cx, cy, fill }: { lane: number; cx: number; cy: number; fill: string }) {
  if (lane === 0) return <path d={`M${cx - 5},${cy - 4} L${cx + 5},${cy - 4} L${cx},${cy + 5} Z`} fill={fill} />
  if (lane === 1) return <rect x={cx - 4} y={cy - 4} width={8} height={8} fill={fill} />
  if (lane === 2) return <path d={`M${cx},${cy - 5} L${cx + 5},${cy} L${cx},${cy + 5} L${cx - 5},${cy} Z`} fill={fill} />
  return <circle cx={cx} cy={cy} r={4.2} fill={fill} />
}

export function LoginShowcase() {
  const [index, setIndex] = React.useState(0)
  React.useEffect(() => {
    const timer = window.setInterval(() => setIndex((value) => (value + 1) % READOUTS.length), 3600)
    return () => window.clearInterval(timer)
  }, [])
  const current = READOUTS[index]
  const laneY = (lane: number) => 50 + lane * 28

  return (
    <div className="relative flex h-svh flex-col gap-5 overflow-y-auto px-10 py-8 xl:px-12">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <VenaMark tile className="size-10" />
          <div className="leading-tight">
            <p className="font-mono text-[19px] font-medium tracking-[0.3em] text-[#f1ede3]">VENA</p>
            <p className="text-[12.5px] text-[#a9bdb7]">прогноз аварий инженерных коллекторов</p>
          </div>
        </div>
        <span className="flex items-center gap-2 border border-[#2c4440] px-2.5 py-1 font-mono text-[11px] text-[#8fb3aa]">
          <span className="size-1.5 bg-[#4fb3a4] vena-breathe" />
          10 856 прогнозов · снимок 30.06.2026
        </span>
      </div>

      <div className="max-w-[640px]">
        <h2 className="text-[34px] leading-[1.08] font-semibold tracking-[-0.015em] text-[#f6f3ea]">
          Видим отказ оборудования
          <br />
          <span className="text-[#d69a3f]">до того, как он станет аварией</span>
        </h2>
        <p className="mt-3 max-w-[560px] text-[14.5px] leading-relaxed text-[#b3c4bf]">
          VENA читает журнал СМВУ по 11 тысячам каналов и каждый час оценивает, какой насос, вентилятор, фидер или датчик
          дыма откажет в ближайшие сутки или трое — и что с этим сделать.
        </p>
      </div>

      <figure className="border border-[#2c4440] bg-[#0b1715]">
        <figcaption className="flex items-center justify-between border-b border-[#2c4440] px-4 py-2 font-mono text-[11px] text-[#8fb3aa]">
          <span>ОБЪЕКТ {current.object} · ТРАССА ПО ПИКЕТАМ</span>
          <span>ПРИМЕР ИЗ СНИМКА</span>
        </figcaption>
        <svg viewBox={`0 0 ${WIDTH} 158`} className="block w-full" aria-hidden>
          <defs>
            <pattern id="login-grid" width="24" height="24" patternUnits="userSpaceOnUse">
              <path d="M24 0H0V24" fill="none" stroke="#1d2f2c" />
            </pattern>
          </defs>
          <rect width={WIDTH} height="158" fill="url(#login-grid)" />
          <line x1={LEFT} x2={WIDTH - 16} y1="26" y2="26" stroke="#3d5a55" strokeWidth="4" />
          {[0, 200, 400, 600, 800, 1000, 1200].map((pk) => (
            <g key={pk}>
              <line x1={x(pk)} x2={x(pk)} y1="20" y2="150" stroke="#1f3531" />
              <text x={x(pk)} y="14" textAnchor="middle" fontSize="9.5" fill="#6f8e87" fontFamily="var(--font-plex-mono)">
                ПК{pk}
              </text>
            </g>
          ))}
          {LANES.map((lane, laneIndex) => (
            <g key={lane.label}>
              <text x="8" y={laneY(laneIndex) + 3.5} fontSize="9.5" fill="#6f8e87" fontFamily="var(--font-plex-mono)">
                {lane.label}
              </text>
              <line x1={LEFT} x2={WIDTH - 16} y1={laneY(laneIndex)} y2={laneY(laneIndex)} stroke="#223a36" strokeDasharray="2 5" />
              {lane.points.map((pk) => {
                const active = laneIndex === current.lane && pk === current.pk
                return (
                  <g key={pk}>
                    {active ? (
                      <circle cx={x(pk)} cy={laneY(laneIndex)} r="13" fill="none" stroke="#e5675c" strokeWidth="1.5" className="vena-breathe" />
                    ) : null}
                    <Glyph lane={laneIndex} cx={x(pk)} cy={laneY(laneIndex)} fill={active ? "#e5675c" : "#4d6b65"} />
                  </g>
                )
              })}
            </g>
          ))}
          <line x1={LEFT} x2={LEFT} y1="20" y2="150" stroke="#4fb3a4" strokeOpacity="0.55" className="vena-scan" />
        </svg>
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-6 gap-y-1.5 border-t border-[#2c4440] px-4 py-3 font-mono text-[12px]">
          <dt className="text-[#6f8e87]">КАНАЛ</dt>
          <dd className="text-[#f1ede3]">
            {current.channel} · {current.system.toLowerCase()} · объект {current.object}
          </dd>
          <dt className="text-[#6f8e87]">РИСК</dt>
          <dd className="flex items-center gap-3 text-[#f1ede3]">
            <span className="relative h-2 w-40 bg-[#1f3531]">
              <span className="absolute inset-y-0 left-0 bg-[#e5675c] transition-[width] duration-700" style={{ width: `${current.p}%` }} />
            </span>
            {current.p}% за {current.horizon}
          </dd>
          <dt className="text-[#6f8e87]">ПРИЧИНА</dt>
          <dd className="truncate text-[#d9d4c8]">{current.why}</dd>
        </dl>
      </figure>

      <div className="grid border-t border-l border-[#2c4440] text-[13px] sm:grid-cols-2">
        <p className="border-r border-b border-[#2c4440] px-4 py-2 font-mono text-[11px] text-[#6f8e87]">ОБЫЧНЫЙ МОНИТОРИНГ</p>
        <p className="border-r border-b border-[#2c4440] px-4 py-2 font-mono text-[11px] text-[#4fb3a4]">С VENA</p>
        {COMPARE.map(([before, after]) => (
          <React.Fragment key={before}>
            <p className="border-r border-b border-[#2c4440] px-4 py-2 text-[#8a9b96] line-through decoration-[#8a9b96]/40">{before}</p>
            <p className="border-r border-b border-[#2c4440] px-4 py-2 text-[#e8e4da]">{after}</p>
          </React.Fragment>
        ))}
      </div>

      <div className="mt-auto flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-wrap gap-x-8 gap-y-3">
          {[
            ["8", "моделей прогноза"],
            ["×2–3", "точнее случайного выбора"],
            ["13–48 ч", "упреждение"],
            ["7,5 лет", "журнала в обучении"],
          ].map(([value, label]) => (
            <div key={label}>
              <p className="font-mono text-[22px] text-[#f1ede3]">{value}</p>
              <p className="text-[12px] text-[#8fb3aa]">{label}</p>
            </div>
          ))}
        </div>
        <p className="font-mono text-[11px] text-[#6f8e87]">КОМАНДА 5BIT · ЛЦТ 2026 · МОСКОЛЛЕКТОР</p>
      </div>
    </div>
  )
}
