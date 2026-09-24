"use client"

import { Activity, Cable, Layers3, MapPinned, Search, Waypoints } from "lucide-react"
import dynamic from "next/dynamic"
import { useMemo, useState } from "react"

import { Badge } from "@/shared/ui/badge"
import { Button } from "@/shared/ui/button"
import { Card, CardContent } from "@/shared/ui/card"
import { Input } from "@/shared/ui/input"
import { NativeSelect, NativeSelectOption } from "@/shared/ui/native-select"
import { Switch } from "@/shared/ui/switch"

import type { MapEdge, MapNode } from "../api/network"
import { useMapNetwork } from "../model/queries"

const GeoMap = dynamic(() => import("./geo-map").then((module) => module.GeoMap), {
  ssr: false,
  loading: () => <div className="h-full min-h-[480px] animate-pulse rounded-2xl border border-border bg-secondary" />,
})

const EMPTY_NODES: MapNode[] = []
const EMPTY_EDGES: MapEdge[] = []
const TYPE_LABELS: Record<string, string> = {
  hub: "Опорные узлы",
  collector: "Коллекторы",
  pump: "Насосные станции",
  ventilation: "Вентшахты",
  power: "Электроузлы",
  monitoring: "Мониторинг",
}
const STATUS_LABELS: Record<string, string> = {
  normal: "Норма",
  attention: "Внимание",
  critical: "Критично",
}

function statusClass(status: string) {
  return status === "critical" ? "bg-destructive" : status === "attention" ? "bg-chart-3" : "bg-chart-2"
}

