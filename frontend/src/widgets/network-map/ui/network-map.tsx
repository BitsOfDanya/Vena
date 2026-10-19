"use client"

import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import { Maximize, Minus, Plus } from "lucide-react"

import {
  extractMapGeometry,
  getSpatialCollection,
  type MapAssetPoint,
  type MapGeometry,
} from "@/entities/infrastructure/api/spatial-client"
import { STATUS_LABEL, type AssetStatus } from "@/entities/infrastructure"
import { cn } from "@/shared/lib/utils"
import { Button } from "@/shared/ui/button"

const STATUS_FILL: Record<AssetStatus, string> = {
  normal: "var(--status-normal)",
  attention: "var(--status-attention)",
  critical: "var(--status-critical)",
  offline: "var(--status-offline, #8a8580)",
}

const UNKNOWN_FILL = "color-mix(in oklab, var(--foreground) 22%, var(--background))"
const STATUS_RANK: Record<AssetStatus, number> = { offline: 0, normal: 1, attention: 2, critical: 3 }
const EMPTY: MapGeometry = { assets: [], corridor: null, collectors: [], lines: [], generated: false }
const MIN_SCALE = 0.7
const MAX_SCALE = 12
const LABEL_LIMIT = 12
const LABEL_SCALE = 1.6

type Bounds = { minLon: number; maxLon: number; minLat: number; maxLat: number }

function project(lon: number, lat: number, bounds: Bounds, width: number, height: number, pad: number) {
  const x = pad + ((lon - bounds.minLon) / Math.max(bounds.maxLon - bounds.minLon, 1e-9)) * (width - pad * 2)
  const y = pad + ((bounds.maxLat - lat) / Math.max(bounds.maxLat - bounds.minLat, 1e-9)) * (height - pad * 2)
  return { x, y }
}

function boundsOf(points: { lon: number; lat: number }[]): Bounds {
  let minLon = Infinity
  let maxLon = -Infinity
  let minLat = Infinity
  let maxLat = -Infinity
  for (const point of points) {
    minLon = Math.min(minLon, point.lon)
    maxLon = Math.max(maxLon, point.lon)
    minLat = Math.min(minLat, point.lat)
    maxLat = Math.max(maxLat, point.lat)
  }
  const lonPad = Math.max((maxLon - minLon) * 0.12, 0.001)
  const latPad = Math.max((maxLat - minLat) * 0.12, 0.001)
  return {
    minLon: minLon - lonPad,
    maxLon: maxLon + lonPad,
    minLat: minLat - latPad,
    maxLat: maxLat + latPad,
  }
}

function localPoint(svg: SVGSVGElement, clientX: number, clientY: number) {
  const matrix = svg.getScreenCTM()
  if (!matrix) return { x: clientX, y: clientY }
  const point = new DOMPoint(clientX, clientY).matrixTransform(matrix.inverse())
  return { x: point.x, y: point.y }
}

