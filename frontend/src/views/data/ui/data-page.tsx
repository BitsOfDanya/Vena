"use client"

import { useDataChannels, useDataEvents, useDataObjects } from "@/entities/data"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/ui/tabs"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/shared/ui/table"

export function DataPage() {
  const events = useDataEvents()
  const channels = useDataChannels()
  const objects = useDataObjects()
  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-5 md:p-8"><div className="mx-auto max-w-[1300px] space-y-6">
      <div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">Реестр и телеметрия</p><h1 className="mt-2 text-3xl font-semibold tracking-tight">Данные инфраструктуры</h1><p className="mt-1 text-sm text-muted-foreground">Демонстрационные записи и файлы, загруженные оператором.</p></div>
      <Tabs defaultValue="events" className="space-y-5"><TabsList><TabsTrigger value="events">События</TabsTrigger><TabsTrigger value="channels">Каналы</TabsTrigger><TabsTrigger value="objects">Объекты</TabsTrigger></TabsList>
        <TabsContent value="events"><Card className="border border-border/70"><CardHeader><CardTitle>Журнал датчиков</CardTitle><CardDescription>Последние 100 событий</CardDescription></CardHeader><CardContent>{events.data?.length ? <Table><TableHeader><TableRow><TableHead>ID записи</TableHead><TableHead>Канал</TableHead><TableHead>Тип</TableHead><TableHead>Значение</TableHead><TableHead>Дата</TableHead></TableRow></TableHeader><TableBody>{events.data.map((item) => <TableRow key={item.id}><TableCell>{item.source_record_id}</TableCell><TableCell>{item.channel_id}</TableCell><TableCell>{item.channel_type || "—"}</TableCell><TableCell>{item.value_raw}</TableCell><TableCell>{new Date(item.occurred_at).toLocaleString("ru-RU")}</TableCell></TableRow>)}</TableBody></Table> : <p className="py-10 text-center text-sm text-muted-foreground">Нет событий</p>}</CardContent></Card></TabsContent>
        <TabsContent value="channels"><Card className="border border-border/70"><CardHeader><CardTitle>Реестр каналов</CardTitle><CardDescription>Первые 500 записей</CardDescription></CardHeader><CardContent>{channels.data?.length ? <Table><TableHeader><TableRow><TableHead>ID канала</TableHead><TableHead>Тег объекта</TableHead><TableHead>Тип</TableHead><TableHead>Название</TableHead></TableRow></TableHeader><TableBody>{channels.data.map((item) => <TableRow key={item.id}><TableCell>{item.id}</TableCell><TableCell>{item.object_tag}</TableCell><TableCell>{item.channel_type || "—"}</TableCell><TableCell>{item.display_name || "—"}</TableCell></TableRow>)}</TableBody></Table> : <p className="py-10 text-center text-sm text-muted-foreground">Нет каналов</p>}</CardContent></Card></TabsContent>
        <TabsContent value="objects"><Card className="border border-border/70"><CardHeader><CardTitle>Дерево объектов</CardTitle><CardDescription>Первые 500 записей</CardDescription></CardHeader><CardContent>{objects.data?.length ? <Table><TableHeader><TableRow><TableHead>ID объекта</TableHead><TableHead>Название</TableHead><TableHead>Система</TableHead><TableHead>Тег</TableHead></TableRow></TableHeader><TableBody>{objects.data.map((item) => <TableRow key={item.id}><TableCell>{item.id}</TableCell><TableCell>{item.name}</TableCell><TableCell>{item.system_name || "—"}</TableCell><TableCell>{item.tag || "—"}</TableCell></TableRow>)}</TableBody></Table> : <p className="py-10 text-center text-sm text-muted-foreground">Нет объектов</p>}</CardContent></Card></TabsContent>
      </Tabs>
    </div></div>
  )
}
