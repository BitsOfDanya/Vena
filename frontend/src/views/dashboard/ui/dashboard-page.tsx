"use client"

import { Activity, Building2, Cable, Database, FileUp, MapPinned, RadioTower } from "lucide-react"
import Link from "next/link"
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts"

import { useDataActivity, useDataEvents, useDataSummary } from "@/entities/data"
import { useImports } from "@/entities/import-batch"
import { useSnapshotStatus } from "@/entities/prediction"
import { useSession } from "@/entities/session"
import { Badge } from "@/shared/ui/badge"
import { Button } from "@/shared/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/ui/card"
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/shared/ui/chart"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/shared/ui/table"

const number = new Intl.NumberFormat("ru-RU")

export function DashboardPage() {
  const summary = useDataSummary()
  const activity = useDataActivity()
  const events = useDataEvents()
  const imports = useImports()
  const session = useSession()
  const snapshot = useSnapshotStatus(session.data?.role === "dispatcher")
  const metrics = [
    { label: "Объекты", value: summary.data?.objects, icon: Building2, color: "text-primary", tint: "bg-primary/15" },
    { label: "Каналы", value: summary.data?.channels, icon: Cable, color: "text-chart-2", tint: "bg-chart-2/15" },
    { label: "События", value: summary.data?.events, icon: Activity, color: "text-chart-3", tint: "bg-chart-3/15" },
    { label: "Загрузки", value: summary.data?.imports, icon: Database, color: "text-chart-4", tint: "bg-chart-4/15" },
  ]

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-5 md:p-8">
      <div className="mx-auto max-w-[1500px] space-y-7">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">Оперативный обзор</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight">Панель управления</h1>
            <p className="mt-1 text-sm text-muted-foreground">{session.data?.role === "dispatcher" ? "Состояние загруженных данных и прогнозного контура." : "Состояние загруженных данных инфраструктуры."}</p>
          </div>
          <div className="flex flex-wrap gap-2"><Button asChild size="lg" variant="outline"><Link href="/map"><MapPinned className="size-4" />Карта Москвы</Link></Button>{session.data?.role === "operator" && <Button asChild size="lg"><Link href="/imports"><FileUp className="size-4" />Загрузить данные</Link></Button>}</div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {metrics.map(({ label, value, icon: Icon, color, tint }) => (
            <Card key={label} className="min-h-36 border border-border/65 shadow-sm shadow-black/10">
              <CardContent className="flex h-full items-start justify-between pt-1">
                <div><p className="text-sm text-muted-foreground">{label}</p><p className="mt-5 text-3xl font-semibold tabular-nums">{value === undefined ? "—" : number.format(value)}</p></div>
                <div className={`flex size-12 items-center justify-center rounded-2xl ${tint} ${color}`}><Icon className="size-6" /></div>
              </CardContent>
            </Card>
          ))}
        </div>

        <div className="grid gap-5 xl:grid-cols-[minmax(0,1.7fr)_minmax(300px,1fr)]">
          <Card className="border border-border/65 shadow-sm shadow-black/10">
            <CardHeader><CardTitle>Активность событий</CardTitle><CardDescription>Количество записей по датам из базы данных</CardDescription></CardHeader>
            <CardContent>
              {activity.data?.length ? (
                <ChartContainer className="h-72 w-full aspect-auto" config={{ count: { label: "События", color: "var(--chart-1)" } }}>
                  <AreaChart data={activity.data} margin={{ left: 0, right: 10, top: 10 }}>
                    <defs><linearGradient id="eventsFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.28} /><stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0} /></linearGradient></defs>
                    <CartesianGrid vertical={false} stroke="var(--border)" strokeOpacity={0.5} />
                    <XAxis dataKey="day" tickLine={false} axisLine={false} tickFormatter={(value: string) => value.slice(5)} />
                    <YAxis tickLine={false} axisLine={false} width={38} />
                    <ChartTooltip content={<ChartTooltipContent />} />
                    <Area dataKey="count" type="monotone" stroke="var(--chart-1)" strokeWidth={3} fill="url(#eventsFill)" />
                  </AreaChart>
                </ChartContainer>
              ) : <div className="flex h-72 items-center justify-center rounded-xl border border-dashed border-border text-sm text-muted-foreground">График появится после первой загрузки журнала</div>}
            </CardContent>
          </Card>
          <Card className="border border-border/65 shadow-sm shadow-black/10">
            <CardHeader><CardTitle>{session.data?.role === "dispatcher" ? "Прогнозный контур" : "Контур данных"}</CardTitle><CardDescription>{session.data?.role === "dispatcher" ? "Статус последнего снимка ML" : "Статус загруженных журналов"}</CardDescription></CardHeader>
            <CardContent className="space-y-5">
              <div className="flex items-center gap-4 rounded-xl bg-secondary/60 p-4">
                <div className="flex size-12 items-center justify-center rounded-xl bg-primary/15 text-primary">{session.data?.role === "dispatcher" ? <RadioTower className="size-6" /> : <FileUp className="size-6" />}</div>
                <div><p className="font-medium">{session.data?.role === "dispatcher" ? snapshot.data?.available ? "Снимок доступен" : "Снимок недоступен" : "Ручная загрузка"}</p><p className="text-xs text-muted-foreground">{session.data?.role === "dispatcher" ? snapshot.data?.available ? `${number.format(snapshot.data.predictionCount)} прогнозов` : "Требуется расчёт ML" : "CSV и XLSX обрабатываются в фоне"}</p></div>
              </div>
              {session.data?.role === "dispatcher" && <div className="flex items-center justify-between border-b border-border pb-3 text-sm"><span className="text-muted-foreground">Свежесть</span><Badge variant={snapshot.data?.stale ? "destructive" : "secondary"}>{snapshot.data?.stale ? "Устарел" : snapshot.data?.available ? "Актуален" : "Нет данных"}</Badge></div>}
              <div className="flex items-center justify-between border-b border-border pb-3 text-sm"><span className="text-muted-foreground">Последнее событие</span><span>{summary.data?.last_event_at ? new Date(summary.data.last_event_at).toLocaleString("ru-RU") : "—"}</span></div>
              <div className="flex items-center justify-between text-sm"><span className="text-muted-foreground">Импортов в обработке</span><span>{imports.data?.filter((item) => ["pending", "processing"].includes(item.status)).length ?? 0}</span></div>
            </CardContent>
          </Card>
        </div>

        <Card className="border border-border/65 shadow-sm shadow-black/10">
          <CardHeader className="flex-row items-center justify-between"><div><CardTitle>Последние события</CardTitle><CardDescription>Последние записи в базе данных</CardDescription></div><Button asChild variant="outline" size="sm"><Link href="/data">Все данные</Link></Button></CardHeader>
          <CardContent>
            {events.data?.length ? <Table><TableHeader><TableRow><TableHead>Время</TableHead><TableHead>Канал</TableHead><TableHead>Тип</TableHead><TableHead>Значение</TableHead></TableRow></TableHeader><TableBody>{events.data.slice(0, 6).map((event) => <TableRow key={event.id}><TableCell>{new Date(event.occurred_at).toLocaleString("ru-RU")}</TableCell><TableCell className="font-medium">{event.channel_id}</TableCell><TableCell>{event.channel_type || "—"}</TableCell><TableCell>{event.value_raw}</TableCell></TableRow>)}</TableBody></Table> : <p className="py-8 text-center text-sm text-muted-foreground">Событий пока нет. Загрузите журнал, чтобы начать работу.</p>}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