export function MapPage() {
  const network = useMapNetwork()
  const [query, setQuery] = useState("")
  const [district, setDistrict] = useState("all")
  const [type, setType] = useState("all")
  const [status, setStatus] = useState("all")
  const [showEdges, setShowEdges] = useState(true)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const allNodes = network.data?.nodes ?? EMPTY_NODES
  const allEdges = network.data?.edges ?? EMPTY_EDGES
  const districts = useMemo(() => [...new Set(allNodes.map((node) => node.district).filter(Boolean))].sort(), [allNodes])
  const types = useMemo(() => [...new Set(allNodes.map((node) => node.object_type))].sort(), [allNodes])
  const needle = query.trim().toLocaleLowerCase("ru-RU")
  const nodes = useMemo(() => allNodes.filter((node) =>
    (district === "all" || node.district === district) &&
    (type === "all" || node.object_type === type) &&
    (status === "all" || node.status === status) &&
    (!needle || `${node.name} ${node.id} ${node.district}`.toLocaleLowerCase("ru-RU").includes(needle))
  ), [allNodes, district, type, status, needle])
  const edges = useMemo(() => {
    if (!showEdges) return EMPTY_EDGES
    const visible = new Set(nodes.map((node) => node.id))
    return allEdges.filter((edge) => visible.has(edge.source_id) && visible.has(edge.target_id))
  }, [allEdges, nodes, showEdges])
  const selected = nodes.find((node) => node.id === selectedId)
  const needsAttention = allNodes.filter((node) => node.status !== "normal").length
  const isDemo = allNodes.some((node) => node.is_demo)

  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-5 md:p-8">
      <div className="mx-auto max-w-[1600px] space-y-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">География инфраструктуры</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight">Карта Москвы</h1>
            <p className="mt-1 text-sm text-muted-foreground">Все объекты с координатами и связи между ними на одной карте.</p>
          </div>
          {isDemo && <Badge variant="secondary" className="border border-primary/30 bg-primary/10 px-3 py-1.5 text-primary">Демонстрационная география</Badge>}
        </div>

        {isDemo && <div className="rounded-xl border border-chart-3/25 bg-chart-3/10 px-4 py-3 text-sm text-chart-3">Точки и линии сети созданы для демонстрации интерфейса. Они не обозначают реальные коллекторы и не подходят для планирования работ.</div>}

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {[
            { label: "Объекты", value: allNodes.length, icon: MapPinned, color: "text-primary" },
            { label: "Связи сети", value: allEdges.length, icon: Waypoints, color: "text-chart-2" },
            { label: "Округа", value: districts.length, icon: Layers3, color: "text-chart-4" },
            { label: "Требуют внимания", value: needsAttention, icon: Activity, color: "text-chart-3" },
          ].map(({ label, value, icon: Icon, color }) => (
            <Card key={label} className="border-border/70"><CardContent className="flex items-center justify-between py-1"><div><p className="text-sm text-muted-foreground">{label}</p><p className="mt-2 text-2xl font-semibold tabular-nums">{network.isPending ? "—" : value}</p></div><Icon className={`size-7 ${color}`} /></CardContent></Card>
          ))}
        </div>

        <Card className="border-border/70"><CardContent className="flex flex-wrap items-end gap-3 py-1">
          <div className="relative min-w-[220px] flex-1"><Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" /><Input aria-label="Поиск объекта" placeholder="Название, ID или округ" className="pl-9" value={query} onChange={(event) => setQuery(event.target.value)} /></div>
          <NativeSelect aria-label="Округ" value={district} onChange={(event) => setDistrict(event.target.value)} className="min-w-36"><NativeSelectOption value="all">Все округа</NativeSelectOption>{districts.map((item) => <NativeSelectOption key={item} value={item}>{item}</NativeSelectOption>)}</NativeSelect>
          <NativeSelect aria-label="Тип объекта" value={type} onChange={(event) => setType(event.target.value)} className="min-w-44"><NativeSelectOption value="all">Все типы</NativeSelectOption>{types.map((item) => <NativeSelectOption key={item} value={item}>{TYPE_LABELS[item] ?? item}</NativeSelectOption>)}</NativeSelect>
          <NativeSelect aria-label="Состояние" value={status} onChange={(event) => setStatus(event.target.value)} className="min-w-36"><NativeSelectOption value="all">Все состояния</NativeSelectOption><NativeSelectOption value="normal">Норма</NativeSelectOption><NativeSelectOption value="attention">Внимание</NativeSelectOption><NativeSelectOption value="critical">Критично</NativeSelectOption></NativeSelect>
          <label className="flex h-9 items-center gap-2 whitespace-nowrap px-2 text-sm text-muted-foreground"><Switch checked={showEdges} onCheckedChange={setShowEdges} />Линии сети</label>
        </CardContent></Card>

        {network.isError ? (
          <Card><CardContent className="flex min-h-96 flex-col items-center justify-center gap-3 text-center"><p>Карту не удалось загрузить.</p><Button variant="outline" onClick={() => void network.refetch()}>Повторить</Button></CardContent></Card>
        ) : (
          <div className="grid min-h-[620px] gap-4 xl:grid-cols-[minmax(0,1fr)_330px]">
            <div className="relative min-h-[520px]"><GeoMap nodes={nodes} edges={edges} selectedId={selected?.id ?? null} onSelect={setSelectedId} /></div>
            <div className="flex min-h-[520px] flex-col gap-4">
              <Card className="border-border/70"><CardContent className="space-y-3 py-1">
                {selected ? <>
                  <div className="flex items-start justify-between gap-2"><div><p className="text-xs uppercase tracking-[0.14em] text-primary">Выбранный объект</p><h2 className="mt-1 text-lg font-semibold">{selected.name}</h2></div><span className={`mt-1 size-3 shrink-0 rounded-full ${statusClass(selected.status)}`} /></div>
                  <div className="grid grid-cols-2 gap-3 text-sm"><div><p className="text-xs text-muted-foreground">Округ</p><p>{selected.district || "—"}</p></div><div><p className="text-xs text-muted-foreground">Состояние</p><p>{STATUS_LABELS[selected.status] ?? selected.status}</p></div><div><p className="text-xs text-muted-foreground">Тип</p><p>{TYPE_LABELS[selected.object_type] ?? selected.object_type}</p></div><div><p className="text-xs text-muted-foreground">ID</p><p className="truncate font-mono text-xs" title={selected.id}>{selected.id}</p></div></div>
                  <p className="border-t border-border pt-3 font-mono text-xs text-muted-foreground">{selected.latitude.toFixed(5)}, {selected.longitude.toFixed(5)}</p>
                </> : <><p className="text-xs uppercase tracking-[0.14em] text-primary">Инспектор</p><p className="font-medium">Выберите точку на карте</p><p className="text-sm text-muted-foreground">Здесь появятся тип объекта, округ, состояние и координаты.</p></>}
              </CardContent></Card>
              <Card className="min-h-0 flex-1 border-border/70"><CardContent className="flex h-full min-h-0 flex-col py-1"><div className="flex items-center justify-between"><h2 className="font-semibold">Объекты на карте</h2><Badge variant="secondary">{nodes.length}</Badge></div><div className="mt-3 min-h-0 flex-1 space-y-1 overflow-y-auto pr-1 xl:max-h-[400px]">{nodes.length ? nodes.map((node) => <Button key={node.id} variant="ghost" className={`h-auto w-full justify-start gap-3 px-2 py-2 text-left ${selectedId === node.id ? "bg-primary/10" : ""}`} onClick={() => setSelectedId(node.id)}><span className={`size-2.5 shrink-0 rounded-full ${statusClass(node.status)}`} /><span className="min-w-0"><span className="block truncate text-sm font-medium">{node.name}</span><span className="block truncate text-xs text-muted-foreground">{node.district} · {TYPE_LABELS[node.object_type] ?? node.object_type}</span></span></Button>) : <p className="py-8 text-center text-sm text-muted-foreground">Объекты по фильтру не найдены</p>}</div></CardContent></Card>
            </div>
          </div>
        )}
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted-foreground"><span className="flex items-center gap-2"><span className="size-2.5 rounded-full bg-chart-2" />Норма</span><span className="flex items-center gap-2"><span className="size-2.5 rounded-full bg-chart-3" />Внимание</span><span className="flex items-center gap-2"><span className="size-2.5 rounded-full bg-destructive" />Критично</span><span className="flex items-center gap-2"><Cable className="size-3 text-primary" />Связь сети</span></div>
      </div>
    </div>
  )
}