export function NetworkMap({
  statusOf,
  isDimmed,
  selectedId,
  onSelect,
}: {
  statusOf: (assetId: string) => AssetStatus | undefined
  isDimmed: (asset: MapAssetPoint) => boolean
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  const spatial = useQuery({
    queryKey: ["infrastructure", "spatial"],
    queryFn: getSpatialCollection,
    staleTime: 60_000,
  })
  const geometry = React.useMemo(() => (spatial.data ? extractMapGeometry(spatial.data) : EMPTY), [spatial.data])

  const [view, setView] = React.useState({ scale: 1, tx: 0, ty: 0 })
  const drag = React.useRef<{ x: number; y: number; tx: number; ty: number } | null>(null)
  const svgRef = React.useRef<SVGSVGElement | null>(null)
  const width = 960
  const height = 640
  const pad = 36

  const bounds = React.useMemo(() => {
    const points = [
      ...geometry.assets,
      ...geometry.collectors,
      ...(geometry.corridor?.coordinates ?? []).map(([lon, lat]) => ({ lon, lat })),
      ...geometry.lines.flatMap((line) => line.paths.flat().map(([lon, lat]) => ({ lon, lat }))),
    ]
    return points.length > 0 ? boundsOf(points) : null
  }, [geometry])

  const lines = React.useMemo(() => {
    if (!bounds) return []
    return geometry.lines.map((line) => {
      const projected = line.paths.map((path) => path.map(([lon, lat]) => project(lon, lat, bounds, width, height, pad)))
      const longest = projected.reduce((best, path) => (path.length > best.length ? path : best), projected[0])
      return {
        line,
        d: projected
          .map((path) => path.map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(" "))
          .join(" "),
        anchor: longest[Math.floor(longest.length / 2)],
      }
    })
  }, [geometry.lines, bounds])

  const ready = bounds !== null
  React.useEffect(() => {
    const element = svgRef.current
    if (!element) return
    function onWheel(event: WheelEvent) {
      event.preventDefault()
      const point = localPoint(element!, event.clientX, event.clientY)
      setView((current) => {
        const scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, current.scale * (event.deltaY < 0 ? 1.08 : 0.92)))
        const ratio = scale / current.scale
        return { scale, tx: point.x - (point.x - current.tx) * ratio, ty: point.y - (point.y - current.ty) * ratio }
      })
    }
    element.addEventListener("wheel", onWheel, { passive: false })
    return () => element.removeEventListener("wheel", onWheel)
  }, [ready])

  const zoomBy = (factor: number) =>
    setView((current) => {
      const scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, current.scale * factor))
      const ratio = scale / current.scale
      return { scale, tx: width / 2 - (width / 2 - current.tx) * ratio, ty: height / 2 - (height / 2 - current.ty) * ratio }
    })

  if (spatial.isPending) {
    return <div className="flex size-full items-center justify-center text-sm text-muted-foreground">Загрузка карты…</div>
  }

  if (spatial.isError && !spatial.data) {
    return (
      <div className="flex size-full flex-col items-center justify-center gap-3 px-8 text-center text-sm text-muted-foreground">
        Пространственный слой недоступен.
        <Button variant="outline" size="sm" onClick={() => spatial.refetch()}>
          Повторить
        </Button>
      </div>
    )
  }

  if (!bounds) {
    return (
      <div className="flex size-full items-center justify-center px-8 text-center text-sm text-muted-foreground">
        Нет пространственных данных. Импортируйте GeoJSON/WKT через API `/spatial`.
      </div>
    )
  }

  const unit = 1 / view.scale
  const placed = geometry.assets.map((asset) => ({ asset, status: statusOf(asset.assetId), dimmed: isDimmed(asset) }))
  const visibleObjects = new Set(placed.filter((item) => !item.dimmed).map((item) => item.asset.objectId))
  const filtering = placed.some((item) => item.dimmed)
  const ordered = [...placed].sort(
    (left, right) =>
      Number(right.dimmed) - Number(left.dimmed) ||
      (left.status ? STATUS_RANK[left.status] : -1) - (right.status ? STATUS_RANK[right.status] : -1)
  )
  const collectorCount = geometry.lines.filter((line) => line.kind === "collector").length
  const showLineLabels = collectorCount <= LABEL_LIMIT || view.scale >= LABEL_SCALE
  const sourceLabel = spatial.data?.source === "demo_spatial" ? "демо" : "GeoJSON"

  return (
    <div className="relative size-full min-h-0 overflow-hidden bg-[linear-gradient(180deg,color-mix(in_oklab,var(--elevated)_88%,#d7e0ea),color-mix(in_oklab,var(--surface)_92%,#c9d4c4))]">
      <p className="pointer-events-none absolute top-3 left-4 z-10 font-mono text-[12px] text-faint">
        {geometry.generated ? "Условная геометрия · риск" : `Карта · ${sourceLabel} · риск`}
      </p>
      <svg
        ref={svgRef}
        role="img"
        aria-label="Карта инфраструктуры"
        viewBox={`0 0 ${width} ${height}`}
        className="size-full touch-none cursor-grab select-none active:cursor-grabbing"
        onPointerDown={(event) => {
          const point = localPoint(event.currentTarget, event.clientX, event.clientY)
          drag.current = { x: point.x, y: point.y, tx: view.tx, ty: view.ty }
          event.currentTarget.setPointerCapture?.(event.pointerId)
        }}
        onPointerMove={(event) => {
          if (!drag.current) return
          const point = localPoint(event.currentTarget, event.clientX, event.clientY)
          const start = drag.current
          setView((current) => ({ ...current, tx: start.tx + (point.x - start.x), ty: start.ty + (point.y - start.y) }))
        }}
        onPointerUp={() => {
          drag.current = null
        }}
      >
        <g transform={`translate(${view.tx} ${view.ty}) scale(${view.scale})`}>
          <rect x={0} y={0} width={width} height={height} fill="transparent" />
          {geometry.corridor ? (
            <path
              d={geometry.corridor.coordinates
                .map((pair, index) => {
                  const { x, y } = project(pair[0], pair[1], bounds, width, height, pad)
                  return `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`
                })
                .join(" ")}
              fill="none"
              stroke="color-mix(in oklab, var(--foreground) 28%, transparent)"
              strokeWidth={3.5}
              strokeLinecap="round"
            />
          ) : null}
          {lines.map(({ line, d }) => (
            <path
              key={line.id}
              d={d}
              fill="none"
              stroke={`color-mix(in oklab, var(--foreground) ${line.kind === "collector" ? 45 : 30}%, transparent)`}
              strokeWidth={line.kind === "collector" ? 3.5 : 2}
              strokeLinecap="round"
              strokeLinejoin="round"
              vectorEffect="non-scaling-stroke"
              opacity={filtering && line.objectId && !visibleObjects.has(line.objectId) ? 0.35 : 1}
            />
          ))}
          {showLineLabels
            ? lines
                .filter(({ line }) => line.kind === "collector" && line.name)
                .map(({ line, anchor }) => (
                  <text
                    key={`label-${line.id}`}
                    x={anchor.x + 6 * unit}
                    y={anchor.y - 6 * unit}
                    fontSize={10 * unit}
                    className="pointer-events-none fill-muted-foreground"
                    paintOrder="stroke"
                    stroke="var(--background)"
                    strokeWidth={3 * unit}
                  >
                    {line.name}
                  </text>
                ))
            : null}
          {geometry.collectors.map((collector) => {
            const { x, y } = project(collector.lon, collector.lat, bounds, width, height, pad)
            return (
              <g key={`c-${collector.assetId}`}>
                <circle
                  cx={x}
                  cy={y}
                  r={7}
                  fill="color-mix(in oklab, var(--foreground) 18%, transparent)"
                  stroke="var(--border)"
                  strokeWidth={1}
                />
                <text x={x + 10} y={y + 3} className="fill-muted-foreground text-[10px]">
                  {collector.groupId ?? collector.name}
                </text>
              </g>
            )
          })}
          {ordered.map(({ asset, status, dimmed }) => {
            const { x, y } = project(asset.lon, asset.lat, bounds, width, height, pad)
            const selected = selectedId === asset.assetId
            const label = asset.name ? `${asset.name} (${asset.assetId})` : asset.assetId
            return (
              <g
                key={asset.assetId}
                role="button"
                tabIndex={0}
                transform={`translate(${x} ${y})`}
                className={cn("cursor-pointer outline-none", dimmed && "opacity-25")}
                aria-label={`Канал ${label}${status ? `, ${STATUS_LABEL[status].toLowerCase()}` : ""}`}
                aria-pressed={selected}
                onPointerDown={(event) => event.stopPropagation()}
                onClick={(event) => {
                  event.stopPropagation()
                  onSelect(asset.assetId)
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault()
                    onSelect(asset.assetId)
                  }
                }}
              >
                <title>{label}</title>
                <circle
                  r={(selected ? 6 : 3.5) * Math.min(1, unit * 1.5)}
                  fill={status ? STATUS_FILL[status] : UNKNOWN_FILL}
                  stroke={selected ? "var(--foreground)" : "color-mix(in oklab, var(--background) 70%, transparent)"}
                  strokeWidth={selected ? 2 : 1}
                  vectorEffect="non-scaling-stroke"
                />
              </g>
            )
          })}
        </g>
      </svg>
      <div className="absolute bottom-3 left-3 flex flex-col gap-1">
        <Button variant="outline" size="icon-sm" aria-label="Увеличить" onClick={() => zoomBy(1.3)}>
          <Plus />
        </Button>
        <Button variant="outline" size="icon-sm" aria-label="Уменьшить" onClick={() => zoomBy(1 / 1.3)}>
          <Minus />
        </Button>
        <Button variant="outline" size="icon-sm" aria-label="Вписать в экран" onClick={() => setView({ scale: 1, tx: 0, ty: 0 })}>
          <Maximize />
        </Button>
      </div>
      {geometry.lines.length > 0 ? (
        <div className="pointer-events-none absolute right-4 bottom-4 flex flex-col gap-1.5 border-l bg-background/80 pl-3 text-[10px] font-medium text-muted-foreground">
          <span className="text-faint">Легенда</span>
          {(["normal", "attention", "critical"] as const).map((status) => (
            <span key={status} className="flex items-center gap-2">
              <span aria-hidden className="size-2.5 rounded-full" style={{ background: STATUS_FILL[status] }} />
              {STATUS_LABEL[status]}
            </span>
          ))}
          <span className="flex items-center gap-2">
            <span aria-hidden className="size-2.5 rounded-full" style={{ background: UNKNOWN_FILL }} />
            Нет прогноза
          </span>
          <span className="flex items-center gap-2">
            <span aria-hidden className="h-[3px] w-3 bg-foreground/35" />
            Коллектор
          </span>
          <span className="flex items-center gap-2">
            <span aria-hidden className="h-px w-3 bg-foreground/25" />
            Галерея
          </span>
        </div>
      ) : null}
    </div>
  )
}
