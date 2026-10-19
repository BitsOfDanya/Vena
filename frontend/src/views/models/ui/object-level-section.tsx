"use client"

import * as React from "react"

import {
  formatShare,
  heldOutPeriodPhrase,
  liftOverRandom,
  listPrecision,
  payback,
  paybackVerdict,
  useObjectLevel,
  type ObjectLevelModel,
} from "@/entities/analytics"
import { formatCount } from "@/shared/lib/plural"
import { cn } from "@/shared/lib/utils"
import { Button } from "@/shared/ui/button"
import { Field, FieldLabel } from "@/shared/ui/field"
import { Input } from "@/shared/ui/input"
import { NativeSelect, NativeSelectOption } from "@/shared/ui/native-select"
import { Segmented } from "@/shared/ui/segmented"
import { LoadingBar, StateMessage } from "@/shared/ui/state-message"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/shared/ui/table"

const LIST_SIZES = [3, 5, 10]
const HEAD = "h-9 px-4 text-[12px] font-normal text-faint"
const CELL = "px-4 py-2.5 text-right font-mono tabular-nums"

function decimal(value: number | null, digits = 1) {
  if (value == null) return "—"
  const scale = 10 ** digits
  return formatCount(Math.round(value * scale) / scale)
}

function rubles(value: number) {
  return `${formatCount(Math.round(value))} ₽`
}

function amount(value: string) {
  const parsed = Number(value.replace(",", "."))
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0
}

function MetricsTable({ models, period }: { models: ObjectLevelModel[]; period: string | null }) {
  return (
    <section id="object-level" className="scroll-mt-20 border border-border bg-elevated">
      <div className="border-b border-border-soft px-4 py-3">
        <h2 className="text-[15px] font-semibold">Точность на уровне объекта</h2>
        <p className="mt-1 max-w-[860px] text-[12px] text-muted-foreground">
          Единица — объект-сутки: в утренний список попадают объекты с наибольшим риском, событие засчитывается, если оно
          случилось на объекте за горизонт модели. Проверено на {heldOutPeriodPhrase(period)}. Кратность — точность топ-3,
          делённая на долю объектов с событием: во сколько раз список лучше случайного выбора объектов.
        </p>
      </div>
      <Table className="text-[13px]">
        <TableHeader>
          <TableRow className="border-border-soft hover:bg-transparent">
            <TableHead className={HEAD}>Сценарий</TableHead>
            <TableHead className={cn(HEAD, "text-right")}>Объектов в сутки</TableHead>
            <TableHead className={cn(HEAD, "text-right")}>Доля событий</TableHead>
            {LIST_SIZES.map((size) => (
              <TableHead key={size} className={cn(HEAD, "text-right")}>
                Точность топ-{size}
              </TableHead>
            ))}
            <TableHead className={cn(HEAD, "text-right")}>Кратность к случайному</TableHead>
            <TableHead className={cn(HEAD, "text-right")}>Полнота при точности 0,7</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {models.map((model) => {
            const lift = liftOverRandom(model)
            return (
              <TableRow key={model.id} className="border-border-soft">
                <TableCell className="px-4 py-2.5">
                  <span className="font-medium">{model.label}</span>
                  {model.horizonHours != null ? (
                    <span className="ml-2 font-mono text-[12px] text-faint">{model.horizonHours} ч</span>
                  ) : null}
                </TableCell>
                <TableCell className={CELL}>{decimal(model.objectsPerDay)}</TableCell>
                <TableCell className={CELL}>{formatShare(model.baseRate)}</TableCell>
                {LIST_SIZES.map((size) => (
                  <TableCell key={size} className={CELL}>
                    {formatShare(listPrecision(model, size))}
                  </TableCell>
                ))}
                <TableCell className={CELL}>{lift != null ? `×${decimal(lift)}` : "—"}</TableCell>
                <TableCell className={CELL}>{formatShare(model.recallAtPrecision70)}</TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </section>
  )
}

function Output({ label, value, detail, className }: { label: string; value: string; detail?: string; className?: string }) {
  return (
    <div className="px-4 py-3">
      <p className="text-[12px] text-faint">{label}</p>
      <p className={cn("mt-1 font-mono text-[22px] tabular-nums", className)}>{value}</p>
      {detail ? <p className="mt-0.5 text-[12px] text-muted-foreground">{detail}</p> : null}
    </div>
  )
}

function PaybackCalculator({ models }: { models: ObjectLevelModel[] }) {
  const [selected, setSelected] = React.useState<string | null>(null)
  const [size, setSize] = React.useState(5)
  const [cost, setCost] = React.useState("15000")
  const [loss, setLoss] = React.useState("300000")
  const [share, setShare] = React.useState("40")

  const model =
    models.find((item) => item.id === selected) ?? models.find((item) => listPrecision(item, 5) != null) ?? models[0]
  const precision = listPrecision(model, size)
  const result = payback({ size, precision, cost: amount(cost), loss: amount(loss), share: amount(share) / 100 })
  const effect = result.yearlyEffect

  return (
    <section className="border border-border bg-elevated">
      <div className="border-b border-border-soft px-4 py-3">
        <h2 className="text-[15px] font-semibold">Окупаемость утреннего списка</h2>
        <p className="mt-1 text-[12px] text-muted-foreground">
          Каждое утро бригада проверяет объекты с наибольшим риском: проверка стоит денег, предотвращённый инцидент экономит
          ущерб.
        </p>
      </div>
      <div className="grid gap-4 px-4 pt-4 sm:grid-cols-2 xl:grid-cols-5">
        <Field>
          <FieldLabel htmlFor="payback-scenario">Сценарий</FieldLabel>
          <NativeSelect id="payback-scenario" className="w-full" value={model.id} onChange={(event) => setSelected(event.target.value)}>
            {models.map((item) => (
              <NativeSelectOption key={item.id} value={item.id}>
                {item.label}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </Field>
        <Field>
          <FieldLabel>Размер списка</FieldLabel>
          <Segmented<number>
            label="Размер списка"
            value={size}
            onChange={setSize}
            options={LIST_SIZES.map((value) => ({ value, label: String(value) }))}
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="payback-cost">Стоимость проверки, ₽</FieldLabel>
          <Input
            id="payback-cost"
            type="number"
            inputMode="numeric"
            min={0}
            step={1000}
            className="font-mono tabular-nums"
            value={cost}
            onChange={(event) => setCost(event.target.value)}
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="payback-loss">Ущерб от инцидента, ₽</FieldLabel>
          <Input
            id="payback-loss"
            type="number"
            inputMode="numeric"
            min={0}
            step={10000}
            className="font-mono tabular-nums"
            value={loss}
            onChange={(event) => setLoss(event.target.value)}
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="payback-share">Доля предотвращаемых, %</FieldLabel>
          <Input
            id="payback-share"
            type="number"
            inputMode="numeric"
            min={0}
            max={100}
            step={5}
            className="font-mono tabular-nums"
            value={share}
            onChange={(event) => setShare(event.target.value)}
          />
        </Field>
      </div>
      <p className="px-4 pt-2 pb-4 text-[12px] text-faint">
        Стоимость, ущерб и доля предотвращаемых — пример, заменяется ценами заказчика.
      </p>
      <div className="grid border-t border-border-soft sm:grid-cols-3 sm:divide-x sm:divide-border-soft">
        <Output
          label="Точность списка"
          value={formatShare(precision, 1)}
          detail={precision != null ? `${decimal(precision * size)} из ${size} объектов с событием` : undefined}
        />
        <Output label="Порог безубыточности" value={formatShare(result.breakEven, 1)} detail="стоимость ÷ (ущерб × доля)" />
        <Output
          label="Эффект в год"
          value={effect != null ? rubles(effect) : "—"}
          detail="365 × (k × точность × доля × ущерб − k × стоимость)"
          className={cn(effect != null && effect > 0 && "text-vena", effect != null && effect < 0 && "text-status-critical")}
        />
      </div>
      <p className="border-t border-border-soft px-4 py-3 text-[13.5px]">{paybackVerdict(precision, result)}</p>
    </section>
  )
}

export function ObjectLevelSection() {
  const report = useObjectLevel()

  if (report.isPending) return <LoadingBar className="min-h-24" />
  if (report.isError) {
    return (
      <StateMessage
        title="Точность на уровне объекта недоступна"
        description="Не удалось загрузить метрики на уровне объекта."
        action={
          <Button variant="outline" size="sm" onClick={() => report.refetch()}>
            Повторить
          </Button>
        }
      />
    )
  }
  if (!report.data || report.data.models.length === 0) return null

  return (
    <>
      <MetricsTable models={report.data.models} period={report.data.period} />
      <PaybackCalculator models={report.data.models} />
    </>
  )
}
